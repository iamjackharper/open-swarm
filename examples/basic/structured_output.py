from swarm import Swarm, Agent
from pydantic import BaseModel

client = Swarm()

def transfer_to_agent_b():
    """Transfer task to calendar manager agent"""
    return agent_b

class CalendarEvent(BaseModel):
    name: str
    date: str
    participants: list[str]


agent_a = Agent(
    name="Agent A",
    instructions="You are a helpful agent.",
    functions=[transfer_to_agent_b],
    model="claude-3-5-sonnet-20240620" # Optional, defaults to gpt-4o
)

agent_b = Agent(
    name="Agent B",
    instructions="Only speak in Json format.",
    response_format=CalendarEvent,
    temperature=0.5,
    model="groq/llama-3.3-70b-versatile"
)

response = client.run(
    agent=agent_a,
    messages=[{"role": "user", "content": "Set me up a meeting with John and Jane on the 21st of March."}],
)

print(response.messages[-1]["content"])