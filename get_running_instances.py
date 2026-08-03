#!/usr/bin/env python3
"""Get running EC2 instances via AWS DevOps Agent — single-file script.

Flow (same as MCP `chat` tool):
  create_chat -> send_message (EventStream) -> extract text -> parse JSON

Dependencies: boto3 only (+ AWS credentials that can call devops-agent)

Usage:
  export DEVOPS_AGENT_SPACE_ID=8ccbf086-ed2f-4d03-b626-2a811d90313c
  export DEVOPS_AGENT_USER_ID=saksham.verma@tothenew.com   # optional
  export DEVOPS_AGENT_REGION=us-east-1

  python3 get_running_instances.py
  python3 get_running_instances.py --space-id <id>
  python3 get_running_instances.py --raw
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Generator, List, Optional, Tuple

import boto3

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_PROMPT = (
    "List all currently running EC2 instances across all regions in my AWS "
    "account. Return a single valid JSON object only (no markdown fences, no "
    "commentary). Schema:\n"
    "{\n"
    '  "runningInstances": [\n'
    "    {\n"
    '      "instanceId": "...",\n'
    '      "name": "...",\n'
    '      "instanceType": "...",\n'
    '      "region": "...",\n'
    '      "availabilityZone": "...",\n'
    '      "state": "running",\n'
    '      "architecture": "...",\n'
    '      "launchTime": "...",\n'
    '      "tags": {}\n'
    "    }\n"
    "  ],\n"
    '  "summary": {\n'
    '    "totalRunningInstances": 0,\n'
    '    "regionsWithInstances": [],\n'
    '    "regionsScanned": 0,\n'
    '    "accountId": "...",\n'
    '    "asOf": "..."\n'
    "  }\n"
    "}"
)

_DEDUP_WINDOW = 80
_MIN_SENT_BEFORE_CHECK = 100
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
_EXTRACTABLE_BLOCK_TYPES = frozenset({"text"})
_Queued = Tuple[str, str, dict]


# ---------------------------------------------------------------------------
# Event-stream text extraction (inlined — no aws_devops_agent import)
# ---------------------------------------------------------------------------

def iter_stream_events(
    events: list,
) -> Generator[tuple[str, Optional[str], dict[str, Any]], None, None]:
    """Iterate DevOps Agent EventStream with text deduplication.

    Yields (event_type, text_or_None, payload).
    Only extractable ``text`` content blocks contribute response text.
    """
    seen_streaming = False
    seen_text_deltas = False
    current_block_type: Optional[str] = None
    seen_block_start = False

    sent_parts: List[str] = []
    pending: List[_Queued] = []
    pending_parts: List[str] = []
    skipping = False

    def _flush_pending():
        nonlocal pending_parts
        out = []
        for et, txt, pl in pending:
            sent_parts.append(txt)
            out.append((et, txt, pl))
        pending.clear()
        pending_parts = []
        return out

    def _discard_pending():
        nonlocal pending_parts
        out = []
        for et, _, pl in pending:
            out.append((et, None, pl))
        pending.clear()
        pending_parts = []
        return out

    def _is_extractable_block() -> bool:
        if current_block_type is None:
            return not seen_block_start
        return current_block_type in _EXTRACTABLE_BLOCK_TYPES

    for event in events or []:
        if not isinstance(event, dict):
            continue
        for event_type, payload in event.items():
            if not isinstance(payload, dict):
                continue

            text: Optional[str] = None

            if event_type in _BLOCK_BOUNDARY_TYPES:
                for item in _flush_pending():
                    yield item
                skipping = False
                if "Start" in event_type or "start" in event_type:
                    current_block_type = payload.get("type")
                    seen_block_start = True
                else:
                    current_block_type = None
                yield (event_type, None, payload)
                continue

            # Nested delta shapes (GA)
            delta = payload.get("delta") or {}
            if isinstance(delta, dict):
                text_delta = delta.get("textDelta") or delta.get("text_delta") or {}
                if isinstance(text_delta, dict) and text_delta.get("text"):
                    text = text_delta["text"]
                elif isinstance(delta.get("text"), str):
                    text = delta["text"]

            # Flat / legacy shapes
            if text is None and event_type in _TEXT_DELTA_TYPES:
                text = payload.get("text") or payload.get("delta")
                if isinstance(text, dict):
                    text = text.get("text")

            if text is None and isinstance(payload.get("text"), str):
                # Only take bare text on extractable blocks / pre-GA streams
                if _is_extractable_block():
                    text = payload["text"]

            if text and not _is_extractable_block():
                text = None

            if text:
                seen_streaming = True
                seen_text_deltas = True
                if skipping:
                    yield (event_type, None, payload)
                    continue

                pending.append((event_type, text, payload))
                pending_parts.append(text)
                pending_joined = "".join(pending_parts)
                sent_joined = "".join(sent_parts)

                if (
                    len(pending_joined) >= _DEDUP_WINDOW
                    and len(sent_joined) >= _MIN_SENT_BEFORE_CHECK
                    and pending_joined in sent_joined
                ):
                    for item in _discard_pending():
                        yield item
                    skipping = True
                    continue

                if len(pending_joined) >= _DEDUP_WINDOW:
                    for item in _flush_pending():
                        yield item
                continue

            # Non-text / boundary-ish events: flush buffer
            for item in _flush_pending():
                yield item
            skipping = False

            # Suppress duplicate final_response-style completed text when
            # we already streamed deltas.
            if seen_text_deltas and event_type in (
                "output_text_done",
                "outputTextDone",
                "message_stop",
                "messageStop",
            ):
                yield (event_type, None, payload)
                continue

            yield (event_type, None, payload)

    for item in _flush_pending():
        yield item


def extract_answer_text(events: list) -> str:
    parts: list[str] = []
    for _etype, text, _payload in iter_stream_events(events):
        if text:
            parts.append(text)
    return "".join(parts)


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def extract_json(text: str) -> Any:
    """Parse JSON from agent answer; tolerate markdown fences / prose."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty response from DevOps Agent")

    fence = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if fence:
        return json.loads(fence.group(1))

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


