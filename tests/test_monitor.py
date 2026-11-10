from copy import deepcopy
from datetime import datetime, timezone

import pytest

from alethe_tui.model import Agent, Event, Execution, ScanResult
from alethe_tui.monitor import Monitor
from alethe_tui.config import load_config


class Feed:
    def __init__(self, result):
        self.result = result

    def scan(self):
        if isinstance(self.result, Exception):
            raise self.result
        return deepcopy(self.result)


def batch(tmp_path, name="alpha", source="alethe", session=None):
    root = tmp_path / name
    root.mkdir(exist_ok=True)
    execution = Execution(name, name, source, str(root), name, str(root), status="running", session_id=session, leader_id=f"lead:{name}")
    actor = Agent(f"agent:{name}", source, "same-name", name, str(root), "same-name", status="running", cwd=str(root), parent_id=execution.leader_id)
    return ScanResult([actor], [execution])


def test_multiple_projects_and_same_agent_names_remain_distinct(tmp_path):
    a = Feed(batch(tmp_path, "alpha"))
    b = Feed(batch(tmp_path, "beta", "claude"))
    monitor = Monitor([a, b])
    data = monitor.refresh()
    assert data["totals"]["projects"] == 2
    assert data["totals"]["agents"] == 2
    assert len({a["id"] for a in data["agents"]}) == 2
    assert data["totals"]["running"] == 2


def test_snapshot_is_detached_and_scan_failure_keeps_last_data(tmp_path):
    feed = Feed(batch(tmp_path))
    monitor = Monitor([feed])
    first = monitor.refresh()
    first["agents"][0]["name"] = "mutated"
    assert monitor.snapshot()["agents"][0]["name"] == "same-name"
    feed.result = OSError("temporarily unreadable")
    data = monitor.refresh()
    assert len(data["agents"]) == 1
    assert any("temporarily unreadable" in d["message"] for d in data["diagnostics"])


def test_proven_session_correlation_keeps_child_under_alethe_worker(tmp_path):
    a = batch(tmp_path, "alpha")
    a.agents[0].session_id = "shared-session"
    child = batch(tmp_path, "beta", "claude", session="shared-session")
    data = Monitor([Feed(a), Feed(child)]).refresh()
    assert len(data["executions"]) == 1
    children = {x["id"]: x for x in data["agents"]}
    assert children["agent:beta"]["parent_id"] == "agent:alpha"
    assert children["agent:beta"]["execution_id"] == "alpha"


def test_missing_metric_is_not_zero(tmp_path):
    data = Monitor([Feed(batch(tmp_path))]).refresh()
    assert data["agents"][0]["tokens"] is None
    assert data["agents"][0]["cost_usd"] is None


def test_initial_and_late_historical_events_do_not_become_live(tmp_path):
    source = batch(tmp_path)
    source.events = [Event("old-1", "delegated", "alethe", "alpha", "2020-01-01T00:00:00Z", "lead:alpha", "agent:alpha")]
    feed = Feed(source)
    monitor = Monitor([feed])
    assert not monitor.refresh()["events"][0]["is_live"]
    source.events.append(Event("old-2", "delegated", "alethe", "alpha", "2020-01-02T00:00:00Z"))
    feed.result = source
    assert not monitor.refresh()["events"][-1]["is_live"]
    source.events.append(Event("new-1", "delegated", "alethe", "alpha", datetime.now(timezone.utc).isoformat()))
    feed.result = source
    assert monitor.refresh()["events"][-1]["is_live"]
    assert len(monitor.refresh()["events"]) == 3


def test_config_honors_env_and_extra_roots(tmp_path):
    env = {"HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path / "config"), "CODEX_HOME": str(tmp_path / "codex"), "CLAUDE_CONFIG_DIR": str(tmp_path / "claude"), "ALETHE_ORCHESTRATE_HOME": str(tmp_path / "custom")}
    config = load_config(path=tmp_path / "none.toml", environ=env, roots=[tmp_path / "extra"])
    assert tmp_path / "config/alethe/orchestrations" in config.roots
    assert tmp_path / "custom" in config.roots
    assert tmp_path / "extra" in config.roots
    assert config.codex_root == tmp_path / "codex/sessions"
    assert config.claude_root == tmp_path / "claude/projects"


def test_invalid_config_interval_is_actionable(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("interval = -1\n")
    with pytest.raises(ValueError, match="interval"):
        load_config(path=config)
