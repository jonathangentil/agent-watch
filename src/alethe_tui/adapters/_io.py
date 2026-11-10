"""Bounded, read-only source primitives. No CLI imports or process control."""
from collections import deque
import hashlib
import json
from pathlib import Path
import re
import stat

LIMIT = 64 * 1024
LINES = 2000


def mapping(value):
    return value if isinstance(value, dict) else {}


def sequence(value):
    return value if isinstance(value, list) else []


def string(value):
    return value if isinstance(value, str) else ""


def diagnostic(source, path, status, message):
    return {"source": source, "path": str(path), "status": status, "message": message}


def stable_id(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=True, sort_keys=True).encode()).hexdigest()[:32]


def safe_text(value):
    """Plain display text; private tagged blocks fail closed if unfinished."""
    text = string(value)
    text = re.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\|$)", "", text)
    text = re.sub(r"\x1b[P_^].*?(?:\x1b\\|$)", "", text, flags=re.S)
    text = re.sub(r"(?:\x1b\[|\x9b)[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"\x1b(?:[@-_]|\[[^\n]*$)", "", text)
    text = re.sub(r"<(think|thinking|reasoning|analysis)\b[^>]*>.*?(?:</\1\s*>|$)", "", text, flags=re.I | re.S)
    # A tail can start inside a private block: discard everything before its close.
    text = re.sub(r"^.*?</(?:think|thinking|reasoning|analysis)\s*>", "", text, flags=re.I | re.S)
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]", "", text)
    return text.translate(str.maketrans({"[": "［", "]": "］", "<": "＜", ">": "＞"}))


def bounded_text(text):
    return "\n".join(text.splitlines()[-LINES:]).encode("utf-8")[-LIMIT:].decode("utf-8", errors="ignore")


def public_blocks(content):
    if isinstance(content, str):
        return [content]
    result = []
    for block in sequence(content):
        block = mapping(block)
        kind = block.get("type")
        if block.get("channel") in ("analysis", "reasoning", "thinking"):
            continue
        if kind in ("text", "input_text", "output_text"):
            result.append(string(block.get("text")))
        elif kind in ("tool_use", "function_call", "custom_tool_call"):
            result.append("tool: " + string(block.get("name")))
        elif kind == "tool_result":
            result.extend(public_blocks(block.get("content")))
    return result


def public_record(row):
    """Only documented public messages/tools; never serialize unknown payloads."""
    row = mapping(row)
    if row.get("channel") in ("analysis", "reasoning", "thinking"):
        return []
    kind = row.get("type")
    if kind in ("assistant", "user"):
        message = mapping(row.get("message"))
        if message.get("channel") in ("analysis", "reasoning", "thinking"):
            return []
        return public_blocks(message.get("content"))
    if kind in ("response_item", "item.completed", "item_completed"):
        item = mapping(row.get("payload") if kind == "response_item" else row.get("item"))
        if item.get("channel") in ("analysis", "reasoning", "thinking"):
            return []
        itype = item.get("type")
        if itype == "message":
            return public_blocks(item.get("content"))
        if itype in ("agent_message", "user_message"):
            return [string(item.get("text"))]
        if itype in ("function_call", "custom_tool_call"):
            return ["tool: " + string(item.get("name"))]
        if itype == "function_call_output":
            return [string(item.get("output"))]
        if itype == "command_execution":
            return ["tool: exec", string(item.get("aggregated_output"))]
    if kind == "event_msg":
        payload = mapping(row.get("payload"))
        if payload.get("channel") in ("analysis", "reasoning", "thinking"):
            return []
        if payload.get("type") in ("agent_message", "user_message"):
            return [string(payload.get("message"))]
        if payload.get("type") == "task_complete":
            return [string(payload.get("last_agent_message"))]
    if kind == "result":  # Claude stream-json public final result
        return [string(row.get("result"))]
    return []


class JsonCache:
    def __init__(self, source):
        self.source = source
        self.values = {}

    def read(self, path, diagnostics, optional=False, validate=None):
        path = Path(path)
        previous = self.values.get(path)
        try:
            info = path.stat()
            key = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            if previous and previous[0] == key:
                return previous[1]
            if not stat.S_ISREG(info.st_mode) or info.st_size > 4 * 1024 * 1024:
                raise ValueError
            with path.open("rb") as handle:
                value = json.loads(handle.read(4 * 1024 * 1024 + 1))
            if not isinstance(value, dict) or (validate and not validate(value)):
                raise ValueError
            self.values[path] = (key, value)
            return value
        except FileNotFoundError:
            if not optional or previous:
                diagnostics.append(diagnostic(self.source, path, "unavailable", "arquivo ausente; última leitura válida preservada"))
        except OSError:
            diagnostics.append(diagnostic(self.source, path, "unavailable", "arquivo não acessível"))
        except (ValueError, UnicodeError, RecursionError):
            diagnostics.append(diagnostic(self.source, path, "invalid", "JSON inválido ou limite excedido; última leitura válida preservada"))
        return previous[1] if previous else {}


class TextCache:
    """Bounded prompt head, cached by file identity; source files stay untouched."""
    def __init__(self, source):
        self.source = source
        self.values = {}

    def read(self, path, diagnostics):
        previous = self.values.get(path)
        try:
            info = path.stat()
            key = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            if previous and previous[0] == key:
                return previous[1]
            if not stat.S_ISREG(info.st_mode):
                raise OSError
            with path.open('rb') as handle:
                data = handle.read(LIMIT)
            text = safe_text(data.decode('utf-8', errors='replace'))
            self.values[path] = (key, text)
            if info.st_size > LIMIT:
                diagnostics.append(diagnostic(self.source, path, 'limited', 'tarefa limitada aos primeiros 64KiB'))
            return text
        except OSError:
            if previous:
                diagnostics.append(diagnostic(self.source, path, 'unavailable', 'tarefa indisponível; última leitura válida preservada'))
            return previous[1] if previous else ''


class JsonlCursor:
    """At most 64KiB per poll, complete records only, bounded pending line.

    Large initial files read the complete metadata line within the budget,
    then use the remaining bytes for the tail. Current Codex metadata can
    exceed 20KiB; a fixed 8KiB prefix would silently lose its identity.
    Append polls catch up in bounded chunks; offsets are evidence, not time.
    """
    def __init__(self, path, source):
        self.path = path
        self.source = source
        self.signature = None
        self.offset = 0
        self.pending = b""
        self.discard = False
        self.anchor = b""
        self.initial_skipped = False

    def _parse(self, data, start, diagnostics):
        rows = []
        base = start - len(self.pending)
        data = self.pending + data
        self.pending = b""
        chunks = data.split(b"\n")
        complete, tail = chunks[:-1], chunks[-1]
        for line in complete:
            if self.discard:
                self.discard = False
            elif len(line) > LIMIT:
                diagnostics.append(diagnostic(self.source, self.path, "invalid", "linha JSONL excede o limite"))
            elif line.strip():
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        rows.append((base, row))
                except (ValueError, UnicodeError, RecursionError):
                    diagnostics.append(diagnostic(self.source, self.path, "invalid", "linha JSONL ignorada"))
            base += len(line) + 1
        if len(tail) > LIMIT:
            self.discard = True
        elif not self.discard:
            self.pending = tail
        return rows

    def poll(self, diagnostics):
        try:
            info = self.path.stat()
            if not stat.S_ISREG(info.st_mode):
                raise OSError
            signature = (info.st_dev, info.st_ino)
            reset = self.signature != signature or info.st_size < self.offset
            budget = LIMIT
            with self.path.open("rb") as handle:
                # Detect same-inode truncate+regrow even when final size increased.
                if not reset and self.anchor:
                    handle.seek(max(0, self.offset - len(self.anchor)))
                    reset = handle.read(len(self.anchor)) != self.anchor
                    budget -= len(self.anchor)
                if reset:
                    self.pending = b""
                    self.discard = False
                    self.offset = 0
                    self.anchor = b""
                    handle.seek(0)
                    self.initial_skipped = info.st_size > budget
                    if info.st_size > budget:
                        diagnostics.append(diagnostic(self.source, self.path, "limited", "leitura inicial limitada a metadados e cauda de 64KiB; trecho intermediário omitido"))
                        head = handle.readline(budget)
                        rows = self._parse(head, 0, diagnostics)
                        self.pending = b""
                        self.discard = True
                        remaining = budget - len(head)
                        self.offset = info.st_size - remaining
                        handle.seek(self.offset)
                        data = handle.read(remaining)
                        rows += self._parse(data, self.offset, diagnostics)
                    else:
                        handle.seek(0)
                        data = handle.read(budget)
                        rows = self._parse(data, 0, diagnostics)
                else:
                    handle.seek(self.offset)
                    data = handle.read(budget)
                    rows = self._parse(data, self.offset, diagnostics)
                self.offset += len(data)
                self.anchor = data[-128:] if data else self.anchor
                self.signature = signature
            return reset, rows
        except OSError:
            diagnostics.append(diagnostic(self.source, self.path, "unavailable", "transcrição não acessível; última leitura válida preservada"))
            return False, []


class NativeFile:
    def __init__(self, path, source):
        self.cursor = JsonlCursor(path, source)
        self.facts = {}
        self.events = deque(maxlen=LINES)
        self.staging = None

    def poll(self, diagnostics, consume):
        reset, rows = self.cursor.poll(diagnostics)
        if reset:
            self.staging = ({}, deque(maxlen=LINES))
        previous = self.facts, self.events
        if self.staging is not None:
            self.facts, self.events = self.staging
        for offset, row in rows:
            consume(self, offset, row)
        if self.staging is not None:
            if self.facts.get("identity") or self.facts.get("valid"):
                self.staging = None
            else:
                self.facts, self.events = previous
                diagnostics.append(diagnostic(self.cursor.source, self.cursor.path, "invalid", "metadados incompletos; última leitura válida preservada"))


def discover(root, pattern, source, diagnostics):
    try:
        if not root.is_dir():
            raise OSError
        return sorted(path.resolve() for path in root.glob(pattern))
    except OSError:
        diagnostics.append(diagnostic(source, root, "unavailable", "raiz não acessível"))
        return []
