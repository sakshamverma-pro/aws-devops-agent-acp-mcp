#!/usr/bin/env python3
"""Get VPC subnet remaining (available) IPs via AWS DevOps Agent — single-file.

Flow (same as MCP `chat` tool):
  create_chat -> send_message (EventStream) -> extract text -> parse JSON

Dependencies: boto3 only (+ AWS credentials that can call devops-agent)

Usage:
  export DEVOPS_AGENT_SPACE_ID=8ccbf086-ed2f-4d03-b626-2a811d90313c
  export DEVOPS_AGENT_USER_ID=saksham.verma@tothenew.com   # optional
  export DEVOPS_AGENT_REGION=us-east-1

  python3 get_subnet_remaining_ips.py
  python3 get_subnet_remaining_ips.py --aws-region ap-south-1
  python3 get_subnet_remaining_ips.py --vpc-id vpc-xxxxxxxx
  python3 get_subnet_remaining_ips.py --raw
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Optional

import boto3

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

def build_prompt(
    aws_region: Optional[str] = None,
    vpc_id: Optional[str] = None,
    healthy_threshold: int = 10,
) -> str:
    scope_parts = []
    if vpc_id:
        scope_parts.append(f'Only include VPC "{vpc_id}".')
    if aws_region:
        scope_parts.append(f'Only scan AWS region "{aws_region}".')
    else:
        scope_parts.append("Scan all regions in my AWS account.")

    scope = " ".join(scope_parts)

    return (
        "List all VPC subnets and their remaining/available IPv4 addresses "
        f"in my AWS account. {scope} "
        "Use EC2 DescribeSubnets (AvailableIpAddressCount) and VPC Name tags. "
        "CRITICAL OUTPUT RULES:\n"
        "1) Reply with ONE compact JSON object only.\n"
        "2) No markdown fences, no commentary, no trailing text.\n"
        "3) Do NOT include a tags object. Put Name tag values only in "
        "subnetName / vpcName fields.\n"
        "4) Keep the response short and complete — do not truncate JSON.\n"
        "Schema:\n"
        "{"
        '"subnets":[{'
        '"subnetId":"...","subnetName":"...","vpcId":"...","vpcName":"...",'
        '"region":"...","availabilityZone":"...","cidrBlock":"...",'
        '"availableIpAddressCount":0,"totalIpAddresses":0,"usedIpAddresses":0,'
        '"mapPublicIpOnLaunch":false,"state":"available","healthStatus":"healthy"'
        "}],"
        '"summary":{'
        '"totalSubnets":0,"totalAvailableIps":0,"regionsScanned":0,'
        '"vpcIds":[],"accountId":"...","asOf":"..."'
        "}}\n"
        "availableIpAddressCount = remaining IPs from AWS. "
        f'Set healthStatus to \"healthy\" only when availableIpAddressCount is '
        f'greater than {healthy_threshold}; otherwise set it to \"unhealthy\". '
        "totalIpAddresses = CIDR size minus 5 AWS-reserved addresses when possible. "
        "usedIpAddresses = totalIpAddresses - availableIpAddressCount. "
        "Sort by availableIpAddressCount ascending."
    )


_TEXT_DELTA_TYPES = frozenset(
    {
        "output_text_delta",
        "reasoning_text_delta",
        "outputTextDelta",
        "reasoningTextDelta",
    }
)
_BLOCK_BOUNDARY_TYPES = frozenset(
    {
        "content_block_start",
        "contentBlockStart",
        "content_block_stop",
        "contentBlockStop",
    }
)


# ---------------------------------------------------------------------------
# Event-stream text extraction (inlined — no aws_devops_agent import)
# ---------------------------------------------------------------------------

def _delta_text(payload: dict) -> Optional[str]:
    delta = payload.get("delta") or {}
    if isinstance(delta, dict):
        text_delta = delta.get("textDelta") or delta.get("text_delta") or {}
        if isinstance(text_delta, dict) and isinstance(text_delta.get("text"), str):
            return text_delta["text"]
        if isinstance(delta.get("text"), str):
            return delta["text"]
    if isinstance(payload.get("text"), str):
        return payload["text"]
    return None


def extract_answer_text(events: list) -> str:
    """Collect answer text from the EventStream.

    Prefers a complete ``final_response`` block when present (avoids truncated
    streaming deltas). Falls back to streamed ``text`` deltas.
    """
    text_parts: list[str] = []
    final_parts: list[str] = []
    current_block_type: Optional[str] = None

    for event in events or []:
        if not isinstance(event, dict):
            continue
        for event_type, payload in event.items():
            if not isinstance(payload, dict):
                continue

            if event_type in _BLOCK_BOUNDARY_TYPES:
                if "Start" in event_type or "start" in event_type:
                    current_block_type = payload.get("type")
                else:
                    current_block_type = None
                continue

            chunk = None
            if event_type in _TEXT_DELTA_TYPES or "delta" in payload or "text" in payload:
                chunk = _delta_text(payload)
            if not chunk:
                continue

            if current_block_type == "final_response":
                final_parts.append(chunk)
            elif current_block_type in (None, "text"):
                # None = pre-GA / unknown; treat as answer text
                if current_block_type == "text" or current_block_type is None:
                    text_parts.append(chunk)

    final_text = "".join(final_parts).strip()
    streamed_text = "".join(text_parts).strip()

    # Prefer the longer complete-looking candidate
    if final_text and (
        not streamed_text
        or len(final_text) >= len(streamed_text)
        or (final_text.count("{") == final_text.count("}") and "{" in final_text)
    ):
        return final_text
    return streamed_text or final_text


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def extract_json(text: str) -> Any:
    """Parse JSON from agent answer; tolerate markdown fences / prose."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty response from DevOps Agent")

    candidates: list[str] = []

    # Full fenced block (greedy content between first opening fence and its close)
    fence = re.search(
        r"```(?:json)?\s*\n?(.*?)\n?```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if fence:
        candidates.append(fence.group(1).strip())

    candidates.append(text)

    start = text.find("{")
    if start >= 0:
        candidates.append(text[start:])

    decoder = json.JSONDecoder()
    errors: list[str] = []
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        # Direct parse
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            errors.append(str(exc))
        # Parse first JSON value, ignore trailing prose
        try:
            idx = candidate.find("{")
            if idx >= 0:
                obj, _end = decoder.raw_decode(candidate[idx:])
                return obj
        except json.JSONDecodeError as exc:
            errors.append(str(exc))

    preview = text[:400].replace("\n", "\\n")
    raise ValueError(
        "Could not parse JSON from DevOps Agent response "
        f"(likely truncated or invalid). Last errors: {errors[-2:]}. "
        f"Preview: {preview}"
    )


# ---------------------------------------------------------------------------
# DevOps Agent client helpers
# ---------------------------------------------------------------------------

def agent_region() -> str:
    """Region for the devops-agent API endpoint (not VPC filter)."""
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("DEVOPS_AGENT_REGION")
        or "us-east-1"
    )


