import json
from pathlib import Path

from alethe_tui.adapters import AletheAdapter, CodexAdapter


def test_codex_large_realistic_metadata_line_does_not_hide_subagent(tmp_path):
    root = tmp_path / "sessions"
    root.mkdir()
    path = root / "rollout.jsonl"
    meta = {"type": "session_meta", "payload": {"id": "child", "cwd": str(tmp_path), "base_instructions": "x" * 22000, "source": {"subagent": {"thread_spawn": {"parent_thread_id": "parent"}}}}}
    filler = {"type": "unused", "payload": "x" * 60000}
    done = {"type": "event_msg", "timestamp": "2026-11-10T00:00:00Z", "payload": {"type": "task_complete", "turn_id": "turn-1"}}
    path.write_text("\n".join(json.dumps(x) for x in [meta, filler, done]) + "\n")
    result = CodexAdapter(root).scan()
    assert len(result.agents) == 1
    assert result.agents[0].source_id == "child"
    assert result.agents[0].status == "turn_complete"


def test_alethe_generic_orchestrator_can_delegate_without_fake_lead_identity(tmp_path):
    group = tmp_path / "orchestration"
    wave = group / "01-build"
    wave.mkdir(parents=True)
    (group / "orchestration.json").write_text(json.dumps({"title": "Example", "lead": {"provider": "codex"}}))
    (wave / "state.json").write_text(json.dumps({"status": "running", "startedAt": "2026-11-10T00:00:00Z", "workers": {"worker": {"status": "running", "cwd": str(tmp_path)}}}))
    (wave / "plan.json").write_text(json.dumps({"workers": [{"id": "worker", "task": "Work"}]}))
    result = AletheAdapter([group], verify_pids=False).scan()
    execution = result.executions[0]
    assert execution.leader_id
    assert execution.leader_name == "orquestrador"
    assert execution.leader_status == "unknown"
    event = next(event for event in result.events if event.kind == "delegated")
    assert event.actor_id == execution.leader_id
    assert event.target_id == result.agents[0].id


def test_orphan_codex_subagent_is_not_mistaken_for_its_own_leader(tmp_path):
    path = tmp_path / "rollout.jsonl"
    path.write_text(json.dumps({"type": "session_meta", "payload": {"id": "orphan", "source": {"subagent": {"review": {}}}, "cwd": str(tmp_path)}}) + "\n")
    result = CodexAdapter(tmp_path).scan()
    assert result.agents[0].parent_id is None
    assert result.executions[0].leader_id != result.agents[0].id
