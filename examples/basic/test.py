from swarm import Swarm, Agent

client = Swarm()

english_agent = Agent(
    name="English Agent",
    instructions="You only speak English.",
    model="ollama_chat/phi3",  
    api_base="http://localhost:11434"
)

spanish_agent = Agent(
    name="Spanish Agent",
    instructions="You only speak Spanish.",  
    model="ollama_chat/phi3",  
    api_base="http://localhost:11434"  
)


def transfer_to_spanish_agent():
    """Transfer spanish speaking users immediately."""
    return spanish_agent


english_agent.functions.append(transfer_to_spanish_agent)

messages = [{"role": "user", "content": "Hola. ¿Como estás?"}]
response = client.run(agent=english_agent, messages=messages)

print(response.messages[-1]["content"])

