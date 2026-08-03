#!/usr/bin/env python3
"""Cursor stdio MCP bridge → AgentCore Runtime (IAM SigV4).

Cursor speaks MCP over stdio. AgentCore speaks MCP over HTTPS with IAM auth.
This script sits in the middle: Cursor runs it as a local MCP server, and it
forwards tool calls to your deployed AgentCore runtime using boto3.

Required env vars:
  AGENT_ARN  - your runtime ARN

Optional:
  AWS_REGION          - defaults to us-east-1
  QUALIFIER           - defaults to DEFAULT
  RUNTIME_SESSION_ID  - reuse session (>= 33 chars); new UUID if unset

Cursor mcp.json example:
  {
    "mcpServers": {
      "aws-devops-agent-agentcore": {
        "command": "/path/to/.venv/bin/python",
        "args": ["/path/to/scripts/cursor_agentcore_bridge.py"],
        "env": {
          "AGENT_ARN": "arn:aws:bedrock-agentcore:us-east-1:ACCOUNT:runtime/DevopsAgentMcpTest-XXXX",
          "AWS_REGION": "us-east-1"
        }
      }
    }
  }
"""

from __future__ import annotations

import inspect
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

# Allow importing agentcore_mcp_client from the same scripts/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import boto3
from mcp.server.fastmcp import FastMCP

from agentcore_mcp_client import extract_tool_text, invoke_mcp

AGENT_ARN = os.getenv(
    "AGENT_ARN",
    "arn:aws:bedrock-agentcore:us-east-1:058029412961:runtime/DevopsAgentMcpTest-Q1Am9rGGut",
)
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
QUALIFIER = os.getenv("QUALIFIER", "DEFAULT")
RUNTIME_SESSION_ID = os.getenv("RUNTIME_SESSION_ID") or str(uuid.uuid4())

if len(RUNTIME_SESSION_ID) < 33:
    print("RUNTIME_SESSION_ID must be at least 33 characters", file=sys.stderr)
    sys.exit(1)

_boto_client = boto3.client("bedrock-agentcore", region_name=AWS_REGION)
_mcp_session_id: str | None = None

mcp = FastMCP(
    "aws-devops-agent-agentcore",
    instructions=(
        "AWS DevOps Agent tools proxied from Amazon Bedrock AgentCore Runtime. "
        "Use chat for quick questions and investigate for incidents."
    ),
)

_JSON_TYPE_MAP = {
    "string": str,
    "integer": int,
    "boolean": bool,
    "number": float,
    "array": list,
    "object": dict,
}


def _annotation_from_property(prop: dict[str, Any], is_required: bool) -> Any:
    """Map a JSON Schema property to a Python type annotation for FastMCP."""
    if "anyOf" in prop:
        non_null = [item for item in prop["anyOf"] if item.get("type") != "null"]
        if not non_null:
            ann: Any = Any
        else:
            ann = _JSON_TYPE_MAP.get(non_null[0].get("type", "string"), Any)
        if not is_required or any(item.get("type") == "null" for item in prop["anyOf"]):
            return Optional[ann]
        return ann

    ann = _JSON_TYPE_MAP.get(prop.get("type", "string"), Any)
    if not is_required:
        return Optional[ann]
    return ann


def _build_proxy_handler(tool_def: dict[str, Any]):
    """Build a local MCP handler that mirrors the remote tool's input schema."""
    tool_name = tool_def["name"]
    description = tool_def.get("description") or f"Remote tool: {tool_name}"
    schema = tool_def.get("inputSchema") or {"type": "object", "properties": {}}
    properties: dict[str, Any] = schema.get("properties", {})
    required = set(schema.get("required", []))

    parameters: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {"return": str}

    for param_name, param_schema in properties.items():
        is_required = param_name in required
        annotation = _annotation_from_property(param_schema, is_required)
        annotations[param_name] = annotation

        if is_required:
            default = inspect.Parameter.empty
        else:
            default = param_schema.get("default", None)

        parameters.append(
            inspect.Parameter(
                param_name,
                inspect.Parameter.KEYWORD_ONLY,
                default=default,
                annotation=annotation,
            )
        )

    def handler(**kwargs: Any) -> str:
        arguments = {key: value for key, value in kwargs.items() if value is not None}
        return _call_remote_tool(tool_name, arguments)

    handler.__name__ = tool_name
    handler.__doc__ = description
    handler.__annotations__ = annotations
    handler.__signature__ = inspect.Signature(parameters, return_annotation=str)  # type: ignore[attr-defined]
    return handler


def _call_remote_tool(name: str, arguments: dict) -> str:
    global _mcp_session_id
    result, _mcp_session_id = invoke_mcp(
        _boto_client,
        agent_arn=AGENT_ARN,
        qualifier=QUALIFIER,
        runtime_session_id=RUNTIME_SESSION_ID,
        mcp_session_id=_mcp_session_id,
        payload={
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        },
    )
    return extract_tool_text(result)


def _bootstrap_remote_session() -> None:
    global _mcp_session_id

    init_result, _mcp_session_id = invoke_mcp(
        _boto_client,
        agent_arn=AGENT_ARN,
        qualifier=QUALIFIER,
        runtime_session_id=RUNTIME_SESSION_ID,
        payload={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "cursor-agentcore-bridge", "version": "1.0"},
            },
        },
    )
    if init_result and "error" in init_result:
        raise RuntimeError(f"MCP initialize failed: {init_result['error']}")

    if _mcp_session_id:
        invoke_mcp(
            _boto_client,
            agent_arn=AGENT_ARN,
            qualifier=QUALIFIER,
            runtime_session_id=RUNTIME_SESSION_ID,
            mcp_session_id=_mcp_session_id,
            payload={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
            allow_empty=True,
        )

    tools_result, _mcp_session_id = invoke_mcp(
        _boto_client,
        agent_arn=AGENT_ARN,
        qualifier=QUALIFIER,
        runtime_session_id=RUNTIME_SESSION_ID,
        mcp_session_id=_mcp_session_id,
        payload={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    if not tools_result or "error" in tools_result:
        raise RuntimeError(f"tools/list failed: {tools_result}")

    remote_tools = tools_result.get("result", {}).get("tools", [])
    for tool in remote_tools:
        handler = _build_proxy_handler(tool)
        mcp.add_tool(
            handler,
            name=tool["name"],
            description=tool.get("description") or f"Remote tool: {tool['name']}",
        )

    print(
        f"AgentCore bridge ready: {len(remote_tools)} tools via {AGENT_ARN}",
        file=sys.stderr,
    )


def _print_tool_schemas() -> None:
    """Debug helper: print registered local tool parameter schemas."""
    _bootstrap_remote_session()
    for tool in sorted(mcp._tool_manager._tools.values(), key=lambda item: item.name):
        print(f"{tool.name}: {json.dumps(tool.parameters, indent=2)[:500]}")
        print("---")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--check-tools":
        _print_tool_schemas()
        return
    _bootstrap_remote_session()
    mcp.run()


if __name__ == "__main__":
    main()
