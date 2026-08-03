import boto3
import os
import json

client = boto3.client("devops-agent")

# Agar env me AgentSpace hai to use use karo
agent_space_id = os.getenv("DEVOPS_AGENT_SPACE_ID")

if not agent_space_id:
    spaces = client.list_agent_spaces()
    print("Available Agent Spaces:")
    print(json.dumps(spaces, indent=2, default=str))

    # First AgentSpace pick kar lo
    agent_space_id = spaces["agentSpaces"][0]["agentSpaceId"]

user_id = os.getenv("DEVOPS_AGENT_USER_ID")

print(f"\nAgentSpace: {agent_space_id}")
print(f"User: {user_id}\n")

resp = client.list_chats(
    agentSpaceId=agent_space_id,
    userId=user_id,
)

print(json.dumps(resp, indent=2, default=str))



# import boto3
# import json

# client = boto3.client("devops-agent")

# resp = client.list_agent_spaces()

# print(json.dumps(resp, indent=2, default=str))