"""Synthetic source contracts: no real sessions or transcript contents."""
import importlib
import importlib.util
import json
import os
from pathlib import Path

import pytest


def adapter(name, *args, **kwargs):
    assert importlib.util.find_spec("alethe_tui.adapters"), "passive adapters are not implemented"
    return getattr(importlib.import_module("alethe_tui.adapters"), name)(*args, **kwargs)


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def append(path, *rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    return path


def wave(path, status="queued", **fields):
    put(path / "state.json", {"runId": "wave", "status": "running", "workers": {
        "writer": {"id": "writer", "status": status, "cwd": "/synthetic/project", **fields}}})
    put(path / "plan.json", {"title": "Synthetic wave", "workers": [{
        "id": "writer", "provider": "codex", "model": "synthetic-model", "task": "Build example"}]})
    return path


def codex_meta(identity="child", parent="parent", **fields):
    return {"type": "session_meta", "payload": {"id": identity, "cwd": "/synthetic/project",
        "source": {"subagent": {"thread_spawn": {"parent_thread_id": parent,
            "agent_path": "root/worker", "agent_nickname": "Example"}}}, **fields}}


def cevent(kind, **fields):
    return {"type": "event_msg", "timestamp": "2026-01-01T00:00:00Z",
            "payload": {"type": kind, **fields}}


def claude_row(identity="alpha", kind="assistant", stop=None, **fields):
    return {"type": kind, "agentId": identity, "isSidechain": True, "sessionId": "main",
            "cwd": "/synthetic/project", "uuid": fields.pop("uuid", "message-one"),
            "message": {"model": "synthetic-model", "stop_reason": stop,
                        "content": [{"type": "text", "text": "Public example"}]}, **fields}


def test_alethe_discovers_all_roots_standalone_and_multiple_waves(tmp_path):
    first = wave(tmp_path / "one" / "single")
    orchestration = tmp_path / "two" / "group"
    put(orchestration / "orchestration.json", {"title": "Group", "lead": {"provider": "codex"}})
    wave(orchestration / "wave-a")
    wave(orchestration / "wave-b")
    put(tmp_path / "two" / "current.json", {"path": str(first)})
    reader = adapter("AletheAdapter", [tmp_path / "one", tmp_path / "two", first], verify_pids=False)
    result = reader.scan()
    assert len(result.agents) == 3
    assert len({a.id for a in result.agents}) == 3
    assert len(result.executions) == 2
    assert {a.task for a in result.agents} == {"Build example"}
    assert all(a.tokens is None and a.cost_usd is None for a in result.agents)


def test_alethe_partial_json_preserves_last_valid_read_and_reports_missing_root(tmp_path):
    run = wave(tmp_path / "run", "running", startedAt="2026-01-01T00:00:00Z")
    reader = adapter("AletheAdapter", [run, tmp_path / "missing"], verify_pids=False)
    before = reader.scan()
    (run / "state.json").write_text('{"workers":')
    after = reader.scan()
    assert after.agents == before.agents
    assert {d["status"] for d in after.diagnostics} >= {"unavailable", "invalid"}


def test_alethe_dead_runner_interrupts_only_unfinished_workers_without_writing(tmp_path, monkeypatch):
    run = wave(tmp_path / "run", "running")
    state = json.loads((run / "state.json").read_text())
    state["runnerPid"] = 123456
    put(run / "state.json", state)
    before = (run / "state.json").read_bytes()
    def absent(pid, signal):
        assert (pid, signal) == (123456, 0)
        raise ProcessLookupError
    monkeypatch.setattr(os, "kill", absent)
    result = adapter("AletheAdapter", [run]).scan()
    assert result.agents[0].status == "interrupted"
    assert result.executions[0].status == "interrupted"
    assert (run / "state.json").read_bytes() == before
    assert result.agents[0].output_path is None


def test_alethe_pid_permission_is_not_dead_or_identity_proof(tmp_path, monkeypatch):
    run = wave(tmp_path / "run", "running")
    state = json.loads((run / "state.json").read_text())
    state["runnerPid"] = 12
    put(run / "state.json", state)
    def denied(*args):
        raise PermissionError
    monkeypatch.setattr(os, "kill", denied)
    result = adapter("AletheAdapter", [run]).scan()
    assert result.agents[0].status == "running"
    assert any(d["status"] == "unverifiable" for d in result.diagnostics)


def test_alethe_lifecycle_has_stable_evidence_and_never_infers_delivery(tmp_path):
    run = wave(tmp_path / "run", "running", startedAt="2026-01-01T00:00:00Z")
    reader = adapter("AletheAdapter", [run], verify_pids=False)
    first = reader.scan()
    put(run / "workers/writer/outcome.json", {"status": "succeeded", "finishedAt": "2026-01-01T01:00:00Z",
        "sessionId": "thread-synthetic", "metrics": {"usage": {"total_tokens": 42}, "totalCostUsd": 0.1}})
    put(run / "workers/writer/result.md", "Synthetic result")
    result = reader.scan()
    assert result.agents[0].status == "succeeded"
    assert result.agents[0].session_id == "thread-synthetic"
    assert (result.agents[0].tokens, result.agents[0].cost_usd) == (42, 0.1)
    assert {e.kind for e in result.events} >= {"started", "result_available"}
    assert "result_delivered" not in {e.kind for e in result.events}
    assert all(e.evidence and e.id for e in result.events)
    assert {e.id for e in first.events} <= {e.id for e in result.events}
    assert [e.id for e in result.events] == [e.id for e in reader.scan().events]


def test_codex_v167_parentage_root_grouping_and_terminal_event(tmp_path):
    append(tmp_path / "sessions/a.jsonl", codex_meta(), cevent("task_started", turn_id="turn-a"),
           cevent("task_complete", turn_id="turn-a", last_agent_message="Done"))
    append(tmp_path / "sessions/b.jsonl", codex_meta("grandchild", "child", parent_thread_id="child"))
    append(tmp_path / "sessions/main.jsonl", {"type": "session_meta", "payload": {"id": "parent", "source": "exec"}})
    reader = adapter("CodexAdapter", tmp_path)
    result = reader.scan()
    assert len(result.agents) == 2
    agents = {a.source_id: a for a in result.agents}
    assert agents["child"].parent_id == "codex:parent"
    assert agents["grandchild"].parent_id == agents["child"].id
    assert agents["child"].execution_id == agents["grandchild"].execution_id
    assert agents["child"].status == "turn_complete"
    assert agents["child"].result_path == agents["child"].output_path
    assert agents["grandchild"].status == "unknown"
    assert {e.kind for e in result.events} >= {"delegated", "started", "result_available"}
    assert "result_delivered" not in {e.kind for e in result.events}
    assert all(e.evidence for e in result.events)
    assert [e.id for e in reader.scan().events] == [e.id for e in result.events]


def test_codex_incremental_partial_line_truncation_and_rotation(tmp_path):
    path = append(tmp_path / "sessions/session.jsonl", codex_meta())
    reader = adapter("CodexAdapter", tmp_path)
    assert reader.scan().agents[0].status == "unknown"
    partial = json.dumps(cevent("task_started", turn_id="one"))
    with path.open("a") as handle:
        handle.write(partial[:40])
    assert reader.scan().agents[0].status == "unknown"
    with path.open("a") as handle:
        handle.write(partial[40:] + "\n")
    assert reader.scan().agents[0].status == "running"
    path.write_text(json.dumps(codex_meta()) + "\n")
    assert reader.scan().agents[0].status == "unknown"
    path.unlink()
    append(path, codex_meta(), cevent("task_complete", turn_id="two"))
    assert reader.scan().agents[0].status == "turn_complete"


def test_codex_large_file_reads_bounded_head_tail_and_skips_unknown_records(tmp_path, monkeypatch):
    path = append(tmp_path / "sessions/large.jsonl", codex_meta())
    with path.open("a") as handle:
        handle.write(json.dumps({"type": "reasoning", "text": "x" * 200_000}) + "\n")
    append(path, cevent("task_complete", turn_id="last"))
    original = Path.open
    reads = []
    class Guard:
        def __init__(self, handle): self.handle = handle
        def __enter__(self): return self
        def __exit__(self, *args): self.handle.close()
        def read(self, count=-1):
            assert 0 <= count <= 65536, "unbounded source read"
            data = self.handle.read(count)
            reads.append(len(data))
            return data
        def __getattr__(self, key): return getattr(self.handle, key)
    def guarded(self, *args, **kwargs):
        handle = original(self, *args, **kwargs)
        return Guard(handle) if self == path else handle
    monkeypatch.setattr(Path, "open", guarded)
    reader = adapter("CodexAdapter", tmp_path)
    first = reader.scan()
    assert first.agents[0].status == "turn_complete"
    assert any(d["status"] == "limited" for d in first.diagnostics)
    assert sum(reads) <= 65536
    reads.clear()
    assert reader.scan().agents == first.agents
    assert sum(reads) <= 256


def test_native_sources_survive_missing_root_invalid_json_and_wrong_shapes(tmp_path):
    for name in ("ClaudeAdapter", "CodexAdapter"):
        result = adapter(name, tmp_path / "missing").scan()
        assert not result.agents
        assert result.diagnostics[0]["status"] == "unavailable"
    path = tmp_path / "sessions/broken.jsonl"
    path.parent.mkdir()
    path.write_text('null\n[]\n{"type":"session_meta","payload":[]}\n{bad}\n')
    append(path, codex_meta())
    assert len(adapter("CodexAdapter", tmp_path).scan().agents) == 1


def test_claude_two_agents_resume_identity_and_no_mtime_activity(tmp_path):
    folder = tmp_path / "projects/example/main/subagents"
    path = append(folder / "agent-alpha.jsonl", claude_row(stop="end_turn"))
    append(folder / "agent-beta.jsonl", claude_row("beta", uuid="message-beta"))
    put(path.with_suffix(".meta.json"), {"agentType": "reviewer", "toolUseId": "tool-alpha", "spawnDepth": 1})
    reader = adapter("ClaudeAdapter", tmp_path)
    first = reader.scan()
    agents = {a.source_id: a for a in first.agents}
    assert len(agents) == 2
    assert agents["alpha"].status == "turn_complete"
    assert agents["alpha"].result_path == str(path)
    assert agents["beta"].status == "unknown"
    assert agents["alpha"].parent_id == "claude:main"
    assert agents["alpha"].model == "synthetic-model"
    path.touch()
    assert reader.scan().agents == first.agents
    append(path, claude_row(kind="user", uuid="resume-message"))
    resumed = {a.source_id: a for a in reader.scan().agents}["alpha"]
    assert resumed.id == agents["alpha"].id
    assert resumed.status == "unknown"
    assert resumed.result_path is None


def test_claude_tool_link_proves_delegation_and_delivery_only_after_parent_result(tmp_path):
    folder = tmp_path / "projects/example/main"
    child = append(folder / "subagents/agent-alpha.jsonl", claude_row(stop="end_turn"))
    put(child.with_suffix(".meta.json"), {"agentType": "reviewer", "toolUseId": "tool-alpha"})
    parent = append(folder.parent / "main.jsonl", {"type": "assistant", "sessionId": "main", "uuid": "spawn",
        "message": {"content": [{"type": "tool_use", "id": "tool-alpha", "name": "Agent", "input": {"prompt": "Check example"}}]}})
    reader = adapter("ClaudeAdapter", tmp_path)
    first = reader.scan()
    delegated = [e for e in first.events if e.kind == "delegated"]
    assert len(delegated) == 1 and delegated[0].actor_id == "claude:main"
    assert not [e for e in first.events if e.kind == "result_delivered"]
    append(parent, {"type": "user", "sessionId": "main", "uuid": "receive",
        "message": {"content": [{"type": "tool_result", "tool_use_id": "tool-alpha", "content": "Done"}]}})
    after = reader.scan()
    delivered = [e for e in after.events if e.kind == "result_delivered"]
    assert len(delivered) == 1
    assert delivered[0].actor_id == after.agents[0].id
    assert delivered[0].target_id == "claude:main"
    assert delivered[0].evidence
    assert [e.id for e in after.events] == [e.id for e in reader.scan().events]


@pytest.mark.parametrize("kind,status", [("task_started", "running"), ("turn_aborted", "interrupted"),
                                         ("task_complete", "turn_complete"), ("unrecognized", "unknown")])
def test_codex_status_requires_explicit_public_lifecycle(tmp_path, kind, status):
    append(tmp_path / "sessions/x.jsonl", codex_meta(), cevent(kind, turn_id="one"))
    assert adapter("CodexAdapter", tmp_path).scan().agents[0].status == status


def test_native_same_inode_rewrite_larger_than_tail_preserves_fresh_metadata(tmp_path):
    path = append(tmp_path / "sessions/x.jsonl", codex_meta(), cevent("task_started", turn_id="old"))
    reader = adapter("CodexAdapter", tmp_path)
    assert reader.scan().agents[0].source_id == "child"
    path.write_text(json.dumps(codex_meta("replacement")) + "\n" + '{"ignored":"' + "x" * 80000 + '"}\n')
    append(path, cevent("task_complete", turn_id="new"))
    after = reader.scan()
    assert len(after.agents) == 1 and after.agents[0].source_id == "replacement"
    assert after.agents[0].status == "turn_complete"


def test_native_dense_tail_does_not_discard_identity_metadata(tmp_path):
    path = append(tmp_path / "sessions/x.jsonl", codex_meta())
    with path.open("a") as handle:
        handle.write('{}\n' * 30000)
    append(path, cevent("task_complete", turn_id="last"))
    result = adapter("CodexAdapter", tmp_path).scan()
    assert len(result.agents) == 1 and result.agents[0].status == "turn_complete"


def test_codex_unavailable_transcript_preserves_observation_and_recovers(tmp_path):
    path = append(tmp_path / "sessions/x.jsonl", codex_meta(), cevent("task_complete", turn_id="one"))
    reader = adapter("CodexAdapter", tmp_path)
    before = reader.scan()
    path.unlink()
    after = reader.scan()
    assert after.agents == before.agents
    assert any(d["status"] == "unavailable" for d in after.diagnostics)
    append(path, codex_meta(), cevent("task_started", turn_id="two"))
    assert reader.scan().agents[0].status == "running"


def test_alethe_invalid_worker_collection_preserves_valid_state(tmp_path):
    run = wave(tmp_path / "run")
    reader = adapter("AletheAdapter", [run], verify_pids=False)
    before = reader.scan()
    put(run / "state.json", {"status": "running", "workers": []})
    after = reader.scan()
    assert after.agents == before.agents
    assert any(d["status"] == "invalid" for d in after.diagnostics)


def test_alethe_unrecognized_unhashable_status_does_not_crash(tmp_path):
    run = wave(tmp_path / "run", ["invalid"])
    result = adapter("AletheAdapter", [run], verify_pids=False).scan()
    assert result.agents[0].status == "unknown"


def test_claude_nested_tool_link_proves_intermediate_parent(tmp_path):
    folder = tmp_path / "projects/project/main/subagents"
    alpha = append(folder / "agent-alpha.jsonl", claude_row())
    beta = append(folder / "agent-beta.jsonl", claude_row("beta"))
    put(alpha.with_suffix(".meta.json"), {"toolUseId": "root-tool", "spawnDepth": 1})
    put(beta.with_suffix(".meta.json"), {"toolUseId": "nested-tool", "spawnDepth": 2})
    append(alpha, {**claude_row(uuid="nested-spawn"), "message": {"content": [
        {"type": "tool_use", "name": "Agent", "id": "nested-tool", "input": {}}]}})
    result = adapter("ClaudeAdapter", tmp_path).scan()
    agents = {a.source_id: a for a in result.agents}
    assert agents["beta"].parent_id == agents["alpha"].id
    assert [e for e in result.events if e.kind == "delegated"][0].actor_id == agents["alpha"].id


def test_claude_private_tool_blocks_do_not_create_public_events(tmp_path):
    path = tmp_path / "projects/example/main/subagents/agent-alpha.jsonl"
    append(path, {**claude_row(), "message": {"channel": "analysis", "content": [
        {"type": "tool_use", "name": "Agent", "id": "private-tool"}]}})
    assert not adapter("ClaudeAdapter", tmp_path).scan().events


def test_event_ids_deduplicate_repeated_native_message_ids(tmp_path):
    path = tmp_path / "projects/example/main/subagents/agent-alpha.jsonl"
    append(path, claude_row(stop="end_turn"), claude_row(stop="end_turn"))
    events = adapter("ClaudeAdapter", tmp_path).scan().events
    assert len(events) == 1


def test_native_sources_have_per_file_error_isolation(tmp_path):
    append(tmp_path / "sessions/bad.jsonl", {"type": "event_msg", "payload": {"type": []}})
    append(tmp_path / "sessions/good.jsonl", codex_meta())
    result = adapter("CodexAdapter", tmp_path).scan()
    assert len(result.agents) == 1


def test_native_partial_replacement_preserves_last_valid_observation_until_identity_recovers(tmp_path):
    path = append(tmp_path / "sessions/x.jsonl", codex_meta(), cevent("task_complete", turn_id="one"))
    reader = adapter("CodexAdapter", tmp_path)
    before = reader.scan()
    replacement = json.dumps(codex_meta("new-child"))
    path.write_text(replacement[:30])
    assert reader.scan().agents == before.agents
    with path.open("a") as handle:
        handle.write(replacement[30:] + "\n")
    after = reader.scan()
    assert [a.source_id for a in after.agents] == ["new-child"]
    assert after.agents[0].status == "unknown"


def test_native_oversized_appended_line_is_skipped_then_complete_event_is_read(tmp_path):
    path = append(tmp_path / "sessions/x.jsonl", codex_meta())
    reader = adapter("CodexAdapter", tmp_path)
    reader.scan()
    with path.open("a") as handle:
        handle.write(json.dumps({"type": "reasoning", "text": "x" * 200000}) + "\n")
    append(path, cevent("task_started", turn_id="last"))
    first = reader.scan()
    assert first.agents[0].status == "unknown"
    for _ in range(4):
        final = reader.scan()
    assert final.agents[0].status == "running"


def test_alethe_bounds_historical_executions_but_keeps_all_explicitly_active(tmp_path):
    for index in range(55):
        run = wave(tmp_path / f"old-{index:03}", "succeeded")
        state = json.loads((run / "state.json").read_text())
        state.update(status="done", startedAt=f"2026-01-{index % 28 + 1:02}T00:00:00Z")
        put(run / "state.json", state)
    wave(tmp_path / "active", "running")
    result = adapter("AletheAdapter", [tmp_path], verify_pids=False).scan()
    assert len(result.executions) == 51
    assert len([a for a in result.agents if a.status == "running"]) == 1


def test_codex_duplicate_turn_completion_has_one_event_even_at_new_offset(tmp_path):
    append(tmp_path / "sessions/x.jsonl", codex_meta(), cevent("task_complete", turn_id="one"),
           cevent("task_complete", turn_id="one"))
    result = adapter("CodexAdapter", tmp_path).scan()
    assert len([e for e in result.events if e.kind == "result_available"]) == 1


def test_claude_tool_result_error_is_not_successful_result_delivery(tmp_path):
    folder = tmp_path / "projects/example/main"
    child = append(folder / "subagents/agent-alpha.jsonl", claude_row())
    put(child.with_suffix(".meta.json"), {"toolUseId": "tool-alpha"})
    append(folder.parent / "main.jsonl", {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Agent", "id": "tool-alpha"}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "tool-alpha", "is_error": True, "content": "Agent launch failed"}]}})
    assert not [e for e in adapter("ClaudeAdapter", tmp_path).scan().events if e.kind == "result_delivered"]


def test_native_public_task_text_is_available_without_private_blocks(tmp_path):
    append(tmp_path / "codex/sessions/x.jsonl", codex_meta(), cevent("user_message", message="Public task <think>PRIVATE</think>"))
    append(tmp_path / "claude/projects/example/main/subagents/agent-alpha.jsonl", {
        **claude_row(kind="user"), "message": {"content": [
            {"type": "thinking", "thinking": "PRIVATE"}, {"type": "text", "text": "Public task"}]}})
    for name, root in (("CodexAdapter", tmp_path / "codex"), ("ClaudeAdapter", tmp_path / "claude")):
        result = adapter(name, root).scan()
        assert result.agents[0].task.strip() == "Public task"


def test_claude_analysis_blocks_do_not_prove_child_delegation(tmp_path):
    folder = tmp_path / "projects/example/main"
    child = append(folder / "subagents/agent-alpha.jsonl", claude_row())
    put(child.with_suffix(".meta.json"), {"toolUseId": "tool-alpha"})
    append(folder.parent / "main.jsonl", {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "channel": "analysis", "name": "Agent", "id": "tool-alpha"}]}})
    assert not [e for e in adapter("ClaudeAdapter", tmp_path).scan().events if e.kind == "delegated"]


def test_claude_background_launch_acknowledgement_is_not_result_delivery(tmp_path):
    folder = tmp_path / "projects/example/main"
    child = append(folder / "subagents/agent-alpha.jsonl", claude_row())
    put(child.with_suffix(".meta.json"), {"toolUseId": "tool-alpha"})
    append(folder.parent / "main.jsonl", {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Agent", "id": "tool-alpha", "input": {"run_in_background": True}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "tool-alpha", "content": "Async agent launched"}]}})
    result = adapter("ClaudeAdapter", tmp_path).scan()
    assert [e for e in result.events if e.kind == "delegated"]
    assert not [e for e in result.events if e.kind == "result_delivered"]
