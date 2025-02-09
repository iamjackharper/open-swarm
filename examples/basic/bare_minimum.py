from swarm import Swarm, Agent

client = Swarm()  

agent = Agent(
    name="Agent",
    instructions="You are a helpful agent.",
    #model="claude-3-5-sonnet-20240620",  
    #temperature=0.5,
    #max_completions_tokens=4096
)

messages = [{"role": "user", "content": "Hi! How are you?"}]

response = client.run(agent, messages, stream=True)
print(response.messages[-1]["content"])