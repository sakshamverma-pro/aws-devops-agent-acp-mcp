#!/usr/bin/env python3
"""Shared AgentCore MCP invoke helpers (IAM SigV4 via boto3)."""

from __future__ import annotations

import json
from typing import Any


def parse_sse_payload(raw: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if line.startswith("data: "):
            try:
                messages.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                continue
    return messages


def invoke_mcp(
    client,
    *,
    agent_arn: str,
    qualifier: str,
    runtime_session_id: str,
    payload: dict[str, Any],
    mcp_session_id: str | None = None,
    allow_empty: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    kwargs: dict[str, Any] = {
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

    messages = parse_sse_payload(raw_body)
    if not messages:
        if allow_empty or not raw_body.strip():
            return None, response.get("mcpSessionId")
        raise RuntimeError(f"No MCP JSON-RPC messages in response: {raw_body[:500]!r}")

    return messages[-1], response.get("mcpSessionId")


def extract_tool_text(result: dict[str, Any] | None) -> str:
    if not result:
        return ""
    if "error" in result:
        return json.dumps(result["error"])
    content = result.get("result", {}).get("content", [])
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    if parts:
        return "\n".join(parts)
    return json.dumps(result.get("result", result))
