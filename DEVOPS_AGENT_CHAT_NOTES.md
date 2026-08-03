# AWS DevOps Agent Chat — Testing Notes

**Agent Space:** `8ccbf086-ed2f-4d03-b626-2a811d90313c`  
**Region:** `us-east-1`

## Goal

Local terminal ACP chat (`python acp_chat.py "..."`) ko run karna, VS Code MCP configure karna, aur understand karna ki chat history web UI mein kab dikhegi.

## What we tried and what happened

| Test | Result | Conclusion |
| --- | --- | --- |
| Ran ACP without `DEVOPS_AGENT_USER_ID` | Failed initially because the sample treated the legacy ID as required. | Sample behavior was outdated. |
| Set `DEVOPS_AGENT_USER_ID={your_username}` | Failed. The placeholder was sent literally. | Placeholder must never be used as a real value. |
| Set `DEVOPS_AGENT_USER_ID=saksham-verma` | Worked with the earlier sample. | This value matches the old SDK format. |
| Set `DEVOPS_AGENT_USER_ID=saksham.verma@tothenew.com` | Failed in the earlier sample. | The old `userId` pattern does not allow `@`. |
| Removed `DEVOPS_AGENT_USER_ID` after the fix | ACP chat worked. | The service uses the AWS-authenticated identity; this environment variable is not needed. |
| Ran `aws devops-agent list-chats ...` | Terminal chats appeared, including **Hello from terminal**. | History is successfully persisted by the DevOps Agent service. |
| Looked for the same terminal chats in the web UI | They did not appear in the browser's Chats list. | Web UI history is scoped to the web-app authenticated user, not merely the Agent Space. |

## Important identity behavior

`DEVOPS_AGENT_USER_ID` is a legacy request field. AWS DevOps Agent resolves the effective chat identity from the authenticated request/session.

- Local ACP uses the AWS credentials configured for the terminal/CLI.
- The web UI uses its browser authentication session (IAM admin access, IAM Identity Center, or external IdP).
- Same Agent Space means the same monitored resources and configuration; it does **not** make all users share private chat history.
- Setting an email/IAM username in `DEVOPS_AGENT_USER_ID` cannot force terminal chats into the web UI user's chat list.

## Verified terminal command

```bash
source .venv/bin/activate

export DEVOPS_AGENT_SPACE_ID="8ccbf086-ed2f-4d03-b626-2a811d90313c"
export DEVOPS_AGENT_REGION="us-east-1"
unset DEVOPS_AGENT_USER_ID

python acp_chat.py "hello from terminal"
```

Verify that the service recorded the chat:

```bash
aws devops-agent list-chats \
  --agent-space-id 8ccbf086-ed2f-4d03-b626-2a811d90313c \
  --region us-east-1 \
  --output json
```

Observed result: the list included a chat with summary **Hello from terminal**.

## Changes made in this repository

1. `setup.cfg`
   - Pinned the MCP dependency to `mcp[cli]>=1.2.0,<2.0.0`.
   - Reason: `mcp 2.0.0` removed `mcp.server.fastmcp`, which this sample imports.

2. `src/aws_devops_agent/acp_server.py`
   - ACP no longer passes the legacy `userId` to `CreateChat` or `SendMessage`.
   - This allows terminal chat to work with no `DEVOPS_AGENT_USER_ID` set.

3. `src/aws_devops_agent/mcp_server.py`
   - MCP chat calls also no longer send the legacy `userId`.

4. `.vscode/mcp.json`
   - Configured VS Code to use the official remote DevOps Agent MCP endpoint.
   - It prompts for a web-app access token rather than storing one in source control.

## VS Code and web UI history

To create chats using the same web-app user identity, use the remote MCP configuration:

1. In the DevOps Agent web app, go to **Settings → Access Tokens**.
2. Create a token with client type **human** and scope **operate**.
3. In VS Code run **MCP: List Servers**, restart `aws-devops-agent`, and paste the token when prompted.

Chats created through that remote MCP connection are the supported approach for IDE usage with the web-app identity. The local `acp_chat.py` sample is a direct AWS API/ACP integration and does not use the browser's web-app session.

## Audit and security

Users cannot browse every other user's private chat sidebar. For administrator auditing, use AWS CloudTrail:

- Event source: `aidevops.amazonaws.com`
- Event names: `CreateChat`, `SendMessage`

CloudTrail can identify who made a request, when it was made, and its source IP. Do not rely on the user-facing web UI as a global audit log.

## Useful references

- [CreateChat API](https://docs.aws.amazon.com/devopsagent/latest/APIReference/API_CreateChat.html)
- [Remote MCP connection](https://docs.aws.amazon.com/devopsagent/latest/userguide/accessing-devops-agent-connect-to-devops-agent-remote-servers.html)
- [DevOps Agent security and audit logging](https://docs.aws.amazon.com/devopsagent/latest/userguide/aws-devops-agent-security.html)
