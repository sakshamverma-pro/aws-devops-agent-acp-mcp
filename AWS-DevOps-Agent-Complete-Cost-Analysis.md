# AWS DevOps Agent — Complete Analysis

| Field | Value |
| --- | --- |
| **Related POC** | [AWS-DevOps-Agent-POC-Summary.md](./AWS-DevOps-Agent-POC-Summary.md) |
| **Agent Space (POC)** | `saksham-testing` (`8ccbf086-ed2f-4d03-b626-2a811d90313c`) |
| **Integration** | DevOps Agent via MCP → Cursor; Python scripts via `create_chat` + `send_message` |
| **Document date** | August 5, 2026 |
| **Pricing sources** | [DevOps Agent Pricing](https://aws.amazon.com/devops-agent/pricing/), [AgentCore Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/) |

---

## 1. What AWS DevOps Agent is

AWS DevOps Agent is an **AWS-managed SRE / operations agent** (frontier agent). It investigates production issues, evaluates reliability, and handles on-demand ops questions — across AWS, multicloud, and on-prem (via integrations / MCP).

It is **not**:

- A coding IDE (Cursor / Amazon Q Developer / Kiro)
- An unsupervised infrastructure provisioner
- Free just because you host an MCP wrapper

**Core unit:** **Agent Space** — the boundary for AWS accounts, IAM, integrations, users, and investigation history.

---

## 2. What it can do

| Capability | What it means |
| --- | --- |
| **Chat / on-demand SRE** | Ask live questions: instances, CPU, VPCs, topology, costs, runbooks |
| **Investigations** | Alarm / outage → correlate telemetry, deploys, topology → RCA journal |
| **Mitigations** | Propose remediations; **after human approval**, execute within Agent Space IAM |
| **Evaluations / goals** | Proactive reliability checks (scheduled / goal-based) |
| **Release management** | Release readiness / testing (preview: no additional DevOps Agent charge during preview period) |
| **Learning / skills** | Learns your environment; custom skills / runbooks |
| **Integrations** | CloudWatch, Datadog, Dynatrace, New Relic, Splunk, GitHub, GitLab, Azure DevOps; extend via MCP / A2A |
| **Audit trail** | Immutable investigation journals, recommendations, execution status |

### Failure → fix model

| Stage | Behavior |
| --- | --- |
| Error / incident arrives | Agent **investigates** (telemetry, topology, deploys) |
| Before approval | Gives **RCA + remediation plan** — does **not** auto-fix unsupervised |
| After human approval | Agent **can execute** mitigation steps via AWS APIs within Agent Space IAM |
| Code / pipeline / big infra | Still outside full autonomous fix (human / coding agent / CI-CD) |

### What it cannot / will not do well

- Create a VPC or arbitrary IaC from chat
- Auto-fix without human approval
- Guarantee permanent root-cause cure (may stop bleeding only)
- Commit code or trigger deploys by itself
- Deep host memory / process detail without CloudWatch Agent + SSM permissions

---

## 3. What we proved in our POC

- MCP → Cursor chat connection works
- Live inventory (running EC2, CPU utilization)
- VPC subnet remaining IPs + `healthStatus` (`healthy` if available IPs > 10, else `unhealthy`)
- Single-file Python automation via DevOps Agent APIs (`create_chat` + `send_message`)
- Safety model confirmed: investigate freely; remediations gated by approval

### Scripts delivered

| Script | Purpose |
| --- | --- |
| `get_running_instances.py` | Running EC2 inventory as JSON via DevOps Agent |
| `get_subnet_remaining_ips.py` | Subnet available IPs + health status via DevOps Agent |

---

## 4. DevOps Agent pricing (primary cost)

**Source:** [aws.amazon.com/devops-agent/pricing](https://aws.amazon.com/devops-agent/pricing/)

| Task type | Rate |
| --- | --- |
| Investigations (Incident Response) | **$0.0083 per agent-second** |
| Evaluations (Site Reliability) | **$0.0083 per agent-second** |
| On-demand SRE tasks (Chat and Custom SRE Agents) | **$0.0083 per agent-second** |

**Rough conversions:**

- ≈ **$0.498 per agent-minute**
- ≈ **$29.88 per agent-hour**

### Billing rules

- Pay only for **active** agent work (idle / waiting = $0)
- No upfront commitment
- Connected AWS services (e.g. CloudWatch Logs Insights, traces) billed **separately** at their own rates

### Free trial (new DevOps Agent customers)

Starting with first operational task after GA, **2 months**, each month up to:

| Limit | Amount |
| --- | --- |
| Agent Spaces | 10 |
| Investigations | 20 hours |
| Evaluations | 15 hours |
| On-demand SRE (chat) | 20 hours |

Usage beyond limits / after trial = standard pay-as-you-go.

### AWS Support credits (offset DevOps Agent usage)

Credits = % of **prior month’s AWS Support charge**; expire end of month if unused.

| Support plan | Credit rate |
| --- | --- |
| Unified Operations | **100%** |
| Enterprise Support | **75%** |
| Business Support+ | **30%** |

**Examples (from AWS pricing page):**

| Support spend | Plan | Monthly DevOps Agent credit |
| --- | --- | --- |
| $1,000 | Business Support+ (30%) | **$300** |
| $10,000 | Enterprise (75%) | **$7,500** |
| $100,000 | Unified Operations (100%) | **$100,000** |

### Official AWS cost examples

| Scenario | Approx. monthly charge |
| --- | --- |
| 10 investigations × 8 min | **~$39.84** |
| 80 investigations × 8 min + 100 chats × 30s | **~$343.62** |
| Enterprise: 500 incidents + 40 evals + 30 custom agents | **~$2,365.50** |
| Daily custom report × 2 min × 30 days | **~$29.88** |

### POC-scale rough costs (before credits / trial)

| Activity | Rough agent time | Rough cost |
| --- | --- | --- |
| Chat: list instances / subnets (~1 min) | ~60s | ~$0.50 |
| Full investigation (typical ~5–8 min) | 300–480s | ~$2.50–$4.00 |

Always verify with account usage APIs / Cost Explorer / AWS Budgets.

---

## 5. Deploying DevOps Agent MCP on Amazon Bedrock AgentCore

### Critical cost split (do not conflate)

```
Cursor / other agents / automation
              │
              ▼
┌─────────────────────────────────┐
│  MCP server (connector)         │  ← local Cursor OR AgentCore Runtime
│  create_chat / send_message     │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  AWS DevOps Agent APIs          │  ← ALWAYS billed per agent-second
│  Agent Space + AWS ops work     │
└─────────────────────────────────┘
```

**Hosting the MCP on AgentCore does not replace DevOps Agent fees.** You pay:

1. **AgentCore** — host/serve the MCP process  
2. **DevOps Agent** — every chat / investigation the MCP triggers  
3. Optionally **Cognito / ECR / CloudWatch / data transfer**

### AgentCore pricing (MCP host layer)

**Source:** [aws.amazon.com/bedrock/agentcore/pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)

| Component | Rate (list) | When you pay |
| --- | --- | --- |
| **Runtime CPU** | **$0.0895 / vCPU-hour** | Active CPU only (I/O wait free if no background work) |
| **Runtime Memory** | **$0.00945 / GB-hour** | Peak memory per second (128 MB minimum) |
| **Gateway InvokeTool** | **$0.005 / 1,000** | If tools go through Gateway |
| **Gateway Search** | **$0.025 / 1,000** | Semantic tool search |
| **Tool indexing** | **$0.02 / 100 tools / month** | If tools are indexed |
| **Identity** | Free via Runtime/Gateway; else **$0.010 / 1,000** | OAuth/API keys for non-AWS resources |
| **ECR / S3** | Standard storage rates | Container / artifact storage |
| **Observability** | CloudWatch rates | Spans, logs, metrics |

### MCP on AgentCore — deployment notes

- AgentCore Runtime supports deploying MCP servers
- Typical contract: host `0.0.0.0`, port `8000`, streamable-http, ARM64 container
- Auth usually Cognito OAuth and/or IAM SigV4
- Docs: [Deploy MCP servers in AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html)

### Rough AgentCore estimate for a light MCP host

Assume ~500 MCP sessions/month, ~5s active CPU @ 0.5 vCPU, ~0.5 GB memory, ~20 tool calls/session via Gateway:

| Line | Rough monthly |
| --- | --- |
| Runtime CPU + Memory | **~$0.03** |
| Gateway InvokeTool | **~$0.05** |
| ECR + Cognito (low traffic) | **~$0–1** |
| **AgentCore host total (light)** | **~$1–5** |

Heavy production (tens of thousands of sessions) scales Runtime + Gateway, but still usually **much smaller** than DevOps Agent agent-seconds if the team chats and investigates often.

### What dominates total cost?

| Layer | Typical share |
| --- | --- |
| **DevOps Agent agent-seconds** | **Dominant** |
| AgentCore Runtime for MCP | Small unless very high session volume |
| CloudWatch / Logs Insights triggered by agent | Can add up on large incidents |
| Support credits | Can offset most DevOps Agent charges |

---

## 6. Architecture options (cost & ops)

| Option | AgentCore cost | DevOps Agent cost | Best for |
| --- | --- | --- | --- |
| **A. Local MCP in Cursor** (current POC) | **$0** | Pay per chat/investigation | Developers, POC, low volume |
| **B. MCP on AgentCore Runtime** | Small Runtime + auth/ECR | Same DevOps Agent usage | Shared secured MCP URL, many clients |
| **C. Direct boto3 / Python scripts** | **$0** | Same DevOps Agent usage | Automation, cron, CI |
| **D. DevOps Agent web app only** | **$0** host | Same | Ops team UI workflows |

**Takeaway:** AgentCore is optional glue. The product you primarily pay Amazon for is **DevOps Agent active time**.

---

## 7. Complete business analysis

### Strengths

- Real AWS ops context (topology + telemetry + deploys)
- Auditable investigations + human-gated remediations
- Fits engineer workflow via MCP (Cursor) or scripts
- Support credits can make it economical if Enterprise / Unified already exists
- Scales with usage; no idle tax

### Risks / limits

- Cost scales with **agent-seconds** — chatty teams + long investigations = real spend
- No built-in hard monthly usage cap (use **AWS Budgets** as guardrail)
- Remediation ≠ permanent root-cause fix
- Needs CloudWatch Agent / SSM / IAM for deep host visibility
- Release management still noted as preview pricing on the pricing page

### When to buy / expand

- Real on-call / MTTR pain
- Multi-service correlation is routine
- Need audit journals + approved mitigations
- Want DevOps intelligence inside Cursor / CI (MCP or scripts)

### When not to buy as “the platform”

- Only need coding AI → Cursor is enough
- Only need VPC create / IaC → CDK / Terraform / CloudFormation
- Expect an unsupervised auto-healer → wrong product

### Rough monthly planning (post-trial, before Support credits)

| Team style | Mix | Ballpark |
| --- | --- | --- |
| Light (POC-like) | ~50 chats + few evals | **$25–80** |
| Active ops | ~80 investigations + 100 chats (AWS example) | **~$350** |
| Multi-team enterprise | AWS enterprise example | **~$2,000+** |
| + AgentCore MCP host | light–medium | **+$1–50** typically |

With **Enterprise / Unified** Support and meaningful Support spend, credits can cover most or all DevOps Agent charges for the month.

---

## 8. Recommendations (next steps)

1. Keep MCP local for day-to-day POC (or move to AgentCore only if a shared secured endpoint is required).
2. Complete one full **investigation → mitigation → approve → execute** cycle and measure MTTR impact.
3. Set **AWS Budgets** alerts on DevOps Agent usage.
4. Confirm Support plan credit eligibility (Business Support+ / Enterprise / Unified).
5. Close visibility gaps: CloudWatch Agent + `ssm:SendCommand` where needed.
6. Then decide commercial commitment.

---

## 9. Manager one-liner

> We connected AWS DevOps Agent to our chat agent via MCP and automated ops queries with Python. It autonomously investigates AWS issues; it remediates only after human approval within the permissions we grant. Primary cost is DevOps Agent time at **$0.0083/agent-second**; hosting the MCP on AgentCore is optional and usually a small add-on — it does not replace DevOps Agent charges.

---

## 10. Sources

- [AWS DevOps Agent Pricing](https://aws.amazon.com/devops-agent/pricing/)
- [AWS DevOps Agent product page / FAQs](https://aws.amazon.com/devops-agent/)
- [Amazon Bedrock AgentCore Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)
- [Deploy MCP servers in AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html)
- [About AWS DevOps Agent (docs)](https://docs.aws.amazon.com/devopsagent/latest/userguide/about-aws-devops-agent.html)
- Internal POC: Cursor MCP integration + `get_running_instances.py` / `get_subnet_remaining_ips.py`
