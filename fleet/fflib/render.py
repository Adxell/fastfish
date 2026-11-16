"""Turn Claude Code stream-json output (as printed by agent-run.sh) into readable lines."""
from __future__ import annotations

import json
from typing import Iterable, Iterator

REPORT_START = "[ff] ===== review report ====="
REPORT_END = "[ff] ===== end review report ====="

_INPUT_KEYS = ("command", "file_path", "pattern", "path", "url", "description", "prompt", "skill")


def _short(text: str, limit: int = 160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _tool_summary(block: dict) -> str:
    name = block.get("name", "tool")
    inp = block.get("input") or {}
    for key in _INPUT_KEYS:
        if isinstance(inp, dict) and inp.get(key):
            return f"  → {name}: {_short(inp[key], 120)}"
    return f"  → {name}"


def render_event(event: dict) -> list[str]:
    kind = event.get("type")
    if kind == "system" and event.get("subtype") == "init":
        return [f"▸ session started · model {event.get('model', '?')}"]
    if kind == "assistant":
        out = []
        for block in (event.get("message") or {}).get("content") or []:
            if block.get("type") == "text" and block.get("text", "").strip():
                out.extend(block["text"].rstrip().splitlines())
            elif block.get("type") == "tool_use":
                out.append(_tool_summary(block))
        return out
    if kind == "user":
        out = []
        content = (event.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if block.get("type") == "tool_result" and block.get("is_error"):
                body = block.get("content")
                if isinstance(body, list):
                    body = " ".join(b.get("text", "") for b in body if isinstance(b, dict))
                out.append(f"  ✗ {_short(body or 'tool error')}")
        return out
    if kind == "result":
        cost = event.get("total_cost_usd")
        bits = [
            "error" if event.get("is_error") else "done",
            f"{event.get('num_turns', '?')} turns",
            f"{(event.get('duration_ms') or 0) / 1000:.0f}s",
        ]
        if cost is not None:
            bits.append(f"${cost:.2f}")
        return [f"■ {' · '.join(bits)}"]
    return []


def render_lines(lines: Iterable[str]) -> Iterator[str]:
    for raw in lines:
        line = raw.rstrip("\n")
        if not line.startswith("{"):
            yield line
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            yield line
            continue
        yield from render_event(event)


def split_log(text: str) -> tuple[list[str], str]:
    """Split a raw pod log into (stream-json transcript lines, review report markdown)."""
    transcript, report, in_report = [], [], False
    for line in text.splitlines():
        if line == REPORT_START:
            in_report = True
        elif line == REPORT_END:
            in_report = False
        elif in_report:
            report.append(line)
        elif line.startswith("{"):
            transcript.append(line)
    return transcript, "\n".join(report).strip()
