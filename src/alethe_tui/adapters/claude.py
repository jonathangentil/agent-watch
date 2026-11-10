"""Claude sidechains and explicit parent tool links; end_turn is resumable."""
from pathlib import Path

from ..model import Agent, Event, Execution, ScanResult
from ._io import JsonCache, NativeFile, bounded_text, discover, mapping, public_blocks, safe_text, sequence, stable_id, string


class ClaudeAdapter:
    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()
        self.files = {}
        self.cache = JsonCache("claude")

    def _consume(self, file, offset, row):
        facts = file.facts
        message = mapping(row.get("message"))
        timestamp = string(row.get("timestamp")) or None
        if row.get("isSidechain") is True and isinstance(row.get("agentId"), str):
            facts.update(identity=row["agentId"], sidechain=True)
            if timestamp:
                facts.setdefault('started', timestamp)
        if isinstance(row.get("sessionId"), str):
            facts["session"] = row["sessionId"]
        if isinstance(row.get("cwd"), str):
            facts["cwd"] = row["cwd"]
        if isinstance(message.get("model"), str):
            facts["model"] = safe_text(message["model"])
        kind = row.get("type")
        evidence = f"{file.cursor.path}:{offset}: {kind}"
        if kind in ("assistant", "user") and message:
            if file.cursor.path.parent.name != "subagents":
                facts["valid"] = True
            facts["activity"] = timestamp
            facts["status"] = "turn_complete" if kind == "assistant" and message.get("stop_reason") == "end_turn" else "unknown"
            facts["finished"] = timestamp if facts["status"] == "turn_complete" else None
            facts["evidence"] = evidence + ("/end_turn" if facts["status"] == "turn_complete" else "; estado não confirmado")
            if facts["status"] == "turn_complete":
                file.events.append((offset, "result_available", timestamp, evidence + "/end_turn", string(row.get("uuid")), None, False))
            if message.get("channel") in ("analysis", "reasoning", "thinking"):
                return
            if kind == "user" and not row.get("isMeta") and not facts.get("task"):
                content = message.get("content")
                blocks = content if isinstance(content, str) else [block for block in sequence(content) if mapping(block).get("type") == "text"]
                facts["task"] = bounded_text(safe_text("\n".join(public_blocks(blocks))))
            for index, block in enumerate(sequence(message.get("content"))):
                block = mapping(block)
                if block.get("channel") in ("analysis", "reasoning", "thinking"):
                    continue
                btype = block.get("type")
                if btype == "tool_use":
                    tool_id = string(block.get("id"))
                    if tool_id:
                        # Bounded public records also serve as evidence for meta.toolUseId.
                        file.events.append((offset, "tool", timestamp, evidence + "/tool_use", tool_id,
                                            safe_text(block.get("name")), bool(mapping(block.get("input")).get("run_in_background"))))
                elif btype == "tool_result" and not block.get("is_error") and isinstance(block.get("tool_use_id"), str):
                    file.events.append((offset, "received", timestamp, evidence + "/tool_result", block["tool_use_id"], None, False))

    def scan(self) -> ScanResult:
        result = ScanResult()
        root = self.root / "projects" if (self.root / "projects").is_dir() else self.root
        paths = discover(root, "**/subagents/agent-*.jsonl", "claude", result.diagnostics)
        for path in paths:
            self.files.setdefault(path, NativeFile(path, "claude"))
            # Main transcript is adjacent to its session directory.
            parent = path.parent.parent
            parent_path = parent.parent / (parent.name + ".jsonl")
            if parent_path.is_file():
                self.files.setdefault(parent_path, NativeFile(parent_path, "claude"))
        for file in self.files.values():
            file.poll(result.diagnostics, self._consume)
        candidates = []
        for path, file in self.files.items():
            facts = file.facts
            if not facts.get("sidechain") or not facts.get("identity") or path.parent.name != "subagents":
                continue
            session = path.parent.parent.name
            identity = facts["identity"]
            agent_id = "claude:" + session + ":" + identity
            meta = self.cache.read(path.with_suffix(".meta.json"), result.diagnostics, optional=True)
            candidates.append((path, file, session, identity, agent_id, meta))
        owners = {}
        for path, file in self.files.items():
            session = path.parent.parent.name if path.parent.name == "subagents" else path.stem
            owner = "claude:" + session
            if file.facts.get("sidechain") and file.facts.get("identity"):
                owner += ":" + file.facts["identity"]
            for event in file.events:
                offset, kind, timestamp, evidence, tool_id, name, background = event
                if kind == "tool" and name in ("Agent", "Task"):
                    owners[(session, tool_id)] = (owner, file, event)
        executions = {}
        for path, file, session, identity, agent_id, meta in sorted(candidates, key=lambda item: str(item[0])):
            facts = file.facts
            execution_id = "claude:execution:" + session
            cwd = facts.get("cwd", "")
            tool_id = string(meta.get("toolUseId"))
            owner = owners.get((session, tool_id))
            parent_id = owner[0] if owner else "claude:" + session
            agent = Agent(
                id=agent_id, source="claude", source_id=identity,
                # sessionId in a sidechain is the *parent* session, not this agent's identity.
                session_id=identity, execution_id=execution_id,
                project_id=cwd or execution_id + ":unknown-project", name=safe_text(meta.get("agentType")) or safe_text(identity),
                parent_id=parent_id, provider="claude", model=facts.get("model"), cwd=cwd,
                task=facts.get("task", ""),
                status=facts.get("status", "unknown"), finished_at=facts.get("finished"), last_activity=facts.get("activity"),
                evidence=facts.get("evidence", "estado não confirmado"), output_path=str(path),
                result_path=str(path) if facts.get("status") == "turn_complete" else None)
            result.agents.append(agent)
            execution = executions.setdefault(execution_id, Execution(
                id=execution_id, title="Claude " + safe_text(session), source="claude", project_id=agent.project_id,
                project_name=safe_text(Path(cwd).name) if cwd else "não informado", project_path=cwd,
                session_id=session, leader_id="claude:" + session, started_at=facts.get('started')))
            if agent.project_id not in execution.project_ids:
                execution.project_ids.append(agent.project_id)
            def add_event(kind, event, actor, target=None):
                offset, _, timestamp, evidence, native_id, _, _ = event
                result.events.append(Event(
                    id="claude:" + stable_id(agent_id, kind, native_id or offset), kind=kind, source="claude",
                    execution_id=execution_id, timestamp=timestamp, actor_id=actor, target_id=target, evidence=evidence))
            for event in file.events:
                if event[1] in ("tool", "result_available"):
                    add_event(event[1], event, agent_id)
            if owner:
                add_event("delegated", owner[2], parent_id, agent_id)
                for event in owner[1].events:
                    if event[1] == "received" and event[4] == tool_id and not owner[2][6]:
                        add_event("result_delivered", event, agent_id, parent_id)
        result.executions = list(executions.values())
        result.events = list({event.id: event for event in result.events}.values())
        return result
