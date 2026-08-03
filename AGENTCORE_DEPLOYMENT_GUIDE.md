# AWS DevOps Agent MCP → Bedrock AgentCore Runtime

**Step-by-step deployment guide**

This document explains everything we implemented to take the AWS sample DevOps Agent MCP server from a local Cursor integration to a **hosted MCP runtime on Amazon Bedrock AgentCore**.

Written for beginners — no prior AgentCore experience required.

---

## Table of contents

1. [What we built](#1-what-we-built)
2. [Architecture](#2-architecture)
3. [Prerequisites](#3-prerequisites)
4. [Step 1 — Clone the sample project](#4-step-1--clone-the-sample-project)
5. [Step 2 — Code changes we made](#5-step-2--code-changes-we-made)
6. [Step 3 — Run locally (HTTP mode)](#6-step-3--run-locally-http-mode)
7. [Step 4 — Dockerize the MCP server](#7-step-4--dockerize-the-mcp-server)
8. [Step 5 — Build ARM64 image and push to ECR](#8-step-5--build-arm64-image-and-push-to-ecr)
9. [Step 6 — Create AgentCore Runtime](#9-step-6--create-agentcore-runtime)
10. [Step 7 — IAM permissions](#10-step-7--iam-permissions)
11. [Step 8 — Test in AWS Console playground](#11-step-8--test-in-aws-console-playground)
12. [Step 9 — Test from your laptop (](#12-step-9--test-from-your-laptop-test_remote_mcppy)`test_remote_mcp.py`[)](#12-step-9--test-from-your-laptop-test_remote_mcppy)
13. [Troubleshooting](#13-troubleshooting)
14. [What’s next](#14-whats-next)

---



## 1. What we built


| Before                                   | After                                      |
| ---------------------------------------- | ------------------------------------------ |
| MCP server ran on your laptop (stdio)    | MCP server runs in AWS (AgentCore Runtime) |
| Only Cursor / local tools could use it   | Any IAM-authorized client can invoke it    |
| `aws-devops-agent mcp` over stdin/stdout | HTTP MCP on `0.0.0.0:8000/mcp`             |


**Important:** We did **not** deploy the AWS DevOps Agent service itself. That is already a managed AWS service. We deployed the **MCP adapter** that exposes DevOps Agent APIs (`chat`, `investigate`, `list_services`, etc.) as 22 MCP tools.

**Our runtime name:** `DevopsAgentMcpTest`  
**Example ARN:** `arn:aws:bedrock-agentcore:us-east-1:058029412961:runtime/DevopsAgentMcpTest-Q1Am9rGGut`

---



## 2. Architecture

```text
┌──────────────────────────────────────────────────────────────────┐
│  Your laptop / other clients                                     │
│  • AWS Console Playground                                        │
│  • scripts/test_remote_mcp.py (IAM SigV4)                        │
│  • Cursor (local stdio — separate from cloud deploy)             │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTPS + IAM (SigV4)
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  Amazon Bedrock AgentCore Runtime                                │
│  Protocol: MCP                                                   │
│  Container: ECR image (ARM64)                                    │
│  Endpoint: /mcp on port 8000                                     │
└────────────────────────────┬─────────────────────────────────────┘
                             │ boto3 (AWS APIs)
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  AWS DevOps Agent (managed service)                              │
│  AgentSpace → investigations, chat, recommendations              │
└──────────────────────────────────────────────────────────────────┘
```



### Local vs cloud


| Mode                  | Transport                 | Used for                   |
| --------------------- | ------------------------- | -------------------------- |
| **Local (Cursor)**    | stdio                     | Development in IDE         |
| **Cloud (AgentCore)** | streamable-http on `/mcp` | Production / shared access |


---



## 3. Prerequisites

Before starting, you need:

- [ ] **Python 3.10+**
- [ ] **AWS account** with DevOps Agent enabled
- [ ] **AWS CLI v2** configured (`aws configure` or SSO)
- [ ] **Docker** with `buildx` (for ARM64 builds)
- [ ] **IAM permissions:**
  - `AIDevOpsAgentFullAccess` (your user) — for DevOps Agent APIs
  - ECR push permissions
  - AgentCore runtime create/deploy permissions
- [ ] **Region:** `us-east-1` (DevOps Agent + AgentCore)

Verify AWS CLI:

```bash
aws --version
aws sts get-caller-identity
```

---



## 4. Step 1 — Clone the sample project



### Option A — Clone from AWS Samples (recommended)

```bash
git clone https://github.com/aws-samples/sample-aws-devops-agent-acp-mcp
cd sample-aws-devops-agent-acp-mcp
```



### Option B — Use our working copy

```bash
cd ~/Desktop/MAIN/poc-aws-devops-agent/sample-aws-devops-agent-acp-mcp
```



### Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[mcp,dev]'
```



### Verify install

```bash
aws-devops-agent --version
which aws-devops-agent
```



### Connect to Cursor (local stdio — optional)

Add to Cursor MCP config:

```json
{
  "mcpServers": {
    "aws-devops-agent": {
      "command": "aws-devops-agent",
      "args": ["mcp"],
      "env": {
        "DEVOPS_AGENT_REGION": "us-east-1"
      }
    }
  }
}
```

This local setup is **separate** from the AgentCore deployment.

---



## 5. Step 2 — Code changes we made

The original sample only supported **stdio** MCP (for Cursor). AgentCore requires **HTTP streamable MCP** on port **8000** at path `/mcp`.

### Files added or modified


| File                                      | What changed                                     |
| ----------------------------------------- | ------------------------------------------------ |
| `src/aws_devops_agent/mcp_server.py`      | HTTP transport, AgentCore settings               |
| `src/aws_devops_agent/mcp_http_server.py` | **New** — entry point for Docker/AgentCore       |
| `setup.cfg`                               | Added `aws-devops-agent-mcp-http` console script |
| `Dockerfile`                              | **New** — ARM64 container image                  |
| `scripts/test_remote_mcp.py`              | **New** — test deployed runtime with IAM         |




### 5.1 `mcp_server.py` — HTTP mode for AgentCore

**Why:** Cursor uses stdio; AgentCore uses HTTP on `/mcp`.

Key changes:

1. **FastMCP** configured for HTTP when `MCP_TRANSPORT=http`:
  - `host=0.0.0.0` (listen on all interfaces inside container)
  - `port=8000`
  - `stateless_http=True` (AWS recommendation for basic MCP)
  - `streamable_http_path="/mcp"`
2. `main()` switches transport by environment variable:
  - `MCP_TRANSPORT=stdio` → local Cursor (default)
  - `MCP_TRANSPORT=http` → AgentCore (streamable-http)
3. **SIGTERM handler** for graceful container shutdown
4. `transport_security = None` in HTTP mode so AgentCore internal routing is not blocked

```python
# Simplified view of main()
def main():
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    if transport == "http":
        mcp.settings.host = os.getenv("MCP_HOST", "0.0.0.0")
        mcp.settings.port = int(os.getenv("MCP_PORT", "8000"))
        mcp.settings.stateless_http = True
        mcp.settings.transport_security = None
        signal.signal(signal.SIGTERM, _shutdown)
        mcp.run(transport="streamable-http")
    else:
        mcp.run()  # stdio for Cursor
```



### 5.2 `mcp_http_server.py` — Docker entry point

Small wrapper that sets `MCP_TRANSPORT=http` and calls `main()`:

```python
import os
os.environ.setdefault("MCP_TRANSPORT", "http")
from aws_devops_agent.mcp_server import main

if __name__ == "__main__":
    main()
```



### 5.3 `setup.cfg` — new CLI command

```ini
aws-devops-agent-mcp-http = aws_devops_agent.mcp_http_server:main
```

Run locally in HTTP mode:

```bash
aws-devops-agent-mcp-http
# or
MCP_TRANSPORT=http python -m aws_devops_agent.mcp_http_server
```

---



## 6. Step 3 — Run locally (HTTP mode)

Test HTTP MCP **before** Docker or AWS.

### Start the server

```bash
source .venv/bin/activate
MCP_TRANSPORT=http MCP_HOST=127.0.0.1 MCP_PORT=8001 \
  python -m aws_devops_agent.mcp_http_server
```

Expected log:

```text
Starting HTTP MCP server on http://127.0.0.1:8001/mcp
INFO:     Uvicorn running on http://127.0.0.1:8001
```

> Use port `8001` if `8000` is already in use.



### Test with curl (initialize)

```bash
curl -s -X POST http://127.0.0.1:8001/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {"name": "local-test", "version": "1.0"}
    }
  }'
```

**Success looks like:** SSE output with `"serverInfo":{"name":"aws-devops-agent",...}`

### Run unit tests

```bash
pytest tests/test_mcp.py -v
```

Expected: **2 passed** (22 tools registered).

---



## 7. Step 4 — Dockerize the MCP server



### Why ARM64?

AgentCore Runtime runs on **AWS Graviton (ARM64)**. x86 images will **not** start.

### `Dockerfile`

```dockerfile
FROM --platform=linux/arm64 python:3.12-slim

WORKDIR /app

COPY setup.py setup.cfg README.md LICENSE.txt ./
COPY src/ ./src/

RUN pip install --no-cache-dir ".[mcp]"

ENV MCP_TRANSPORT=http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000
ENV DEVOPS_AGENT_REGION=us-east-1

EXPOSE 8000

CMD ["python", "-m", "aws_devops_agent.mcp_http_server"]
```



### Dockerfile notes


| Item                     | Why                                                                   |
| ------------------------ | --------------------------------------------------------------------- |
| `--platform=linux/arm64` | Required by AgentCore                                                 |
| Copy `setup.py`          | Pip needs it to install the package (`setup.cfg` alone is not enough) |
| `pip install ".[mcp]"`   | Non-editable install (better for containers)                          |
| `MCP_HOST=0.0.0.0`       | Container must accept traffic from AgentCore load balancer            |
| `MCP_PORT=8000`          | AgentCore MCP contract                                                |
| `DEVOPS_AGENT_REGION`    | Region for DevOps Agent API calls                                     |
| `mcp_http_server` CMD    | Starts HTTP MCP, not stdio                                            |




### Common Docker build error we fixed

```text
ERROR: neither 'setup.py' nor 'pyproject.toml' found
```

**Fix:** Include `setup.py` in `COPY`.

---



## 8. Step 5 — Build ARM64 image and push to ECR



### 8.1 Create ECR repository (one time)

```bash
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export ECR_REPO=devops-agent-mcp

aws ecr create-repository \
  --repository-name $ECR_REPO \
  --region $AWS_REGION
```



### 8.2 Set up buildx (one time)

```bash
docker buildx create --use --name arm-builder 2>/dev/null || docker buildx use arm-builder
```



### 8.3 Build for ARM64

```bash
cd sample-aws-devops-agent-acp-mcp

docker buildx build \
  --platform linux/arm64 \
  -t devops-agent-mcp:latest \
  --load \
  .
```



### 8.4 Login to ECR

```bash
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
```



### 8.5 Tag and push

```bash
docker tag devops-agent-mcp:latest \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest

docker push \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest
```

**Save the full image URI** — you need it when creating the runtime:

```text
058029412961.dkr.ecr.us-east-1.amazonaws.com/devops-agent-mcp:latest
```

---



## 9. Step 6 — Create AgentCore Runtime

Create the runtime in the **AWS Console** (Bedrock → AgentCore → Runtimes) or via CLI.

### Runtime settings we used


| Setting             | Value                |
| ------------------- | -------------------- |
| **Name**            | `DevopsAgentMcpTest` |
| **Protocol**        | **MCP** (not HTTP)   |
| **Container image** | ECR URI from Step 5  |
| **Architecture**    | ARM64 (from image)   |
| **Inbound auth**    | **IAM** (SigV4)      |
| **Endpoint**        | `DEFAULT`            |




### Environment variables (container)


| Variable              | Value       | Purpose                          |
| --------------------- | ----------- | -------------------------------- |
| `MCP_TRANSPORT`       | `http`      | Use HTTP MCP (set in Dockerfile) |
| `MCP_HOST`            | `0.0.0.0`   | Listen on all interfaces         |
| `MCP_PORT`            | `8000`      | AgentCore MCP port               |
| `DEVOPS_AGENT_REGION` | `us-east-1` | DevOps Agent API region          |


Optional:


| Variable                         | Purpose                             |
| -------------------------------- | ----------------------------------- |
| `DEVOPS_AGENT_SPACE_ID`          | Pin a specific AgentSpace           |
| `DEVOPS_AGENT_AUTO_CREATE_SPACE` | `true` to auto-create if none exist |




### Runtime execution role (IAM)

The **runtime role** (not your user) needs permission to call DevOps Agent APIs:

- Attach `AIDevOpsAgentAccessPolicy` or equivalent
- `devopsagent:*` on appropriate resources (scope down in production)



### Wait for READY

After create/update, wait until:

- Runtime status: **READY**
- Endpoint `DEFAULT`: **READY**
- Health check: **passing**

Check CloudWatch logs:

```text
/aws/bedrock-agentcore/runtimes/<runtime-id>-DEFAULT/
```

Look for:

```text
Starting HTTP MCP server on http://0.0.0.0:8000/mcp
```

---



## 10. Step 7 — IAM permissions

Two different IAM contexts:


| Who                        | Purpose                                |
| -------------------------- | -------------------------------------- |
| **Runtime execution role** | Container → DevOps Agent APIs          |
| **Your IAM user**          | Your laptop → invoke AgentCore runtime |




### 10.1 Runtime execution role

Allows the **container** to call AWS DevOps Agent.

### 10.2 Your user — invoke from CLI / script

To run `test_remote_mcp.py`, your user needs `bedrock-agentcore:InvokeAgentRuntime` on **both**:

1. The runtime ARN
2. The **runtime endpoint** ARN (easy to miss)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeDevopsAgentMcpRuntime",
      "Effect": "Allow",
      "Action": "bedrock-agentcore:InvokeAgentRuntime",
      "Resource": [
        "arn:aws:bedrock-agentcore:us-east-1:058029412961:runtime/DevopsAgentMcpTest-Q1Am9rGGut",
        "arn:aws:bedrock-agentcore:us-east-1:058029412961:runtime/DevopsAgentMcpTest-Q1Am9rGGut/runtime-endpoint/DEFAULT"
      ]
    }
  ]
}
```

Or wildcard:

```json
"Resource": "arn:aws:bedrock-agentcore:us-east-1:058029412961:runtime/DevopsAgentMcpTest-Q1Am9rGGut*"
```



### Why console worked before CLI

The **AWS Console playground** uses the console’s own IAM session (broader permissions). Your **local CLI** uses `saksham.verma@tothenew.com`, which needed the endpoint ARN added to the policy.

---



## 11. Step 8 — Test in AWS Console playground

Open: **Bedrock → AgentCore → Runtimes → DevopsAgentMcpTest → Playground**

### Wrong input (causes 404)

```json
{"prompt": "Hello"}
```

That is **HTTP agent** format. MCP runtime does **not** understand `prompt`.

### Correct input — MCP initialize

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {
      "name": "console-test",
      "version": "1.0"
    }
  }
}
```



### Success response

```text
event: message
data: {"jsonrpc":"2.0","id":1,"result":{
  "protocolVersion":"2024-11-05",
  "serverInfo":{"name":"aws-devops-agent","version":"1.29.0"},
  ...
}}
```



### Next — list tools (same session)

Reuse the **Session ID** from the playground, then send:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}
```

You should see all **22 tools**.

### Call a tool — example `list_agent_spaces`

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "list_agent_spaces",
    "arguments": {}
  }
}
```

---



## 12. Step 9 — Test from your laptop (`test_remote_mcp.py`)



### Why run this if the console already works?


| Reason                                          | Explanation                           |
| ----------------------------------------------- | ------------------------------------- |
| Verify **your IAM user** can invoke the runtime | Console may use different permissions |
| **Automate** testing                            | Repeatable without clicking           |
| **Learn the API**                               | Same pattern production apps use      |


You are **not** running the server locally. The script is a **remote client** calling AWS.

### Run the test

```bash
source .venv/bin/activate

export AGENT_ARN="arn:aws:bedrock-agentcore:us-east-1:058029412961:runtime/DevopsAgentMcpTest-Q1Am9rGGut"
export AWS_REGION="us-east-1"

python scripts/test_remote_mcp.py
```



### Expected output

```text
Agent ARN:          arn:aws:bedrock-agentcore:us-east-1:058029412961:runtime/DevopsAgentMcpTest-Q1Am9rGGut
Region:             us-east-1
Qualifier:          DEFAULT
Runtime session ID: <uuid>
Auth:               IAM (SigV4 via default AWS credential chain)

Connected to: aws-devops-agent v1.29.0
MCP session ID: <uuid>
Tools available: 22
  - list_services
  - get_service
  - list_agent_spaces
  ...
```



### How auth works

- **Inbound auth = IAM** → script uses `boto3.invoke_agent_runtime` (SigV4)
- **No bearer token** required
- Uses credentials from `aws configure` / SSO / environment

---



## 13. Troubleshooting



### 404 in console playground


| Cause                            | Fix                                                 |
| -------------------------------- | --------------------------------------------------- |
| Sent `{"prompt": "..."}`         | Use MCP JSON-RPC (`initialize`, `tools/list`, etc.) |
| Runtime protocol is HTTP not MCP | Recreate runtime with protocol **MCP**              |
| Wrong port/path in container     | Must be `0.0.0.0:8000/mcp`                          |




### Docker build: `setup.py not found`

Copy `setup.py` in Dockerfile:

```dockerfile
COPY setup.py setup.cfg README.md LICENSE.txt ./
```



### Container won’t start on AgentCore


| Cause       | Fix                                    |
| ----------- | -------------------------------------- |
| x86 image   | Rebuild with `--platform linux/arm64`  |
| Wrong CMD   | Use `mcp_http_server`, not stdio `mcp` |
| Missing env | Set `MCP_TRANSPORT=http`               |




### `AccessDeniedException` on `test_remote_mcp.py`


| Cause                              | Fix                                            |
| ---------------------------------- | ---------------------------------------------- |
| Missing endpoint ARN in IAM policy | Add `.../runtime-endpoint/DEFAULT` to Resource |
| Wrong user/credentials             | Run `aws sts get-caller-identity`              |




### `Session terminated` in old test script


| Cause                     | Fix                              |
| ------------------------- | -------------------------------- |
| Placeholder ARN (`-XXXX`) | Use real ARN from console        |
| Fake bearer token         | Use IAM script (no token needed) |




### `No MCP JSON-RPC messages` on notifications


| Cause                                          | Fix                                                |
| ---------------------------------------------- | -------------------------------------------------- |
| `notifications/initialized` returns empty body | Expected — script updated to allow empty responses |


---



## 14. What’s next


| Step                        | Description                                                    |
| --------------------------- | -------------------------------------------------------------- |
| **AgentCore Harness**       | Bedrock-managed agent that uses your MCP as `remote_mcp` tools |
| **MCP Inspector**           | Visual remote testing: `npx @modelcontextprotocol/inspector`   |
| **CI/CD**                   | Auto-build ARM64 image → push ECR → update runtime on merge    |
| **Production hardening**    | Least-privilege IAM, VPC networking, CloudWatch alarms         |
| **Connect Cursor remotely** | Point MCP client at AgentCore URL with IAM/OAuth               |


---



## Quick reference — commands cheat sheet

```bash
# Local HTTP test
MCP_TRANSPORT=http MCP_HOST=127.0.0.1 MCP_PORT=8001 python -m aws_devops_agent.mcp_http_server

# Unit tests
pytest tests/test_mcp.py -v

# Docker build (ARM64)
docker buildx build --platform linux/arm64 -t devops-agent-mcp:latest --load .

# Push ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com
docker tag devops-agent-mcp:latest <account>.dkr.ecr.us-east-1.amazonaws.com/devops-agent-mcp:latest
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/devops-agent-mcp:latest

# Test deployed runtime (IAM)
export AGENT_ARN="arn:aws:bedrock-agentcore:us-east-1:<account>:runtime/DevopsAgentMcpTest-<suffix>"
python scripts/test_remote_mcp.py
```

---



## Summary timeline

```text
1. Clone sample-aws-devops-agent-acp-mcp
2. Add HTTP transport (mcp_server.py, mcp_http_server.py)
3. Test locally on :8001/mcp
4. Write Dockerfile (ARM64 + setup.py)
5. buildx build → push ECR
6. Create AgentCore Runtime (MCP, IAM, env vars)
7. Fix IAM (runtime + runtime-endpoint/DEFAULT)
8. Test console playground (initialize JSON-RPC)
9. Test test_remote_mcp.py from laptop
✅ DevOps Agent MCP live on AgentCore
```

---



## References

- [AWS DevOps Agent User Guide](https://docs.aws.amazon.com/devopsagent/latest/userguide/)
- [Deploy MCP servers in AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html)
- [Sample repo](https://github.com/aws-samples/sample-aws-devops-agent-acp-mcp)
- [AgentCore Runtime protocols](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime.html)

---

*Document version: 1.0 — reflects deployment completed March 2026*