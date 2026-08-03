# Cursor ↔ AgentCore Runtime Integration

Connect **Cursor** to your **live** DevOps Agent MCP on Amazon Bedrock AgentCore.

---

## How it works

```text
┌─────────────┐   stdio MCP    ┌──────────────────────────┐   IAM SigV4    ┌─────────────────┐
│   Cursor    │ ─────────────► │ cursor_agentcore_bridge  │ ─────────────► │ AgentCore       │
│   (IDE)     │ ◄───────────── │ (local Python process)   │ ◄───────────── │ Runtime (AWS)   │
└─────────────┘                └──────────────────────────┘                └─────────────────┘
```

Cursor cannot sign **IAM (SigV4)** requests itself. The **bridge script** runs locally, signs calls with your AWS credentials (`aws configure` / SSO), and forwards MCP tool calls to AgentCore.

---

## Prerequisites

- [x] AgentCore runtime deployed and **READY** (see [AGENTCORE_DEPLOYMENT_GUIDE.md](AGENTCORE_DEPLOYMENT_GUIDE.md))
- [x] Runtime inbound auth = **IAM**
- [x] IAM user/role with `bedrock-agentcore:InvokeAgentRuntime` on:
  - `arn:aws:bedrock-agentcore:us-east-1:ACCOUNT:runtime/DevopsAgentMcpTest-XXXX`
  - `arn:aws:bedrock-agentcore:us-east-1:ACCOUNT:runtime/DevopsAgentMcpTest-XXXX/runtime-endpoint/DEFAULT`
- [x] AWS credentials configured locally (`aws sts get-caller-identity`)
- [x] Python venv with project installed: `pip install -e '.[mcp]'`

Verify remote access:

```bash
export AGENT_ARN="arn:aws:bedrock-agentcore:us-east-1:058029412961:runtime/DevopsAgentMcpTest-Q1Am9rGGut"
python scripts/test_remote_mcp.py
```

---

## Step 1 — Configure Cursor MCP

### Option A — Project-level (recommended for this repo)

Create or edit **`.cursor/mcp.json`** in the project root:

```json
{
  "mcpServers": {
    "aws-devops-agent-agentcore": {
      "command": "/home/saksham-verma/Desktop/MAIN/poc-aws-devops-agent/sample-aws-devops-agent-acp-mcp/.venv/bin/python",
      "args": [
        "/home/saksham-verma/Desktop/MAIN/poc-aws-devops-agent/sample-aws-devops-agent-acp-mcp/scripts/cursor_agentcore_bridge.py"
      ],
      "env": {
        "AGENT_ARN": "arn:aws:bedrock-agentcore:us-east-1:058029412961:runtime/DevopsAgentMcpTest-Q1Am9rGGut",
        "AWS_REGION": "us-east-1"
      }
    }
  }
}
```

> Replace paths with your actual machine paths.

### Option B — User-level (all Cursor projects)

Edit **`~/.cursor/mcp.json`** with the same `mcpServers` block.

---

## Step 2 — Reload MCP in Cursor

1. Open **Cursor Settings** → **MCP** (or Command Palette → "MCP: List Servers")
2. Restart / reload MCP servers
3. Confirm **`aws-devops-agent-agentcore`** shows **connected** (green)

On first connect, stderr should show:

```text
AgentCore bridge ready: 22 tools via arn:aws:bedrock-agentcore:...
```

---

## Step 3 — Use it in chat

In Cursor Agent chat, the DevOps Agent tools are available. Examples:

- *"Use list_agent_spaces to show my AgentSpaces"*
- *"Use chat to ask: what alarms are firing in my account?"*
- *"Use investigate to look into ECS 503 errors on checkout-service"*

Same 22 tools as local MCP — but routed through **AgentCore**.

---

## Two ways to use DevOps Agent in Cursor

