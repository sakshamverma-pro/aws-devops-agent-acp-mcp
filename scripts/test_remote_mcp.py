#!/usr/bin/env python3
"""Test a deployed DevOps Agent MCP runtime on AgentCore with IAM (SigV4) auth.

Uses boto3 invoke_agent_runtime — signs requests with your AWS credentials.
No bearer token required when the endpoint uses inbound IAM auth.

Required env vars:
  AGENT_ARN  - runtime ARN

Optional:
  AWS_REGION          - defaults to us-east-1
  RUNTIME_SESSION_ID  - reuse a session (must be >= 33 chars); auto-generated if unset
  QUALIFIER           - endpoint qualifier, defaults to DEFAULT
"""

from __future__ import annotations

import json
import os
import sys
import uuid


def _parse_sse_payload(raw: str) -> list[dict]:
    """Extract JSON objects from MCP streamable-http SSE responses."""
    messages: list[dict] = []
    for line in raw.splitlines():
        if line.startswith("data: "):
            try:
                messages.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                continue
    return messages


def _invoke_mcp(
    client,
    *,
    agent_arn: str,
    qualifier: str,
    runtime_session_id: str,
    payload: dict,
    mcp_session_id: str | None = None,
    allow_empty: bool = False,
) -> tuple[dict | None, str | None, str]:
    kwargs = {
        "agentRuntimeArn": agent_arn,
        "qualifier": qualifier,
        "runtimeSessionId": runtime_session_id,
        "payload": json.dumps(payload).encode("utf-8"),
        "contentType": "application/json",
        "accept": "application/json, text/event-stream",
    }
    if mcp_session_id:
        kwargs["mcpSessionId"] = mcp_session_id

    response = client.invoke_agent_runtime(**kwargs)
    status_code = response.get("statusCode", 0)
    raw_body = response["response"].read().decode("utf-8", errors="replace")

    if status_code >= 400:
        raise RuntimeError(
            f"InvokeAgentRuntime failed with HTTP {status_code}: {raw_body[:500]}"
        )

    messages = _parse_sse_payload(raw_body)
    if not messages:
        if allow_empty or not raw_body.strip():
            return None, response.get("mcpSessionId"), raw_body
        raise RuntimeError(f"No MCP JSON-RPC messages in response: {raw_body[:500]!r}")

    return messages[-1], response.get("mcpSessionId"), raw_body


def main() -> None:
    agent_arn = os.getenv(
        "AGENT_ARN",
        "arn:aws:bedrock-agentcore:us-east-1:058029412961:runtime/DevopsAgentMcpTest-Q1Am9rGGut",
    )
    region = os.getenv("AWS_REGION", "us-east-1")
    qualifier = os.getenv("QUALIFIER", "DEFAULT")
    runtime_session_id = os.getenv("RUNTIME_SESSION_ID") or str(uuid.uuid4())

    if len(runtime_session_id) < 33:
        print("Error: RUNTIME_SESSION_ID must be at least 33 characters")
        sys.exit(1)

    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        print("Error: boto3 is required (pip install boto3)")
        sys.exit(1)

    client = boto3.client("bedrock-agentcore", region_name=region)

    print(f"Agent ARN:          {agent_arn}")
    print(f"Region:             {region}")
    print(f"Qualifier:          {qualifier}")
    print(f"Runtime session ID: {runtime_session_id}")
    print("Auth:               IAM (SigV4 via default AWS credential chain)")
    print()

    try:
        init_result, mcp_session_id, _ = _invoke_mcp(
            client,
            agent_arn=agent_arn,
            qualifier=qualifier,
            runtime_session_id=runtime_session_id,
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-remote-mcp", "version": "1.0"},
                },
            },
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        message = exc.response.get("Error", {}).get("Message", str(exc))
        print(f"AWS error ({code}): {message}")
        if code == "AccessDeniedException":
            print(
                "\nYour IAM user/role needs bedrock-agentcore:InvokeAgentRuntime on:\n"
                f"  {agent_arn}\n"
                f"  {agent_arn}/runtime-endpoint/{qualifier}"
            )
        sys.exit(1)
    except RuntimeError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    if "error" in init_result:
        print(f"MCP initialize error: {init_result['error']}")
        sys.exit(1)

    server_info = init_result.get("result", {}).get("serverInfo", {})
    print(f"Connected to: {server_info.get('name')} v{server_info.get('version')}")
    print(f"MCP session ID: {mcp_session_id}")

    if mcp_session_id:
        _invoke_mcp(
            client,
            agent_arn=agent_arn,
            qualifier=qualifier,
            runtime_session_id=runtime_session_id,
            mcp_session_id=mcp_session_id,
            payload={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            allow_empty=True,
        )

    tools_result, _, _ = _invoke_mcp(
        client,
        agent_arn=agent_arn,
        qualifier=qualifier,
        runtime_session_id=runtime_session_id,
        mcp_session_id=mcp_session_id,
        payload={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )

    if "error" in tools_result:
        print(f"tools/list error: {tools_result['error']}")
        sys.exit(1)

    tools = tools_result.get("result", {}).get("tools", [])
    print(f"Tools available: {len(tools)}")
    for tool in tools[:8]:
        print(f"  - {tool.get('name')}")
    if len(tools) > 8:
        print(f"  ... and {len(tools) - 8} more")


if __name__ == "__main__":
    main()
