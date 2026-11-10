"""On-demand public detail, bounded and returned as inert plain text."""
import json
from pathlib import Path
import re
import stat

from .adapters._io import LIMIT, bounded_text, mapping, public_record, safe_text
from .model import Agent


def read_agent_detail(agent: Agent, kind: str = "output") -> str:
    if kind == "task":
        return bounded_text(safe_text(agent.task))
    if kind not in ("output", "result", "error"):
        return ""
    filename = getattr(agent, {"output": "output_path", "result": "result_path", "error": "error_path"}[kind])
    if not filename:
        return bounded_text(safe_text(agent.error or "")) if kind == "error" else ""
    path = Path(filename)
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            return ""
        with path.open("rb") as handle:
            start = max(0, info.st_size - LIMIT)
            handle.seek(start)
            data = handle.read(LIMIT)
        if start:
            data = data.partition(b"\n")[2]
    except OSError:
        return ""
    text = data.decode("utf-8", errors="replace")
    structured = path.suffix == ".jsonl" or (kind == "output" and text.lstrip().startswith("{"))
    parts = []
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        json_line = stripped.startswith("{") or (stripped.startswith("[") and not re.match(r"\[/?[A-Za-z][^\]\n]*\]", stripped))
        if structured or json_line:
            if not line.endswith("\n"):
                continue
            try:
                row = mapping(json.loads(line))
                public = public_record(row)
                if kind == "result":
                    message = mapping(row.get("message"))
                    payload = mapping(row.get("payload"))
                    final = (row.get("type") == "result" or
                             (row.get("type") == "assistant" and message.get("stop_reason") == "end_turn") or
                             (row.get("type") == "event_msg" and payload.get("type") == "task_complete") or
                             (row.get("type") == "response_item" and payload.get("type") == "message" and payload.get("channel") == "final"))
                    if final and public:
                        parts = public
                else:
                    parts.extend(public)
            except (ValueError, RecursionError):
                continue
        else:
            parts.append(line.rstrip("\n"))
    text = "\n".join(parts)
    return bounded_text(safe_text(text))
