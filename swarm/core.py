# Standard library imports
from collections import defaultdict
import copy
import json
from typing import List, Optional

# Local imports
from .util import function_to_json, debug_print, merge_chunk
from .types import (
    Agent,
    AgentFunction,
    ChatCompletionMessage,
    ChatCompletionMessageToolCall,
    Function,
    Response,
    Result,
)

import litellm
litellm.modify_params = True
litellm.drop_params = True # Drop any unmapped params

__CTX_VARS_NAME__ = "context_variables"

class Swarm:
    def __init__(self, config_path: Optional[str] = None):
       pass

    def get_chat_completion(
        self,
        agent: Agent,
        history: List,
        context_variables: dict,
        model_override: str,
        stream: bool,
        debug: bool,
    ) -> ChatCompletionMessage:
        context_variables = defaultdict(str, context_variables)
        instructions = (
            agent.instructions(context_variables)
            if callable(agent.instructions)
            else agent.instructions
        )
        messages = [{"role": "system", "content": instructions}]
        for msg in history:
            # Converti il messaggio Pydantic in dizionario e poi crea una copia
            msg_dict = msg.dict() if hasattr(msg, 'dict') else dict(msg)
            msg_copy = msg_dict.copy()
            msg_copy.pop('sender', None)  # Rimuove sender temporaneamente
            messages.append(msg_copy)
        
        debug_print(debug, "Getting chat completion for...:", messages)

        # Prepare tools for the chat completion
        tools = [function_to_json(f) for f in agent.functions]
        # hide context_variables from model
        for tool in tools:
            params = tool["function"]["parameters"]
            params["properties"].pop(__CTX_VARS_NAME__, None)
            if __CTX_VARS_NAME__ in params["required"]:
                params["required"].remove(__CTX_VARS_NAME__)

        # Prepare params for the chat completion
        optional_params = {
            "response_format": agent.response_format,
            "temperature": agent.temperature,
            "max_completion_tokens": agent.max_completion_tokens,
            "response_format": agent.response_format,
            "top_p": agent.top_p,
            "api_base": agent.api_base,    
        }
        create_params = {
            "messages": messages,
            "model": model_override or agent.model,
            "stream": stream,
            **{k: v for k, v in optional_params.items() if v is not None}
        }
        
        if tools:
            create_params["parallel_tool_calls"] = agent.parallel_tool_calls
            create_params["tools"] = tools
            create_params["tool_choice"] = agent.tool_choice
        return litellm.completion(**create_params)

    def handle_function_result(self, result, debug) -> Result:
        match result:
            case Result() as result:
                return result
            case Agent() as agent:
                return Result(
                    value=json.dumps({"assistant": agent.name}),
                    agent=agent,
                )
            case _:
                try:
                    return Result(value=str(result))
                except Exception as e:
                    error_message = f"Failed to cast response to string: {result}. Make sure agent functions return a string or Result object. Error: {str(e)}"
                    debug_print(debug, error_message)
                    raise TypeError(error_message)

    def handle_tool_calls(
        self,
        tool_calls: List[ChatCompletionMessageToolCall],
        functions: List[AgentFunction],
        context_variables: dict,
        debug: bool,
    ) -> Response:
        function_map = {f.__name__: f for f in functions}
        partial_response = Response(
            messages=[], agent=None, context_variables={})

        for tool_call in tool_calls:
            name = tool_call.function.name 
            # handle missing tool case, skip to next tool
            if name not in function_map:
                debug_print(debug, f"Tool {name} not found in function map.")
                partial_response.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "tool_name": name,
                        "content": f"Error: Tool {name} not found.",
                    }
                )
                continue
            
            args = json.loads(tool_call.function.arguments)
            debug_print(
                debug, f"Processing tool call: {name} with arguments {args}")

            func = function_map[name]
            # pass context_variables to agent functions
            if __CTX_VARS_NAME__ in func.__code__.co_varnames:
                args[__CTX_VARS_NAME__] = context_variables
            raw_result = function_map[name](**args)

            result: Result = self.handle_function_result(raw_result, debug)
            partial_response.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "tool_name": name,
                    "content": result.value,
                }
            )
            partial_response.context_variables.update(result.context_variables)
            if result.agent:
                partial_response.agent = result.agent

        return partial_response

    def run_and_stream(
        self,
        agent: Agent,
        messages: List,
        context_variables: dict = {},
        model_override: str = None,
        debug: bool = False,
        max_turns: int = float("inf"),
        execute_tools: bool = True,
    ):
        active_agent = agent
        context_variables = copy.deepcopy(context_variables)
        history = copy.deepcopy(messages)
        init_len = len(messages)

        while len(history) - init_len < max_turns:
            message = {
                "content": "",
                "sender": agent.name,
                "role": "assistant",
                "function_call": None,
                "tool_calls": defaultdict(
                    lambda: {
                        "function": {"arguments": "", "name": ""},
                        "id": "",
                        "type": "",
                    }
                ),
            }

            # get completion with current history, agent
            completion = self.get_chat_completion(
                agent=active_agent,
                history=history,
                context_variables=context_variables,
                model_override=model_override,
                stream=True,
                debug=debug,
            )

            yield {"delim": "start"}
            for chunk in completion:
                delta = chunk["choices"][0]["delta"]
                delta_dict = delta.dict() if hasattr(delta, 'dict') else dict(delta)
                if delta_dict.get("role") == "assistant":
                    delta_dict["sender"] = active_agent.name
                yield delta_dict
                delta_dict.pop("role", None)
                delta_dict.pop("sender", None)
                merge_chunk(message, delta_dict)
            yield {"delim": "end"}

            message["tool_calls"] = list(
                message.get("tool_calls", {}).values())
            if not message["tool_calls"]:
                message["tool_calls"] = None
            debug_print(debug, "Received completion:", message)
            history.append(message)

            if not message["tool_calls"] or not execute_tools:
                debug_print(debug, "Ending turn.")
                break

            # convert tool_calls to objects
            tool_calls = []
            for tool_call in message["tool_calls"]:
                function = Function(
                    arguments=tool_call["function"]["arguments"],
                    name=tool_call["function"]["name"],
                )
                tool_call_object = ChatCompletionMessageToolCall(
                    id=tool_call["id"], function=function, type=tool_call["type"]
                )
                tool_calls.append(tool_call_object)

            # handle function calls, updating context_variables, and switching agents
            partial_response = self.handle_tool_calls(
                tool_calls, active_agent.functions, context_variables, debug
            )
            history.extend(partial_response.messages)
            context_variables.update(partial_response.context_variables)
            if partial_response.agent:
                active_agent = partial_response.agent

        yield {
            "response": Response(
                messages=history[init_len:],
                agent=active_agent,
                context_variables=context_variables,
            )
        }

    def run(
        self,
        agent: Agent,
        messages: List,
        context_variables: dict = {},
        model_override: str = None,
        stream: bool = False,
        debug: bool = False,
        max_turns: int = float("inf"),
        execute_tools: bool = True,
    ) -> Response:
        if stream:
            return self.run_and_stream(
                agent=agent,
                messages=messages,
                context_variables=context_variables,
                model_override=model_override,
                debug=debug,
                max_turns=max_turns,
                execute_tools=execute_tools,
            )

        active_agent = agent
        context_variables = copy.deepcopy(context_variables)
        history = copy.deepcopy(messages)
        init_len = len(messages)

        while len(history) - init_len < max_turns and active_agent:
            # get completion with current history, agent
            completion = self.get_chat_completion(
                agent=active_agent,
                history=history,
                context_variables=context_variables,
                model_override=model_override,
                stream=stream,
                debug=debug,
            )

            message = completion["choices"][0]["message"]
            debug_print(debug, "Received completion:", message)
            message["sender"] = active_agent.name
            history.append(message)
            if not message.get("tool_calls") or not execute_tools:
                debug_print(debug, "Ending turn.")
                break

            # handle function calls, updating context_variables, and switching agents
            partial_response = self.handle_tool_calls(
                message["tool_calls"], active_agent.functions, context_variables, debug
            )
            history.extend(partial_response.messages)
            context_variables.update(partial_response.context_variables)
            if partial_response.agent:
                active_agent = partial_response.agent

        return Response(
            messages=history[init_len:],
            agent=active_agent,
            context_variables=context_variables,
        )