| Mode | Config | Path to AWS |
|------|--------|-------------|
| **Local stdio** (original) | `aws-devops-agent mcp` | Laptop → DevOps Agent APIs directly |
| **AgentCore bridge** (this guide) | `cursor_agentcore_bridge.py` | Laptop → AgentCore Runtime → DevOps Agent APIs |

Use **AgentCore bridge** when you want Cursor to hit the **same deployed runtime** as production/other teams.

Use **local stdio** for fastest iteration during development (no AgentCore invoke latency).

### Local stdio config (reference)

```json
{
  "mcpServers": {
    "aws-devops-agent-local": {
      "command": "/path/to/.venv/bin/aws-devops-agent",
      "args": ["mcp"],
      "env": {
        "DEVOPS_AGENT_REGION": "us-east-1"
      }
    }
  }
}
```

You can run **both** servers in Cursor at the same time (different names).

---

## Troubleshooting

### MCP server shows red / failed to start

| Check | Action |
|-------|--------|
| Python path wrong | Use absolute path to `.venv/bin/python` |
| Script path wrong | Use absolute path to `cursor_agentcore_bridge.py` |
| Missing deps | `pip install -e '.[mcp]'` in venv |
| `ModuleNotFoundError: agentcore_mcp_client` | Run bridge from repo with `scripts/` on path, or: `"args": ["-c", "import sys; sys.path.insert(0, '.../scripts'); ..."]` |

**Fix for import path:** run via module from repo root:

```json
{
  "command": "/path/to/.venv/bin/python",
  "args": ["scripts/cursor_agentcore_bridge.py"],
  "cwd": "/path/to/aws-devops-agent-acp-mcp",
  "env": { "AGENT_ARN": "...", "AWS_REGION": "us-east-1" }
}
```

Add `"cwd"` if Cursor supports it; otherwise set `PYTHONPATH`:

```json
"env": {
  "AGENT_ARN": "...",
  "AWS_REGION": "us-east-1",
  "PYTHONPATH": "/path/to/aws-devops-agent-acp-mcp/scripts"
}
```

### AccessDeniedException

Same IAM fix as [AGENTCORE_DEPLOYMENT_GUIDE.md](AGENTCORE_DEPLOYMENT_GUIDE.md) — include **runtime-endpoint/DEFAULT** in policy.

### Tools work in console but not in Cursor

1. Run `python scripts/test_remote_mcp.py` — if this fails, fix IAM/credentials first
2. Check Cursor MCP logs for bridge stderr
3. Reload MCP servers

### `chat` fails validation / tool shows a single `kwargs` parameter

The bridge forwards each remote tool's `inputSchema` from AgentCore (e.g. `chat` expects `message`, not `kwargs`). Verify with:

```bash
python scripts/cursor_agentcore_bridge.py --check-tools
```

Reload MCP servers in Cursor after updating the bridge script.

### Slow responses

AgentCore adds network hop + cold start. Investigations still take 5–8 minutes by design. Use `chat` for quick answers.

---

## Alternative: OAuth instead of IAM (advanced)

If you change runtime inbound auth to **OAuth/Cognito**, Cursor can connect **directly** via HTTP (no bridge):

```json
{
  "mcpServers": {
    "aws-devops-agent-agentcore": {
      "url": "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A058029412961%3Aruntime%2FDevopsAgentMcpTest-Q1Am9rGGut/invocations?qualifier=DEFAULT",
      "headers": {
        "Authorization": "Bearer YOUR_COGNITO_ACCESS_TOKEN"
      }
    }
  }
}
```

Tokens expire — IAM bridge is simpler for daily Cursor use.

---

## Related docs

- [AGENTCORE_DEPLOYMENT_GUIDE.md](AGENTCORE_DEPLOYMENT_GUIDE.md) — deploy runtime
- [scripts/test_remote_mcp.py](scripts/test_remote_mcp.py) — test IAM invoke
- [main_readme.md](main_readme.md) — local MCP setup
