# import boto3

# client = boto3.client("devops-agent")

# print(client.meta.service_model.operation_names)


# import boto3
# import json
# import os

# client = boto3.client("devops-agent")

# resp = client.list_executions(
#     agentSpaceId=os.getenv("DEVOPS_AGENT_SPACE_ID")
# )

# print(json.dumps(resp, indent=2, default=str))



# import boto3
# import json
# import os

# client = boto3.client("devops-agent")

# resp = client.list_chats(
#     agentSpaceId=os.environ["DEVOPS_AGENT_SPACE_ID"],
#     userId=os.environ["DEVOPS_AGENT_USER_ID"]
# )

# print(json.dumps(resp, indent=2, default=str))

import boto3

client = boto3.client("devops-agent")

print("\n".join(sorted(client.meta.service_model.operation_names)))


# get chat



# import boto3
# import json
# import os

# client = boto3.client("devops-agent")

# resp = client.list_chats(
#     agentSpaceId=os.environ["DEVOPS_AGENT_SPACE_ID"],
#     userId=os.environ["DEVOPS_AGENT_USER_ID"],
# )

# print(json.dumps(resp, indent=2, default=str))


# import boto3
# import json

# client = boto3.client("devops-agent")

# # print(client.get_account_usage())
# print(client.get_agent_space(
#     agentSpaceId="8ccbf086-ed2f-4d03-b626-2a811d90313c"
# ))


# import boto3
# import json
# import os

# client = boto3.client("devops-agent")

# resp = client.list_chats(
#     agentSpaceId=os.environ["DEVOPS_AGENT_SPACE_ID"]
# )

# print(json.dumps(resp, indent=2, default=str))

# import boto3

# client = boto3.client("devops-agent")

# op = client.meta.service_model.operation_model("ListChats")

# print(op.input_shape.members)