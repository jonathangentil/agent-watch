"""Codex rollout metadata and public lifecycle events, including 0.167."""
from pathlib import Path

from ..model import Agent, Event, Execution, ScanResult
from ._io import NativeFile, bounded_text, discover, mapping, safe_text, stable_id, string


class CodexAdapter:
    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()
        self.files = {}

    def _consume(self, file, offset, row):
        facts = file.facts
        payload = mapping(row.get("payload"))
        kind = row.get("type")
        if row.get("channel") in ("analysis", "reasoning", "thinking") or payload.get("channel") in ("analysis", "reasoning", "thinking"):
            return
        timestamp = string(row.get("timestamp")) or None
        evidence = f"{file.cursor.path}:{offset}: {kind}"
        if kind == "session_meta":
            source = mapping(payload.get("source"))
            subagent = mapping(source.get("subagent"))
            spawn = mapping(subagent.get("thread_spawn"))
            facts.update(
                identity=string(payload.get("id")), is_subagent="subagent" in source,
                parent=string(payload.get("parent_thread_id")) or string(spawn.get("parent_thread_id")),
                cwd=string(payload.get("cwd")), nickname=safe_text(payload.get("agent_nickname") or spawn.get("agent_nickname")),
                started=string(payload.get("timestamp")) or timestamp, meta_evidence=evidence,
            )
        elif kind == "turn_context":
            if isinstance(payload.get("model"), str):
                facts["model"] = safe_text(payload["model"])
        elif kind == "event_msg":
            etype = string(payload.get("type"))
            lifecycle = {"task_started": ("running", "started"), "task_complete": ("turn_complete", "result_available"),
                         "turn_aborted": ("interrupted", "failed"), "task_failed": ("failed", "failed")}
            if etype in lifecycle:
                status, event_kind = lifecycle[etype]
                facts.update(status=status, evidence=evidence + "/" + etype, activity=timestamp)
                facts["finished"] = timestamp if status != "running" else None
                file.events.append((offset, event_kind, timestamp, evidence + "/" + etype, string(payload.get("turn_id"))))
            elif etype == "user_message":
                facts.update(status="unknown", finished=None, activity=timestamp)
                if not facts.get("task"):
                    facts["task"] = bounded_text(safe_text(payload.get("message")))
            elif etype in ("agent_message", "item_completed"):
                facts["activity"] = timestamp
            elif etype == "token_count":
                usage = mapping(mapping(payload.get("info")).get("total_token_usage"))
                value = usage.get("total_tokens")
                if isinstance(value, int) and not isinstance(value, bool):
                    facts["tokens"] = value
        elif kind == "response_item" and payload.get("type") in ("function_call", "custom_tool_call"):
            if payload.get("channel") not in ("analysis", "reasoning", "thinking"):
                file.events.append((offset, "tool", timestamp, evidence + "/" + safe_text(payload.get("name")), string(payload.get("call_id"))))

    def scan(self) -> ScanResult:
        result = ScanResult()
        root = self.root / "sessions" if (self.root / "sessions").is_dir() else self.root
        for path in discover(root, "**/*.jsonl", "codex", result.diagnostics):
            self.files.setdefault(path, NativeFile(path, "codex"))
        for file in self.files.values():
            file.poll(result.diagnostics, self._consume)
        identities = {file.facts.get("identity"): file for file in self.files.values() if file.facts.get("identity")}
        def root_parent(identity):
            seen = set()
            while identity in identities and identity not in seen:
                seen.add(identity)
                parent = identities[identity].facts.get("parent")
                if not parent:
                    break
                identity = parent
            return identity
        executions = {}
        for identity, file in sorted(identities.items()):
            facts = file.facts
            if not facts.get("is_subagent"):
                continue
            parent = facts.get("parent")
            root_id = root_parent(identity)
            execution_id = "codex:execution:" + root_id
            cwd = facts.get("cwd", "")
            agent_id = "codex:" + identity
            agent = Agent(
                id=agent_id, source="codex", source_id=identity, session_id=identity,
                execution_id=execution_id, project_id=cwd or execution_id + ":unknown-project",
                name=facts.get("nickname") or safe_text(identity), parent_id="codex:" + parent if parent else None,
                provider="codex", model=facts.get("model"), status=facts.get("status", "unknown"), cwd=cwd,
                task=facts.get("task", ""),
                started_at=facts.get("started"), finished_at=facts.get("finished"), last_activity=facts.get("activity"),
                tokens=facts.get("tokens"), evidence=facts.get("evidence", "estado não confirmado; " + facts.get("meta_evidence", "")),
                output_path=str(file.cursor.path),
                result_path=str(file.cursor.path) if facts.get("status") == "turn_complete" else None)
            result.agents.append(agent)
            execution = executions.setdefault(execution_id, Execution(
                id=execution_id, title="Codex " + safe_text(root_id), source="codex", project_id=agent.project_id,
                project_name=safe_text(Path(cwd).name) if cwd else "não informado", project_path=cwd,
                session_id=root_id, leader_id="codex:" + root_id if root_id != identity else None, started_at=facts.get('started')))
            if agent.project_id not in execution.project_ids:
                execution.project_ids.append(agent.project_id)
            if parent:
                result.events.append(Event(
                    id="codex:" + stable_id(identity, "delegated", parent), kind="delegated", source="codex",
                    execution_id=execution_id, timestamp=facts.get("started"), actor_id="codex:" + parent,
                    target_id=agent_id, evidence=facts["meta_evidence"] + "/parent_thread_id"))
            for offset, kind, timestamp, evidence, native_id in file.events:
                result.events.append(Event(
                    id="codex:" + stable_id(identity, kind, native_id or [str(file.cursor.path), offset]),
                    kind=kind, source="codex", execution_id=execution_id, timestamp=timestamp,
                    actor_id=agent_id, evidence=evidence))
        result.executions = list(executions.values())
        result.events = list({event.id: event for event in result.events}.values())
        return result
