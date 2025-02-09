from swarm import Swarm, Agent

client = Swarm()

my_agent = Agent(
    name="Agent",
    instructions="You are a helpful agent.",
    #model="claude-3-5-sonnet-20240620",
    model="groq/llama-3.3-70b-versatile",
    max_tokens=1024
)


def pretty_print_messages(messages):
    for message in messages:
        if message["content"] is None:
            continue
        print(f"{message['sender']}: {message['content']}")


messages = []
agent = my_agent
while True:
    user_input = input("> ")
    messages.append({"role": "user", "content": user_input})

    response = client.run(agent=agent, messages=messages)
    messages = response.messages
    agent = response.agent
    pretty_print_messages(messages)