def resolve_space_id(explicit: Optional[str] = None) -> str:
    space_id = explicit or os.environ.get("DEVOPS_AGENT_SPACE_ID")
    if space_id:
        return space_id

    client = boto3.client("devops-agent", region_name=agent_region())
    spaces = client.list_agent_spaces().get("agentSpaces") or []
    if not spaces:
        raise SystemExit(
            "No Agent Space found. Set DEVOPS_AGENT_SPACE_ID or pass --space-id."
        )
    return spaces[0]["agentSpaceId"]


def chat(space_id: str, message: str) -> tuple[str, str]:
    """create_chat + send_message. Returns (execution_id, answer_text)."""
    client = boto3.client("devops-agent", region_name=agent_region())

    chat_resp = client.create_chat(agentSpaceId=space_id)
    execution_id = chat_resp["executionId"]

    msg_resp = client.send_message(
        agentSpaceId=space_id,
        executionId=execution_id,
        content=message,
    )
    answer = extract_answer_text(msg_resp.get("events", []))
    return execution_id, answer


def get_subnet_remaining_ips(
    space_id: str,
    prompt: str,
    healthy_threshold: int = 10,
) -> dict[str, Any]:
    execution_id, answer = chat(space_id, prompt)
    data = extract_json(answer)
    if isinstance(data, dict):
        for subnet in data.get("subnets", []):
            if not isinstance(subnet, dict):
                continue
            available = subnet.get("availableIpAddressCount")
            if isinstance(available, (int, float)) and not isinstance(available, bool):
                subnet["healthStatus"] = (
                    "healthy" if available > healthy_threshold else "unhealthy"
                )
        meta = data.setdefault("_meta", {})
        if isinstance(meta, dict):
            meta["executionId"] = execution_id
            meta["agentSpaceId"] = space_id
            meta["devopsAgentRegion"] = agent_region()
            meta["via"] = "boto3.create_chat+send_message"
            meta["healthyThresholdExclusive"] = healthy_threshold
    return data


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch VPC subnet remaining/available IPs via AWS DevOps Agent "
            "(single-file, JSON out)"
        )
    )
    parser.add_argument(
        "--space-id",
        default=None,
        help="Agent Space ID (default: DEVOPS_AGENT_SPACE_ID or first listed space)",
    )
    parser.add_argument(
        "--aws-region",
        default=None,
        help="Limit VPC/subnet scan to this AWS region (e.g. ap-south-1). "
        "If omitted, ask the agent to scan all regions.",
    )
    parser.add_argument(
        "--vpc-id",
        default=None,
        help="Limit results to a single VPC ID",
    )
    parser.add_argument(
        "--healthy-threshold",
        type=int,
        default=10,
        help="Subnet is healthy only when available IPs exceed this value (default: 10)",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print raw agent text instead of parsed JSON",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Override the chat prompt sent to DevOps Agent",
    )
    args = parser.parse_args()

    space_id = resolve_space_id(args.space_id)
    prompt = args.prompt or build_prompt(
        aws_region=args.aws_region,
        vpc_id=args.vpc_id,
        healthy_threshold=args.healthy_threshold,
    )

    if args.raw:
        _execution_id, answer = chat(space_id, prompt)
        print(answer)
        return 0

    result = get_subnet_remaining_ips(
        space_id,
        prompt=prompt,
        healthy_threshold=args.healthy_threshold,
    )
    if isinstance(result, dict) and isinstance(result.get("_meta"), dict):
        if args.aws_region:
            result["_meta"]["filterAwsRegion"] = args.aws_region
        if args.vpc_id:
            result["_meta"]["filterVpcId"] = args.vpc_id

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(
            json.dumps(
                {"error": type(exc).__name__, "message": str(exc)},
                indent=2,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)