# ---------------------------------------------------------------------------
# DevOps Agent client helpers
# ---------------------------------------------------------------------------

def region() -> str:
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("DEVOPS_AGENT_REGION")
        or "us-east-1"
    )


def resolve_space_id(explicit: Optional[str] = None) -> str:
    space_id = explicit or os.environ.get("DEVOPS_AGENT_SPACE_ID")
    if space_id:
        return space_id

    client = boto3.client("devops-agent", region_name=region())
    spaces = client.list_agent_spaces().get("agentSpaces") or []
    if not spaces:
        raise SystemExit(
            "No Agent Space found. Set DEVOPS_AGENT_SPACE_ID or pass --space-id."
        )
    return spaces[0]["agentSpaceId"]


def chat(space_id: str, message: str) -> tuple[str, str]:
    """create_chat + send_message. Returns (execution_id, answer_text)."""
    client = boto3.client("devops-agent", region_name=region())

    chat_resp = client.create_chat(agentSpaceId=space_id)
    execution_id = chat_resp["executionId"]

    msg_resp = client.send_message(
        agentSpaceId=space_id,
        executionId=execution_id,
        content=message,
    )
    answer = extract_answer_text(msg_resp.get("events", []))
    return execution_id, answer


def get_running_instances(space_id: str, prompt: str = DEFAULT_PROMPT) -> dict[str, Any]:
    execution_id, answer = chat(space_id, prompt)
    data = extract_json(answer)
    if isinstance(data, dict):
        meta = data.setdefault("_meta", {})
        if isinstance(meta, dict):
            meta["executionId"] = execution_id
            meta["agentSpaceId"] = space_id
            meta["region"] = region()
            meta["via"] = "boto3.create_chat+send_message"
    return data


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="List running EC2 instances via AWS DevOps Agent (single-file, JSON out)"
    )
    parser.add_argument(
        "--space-id",
        default=None,
        help="Agent Space ID (default: DEVOPS_AGENT_SPACE_ID or first listed space)",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print raw agent text instead of parsed JSON",
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="Override the chat prompt sent to DevOps Agent",
    )
    args = parser.parse_args()

    space_id = resolve_space_id(args.space_id)

    if args.raw:
        _execution_id, answer = chat(space_id, args.prompt)
        print(answer)
        return 0

    result = get_running_instances(space_id, prompt=args.prompt)
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
