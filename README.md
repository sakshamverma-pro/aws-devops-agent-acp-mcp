# AWS DevOps Agent — Sample ACP & MCP Server

[![License: MIT-0](https://img.shields.io/badge/License-MIT--0-blue.svg)](LICENSE.txt)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-DevOps%20Agent-FF9900?logo=amazonaws&logoColor=white)

Sample **ACP client**, **ACP server**, and **MCP server** for the [AWS DevOps Agent](https://docs.aws.amazon.com/devopsagent/latest/userguide/). Use this repo to integrate operational intelligence into IDEs and agents — locally with Cursor, or in the cloud on **Amazon Bedrock AgentCore**.

**Start here** → pick the guide that matches what you want to do.

---

## Quick navigation

| I want to… | Read this |
|------------|-----------|
| Install, configure, and use the sample locally | [main_readme.md](main_readme.md) |
| Deploy the MCP server to **Bedrock AgentCore Runtime** | [AGENTCORE_DEPLOYMENT_GUIDE.md](AGENTCORE_DEPLOYMENT_GUIDE.md) |
| Set up AWS credentials for AI tools | [setup.md](setup.md) |
| Connect **Kiro** (ACP or MCP) | [kiro-power/KIRO_QUICKSTART.md](kiro-power/KIRO_QUICKSTART.md) |
| Connect **Claude Code** | [CLAUDE.md](CLAUDE.md) |
| Understand security controls | [TOOL_SECURITY.md](TOOL_SECURITY.md) |

---

## Documentation index

### Getting started

| Document | Description |
|----------|-------------|
| [main_readme.md](main_readme.md) | **Primary project guide** — prerequisites, quick start, CLI modes, MCP tools (22), workflow patterns, environment variables, troubleshooting, development |
| [setup.md](setup.md) | AWS CLI install, `aws login`, Agent Toolkit setup, and credential verification for AI coding tools |
| [AGENTCORE_DEPLOYMENT_GUIDE.md](AGENTCORE_DEPLOYMENT_GUIDE.md) | **End-to-end AgentCore deploy** — code changes, Docker (ARM64), ECR, runtime config, IAM, console + CLI testing |

### IDE & agent integrations

| Document | Description |
|----------|-------------|
| [kiro-power/KIRO_QUICKSTART.md](kiro-power/KIRO_QUICKSTART.md) | Step-by-step Kiro setup — ACP path (recommended) and MCP fallback |
| [kiro-power/POWER.md](kiro-power/POWER.md) | Kiro Power / agent behavior — incident triggers, streaming updates, workflow guidance |
| [CLAUDE.md](CLAUDE.md) | Claude Code MCP integration — `claude mcp add`, config, and usage patterns |

### AWS DevOps Agent skills & references

| Document | Description |
|----------|-------------|
| [aws-devops-agent/SKILL.md](aws-devops-agent/SKILL.md) | Agent skill for orchestrating investigations, cost analysis, architecture review, and remediation |
| [aws-devops-agent/references/ONBOARDING.md](aws-devops-agent/references/ONBOARDING.md) | IAM policies, AgentSpace setup, and account association for DevOps Agent |
| [aws-devops-agent/references/WORKFLOWS.md](aws-devops-agent/references/WORKFLOWS.md) | Investigation, chat, discovery, and mitigation workflow patterns |

### Security, contributing & project meta

| Document | Description |
|----------|-------------|
| [TOOL_SECURITY.md](TOOL_SECURITY.md) | MCP/ACP security model — allowlists, validation, approval gates |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute to this sample project |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | Community code of conduct |
| [CHANGELOG.md](CHANGELOG.md) | Version history and release notes |

### Internal / session notes

| Document | Description |
|----------|-------------|
| [DEVOPS_AGENT_CHAT_NOTES.md](DEVOPS_AGENT_CHAT_NOTES.md) | Local ACP chat testing notes, VS Code MCP config, and session behavior observations |

---

## Repo layout (key paths)

```text
sample-aws-devops-agent-acp-mcp/
├── README.md                      ← You are here (documentation index)
├── main_readme.md                 ← Full project README (install & usage)
├── AGENTCORE_DEPLOYMENT_GUIDE.md  ← Deploy MCP to Bedrock AgentCore
├── Dockerfile                     ← ARM64 container for AgentCore
├── scripts/
│   └── test_remote_mcp.py         ← Test deployed runtime (IAM SigV4)
├── src/aws_devops_agent/
│   ├── mcp_server.py              ← MCP server (22 tools)
│   ├── mcp_http_server.py         ← HTTP entry point for AgentCore
│   ├── acp_server.py              ← ACP server
│   └── acp_client.py              ← ACP client SDK
└── aws-devops-agent/              ← Skills & reference docs
```

---

## Common paths

### Local development (Cursor / IDE)

1. [main_readme.md](main_readme.md) → Quick Start  
2. [aws-devops-agent/references/ONBOARDING.md](aws-devops-agent/references/ONBOARDING.md) → IAM & AgentSpace  
3. [TOOL_SECURITY.md](TOOL_SECURITY.md) → Security review  

### Cloud deployment (AgentCore)

1. [AGENTCORE_DEPLOYMENT_GUIDE.md](AGENTCORE_DEPLOYMENT_GUIDE.md) → Full walkthrough  
2. `scripts/test_remote_mcp.py` → Verify IAM invoke from your laptop  

### Incident investigation workflow

1. [aws-devops-agent/references/WORKFLOWS.md](aws-devops-agent/references/WORKFLOWS.md)  
2. [aws-devops-agent/SKILL.md](aws-devops-agent/SKILL.md)  
3. [main_readme.md](main_readme.md) → Workflow Patterns  

---

## License

MIT-0 — see [LICENSE.txt](LICENSE.txt)
