from copy import deepcopy
from datetime import datetime, timezone
import subprocess

import pytest

from alethe_tui.model import Agent, Event, Execution, ScanResult
from alethe_tui.monitor import Monitor
from alethe_tui.config import load_config
from alethe_tui.monitor import resolve_project


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


def test_late_session_correlation_updates_existing_events(tmp_path):
    a = batch(tmp_path, 'alpha')
    child = batch(tmp_path, 'beta', 'codex', session='shared')
    child.events = [Event('stable-event','delegated','codex','beta',actor_id='lead:beta',target_id='agent:beta')]
    feed = Feed(a)
    monitor = Monitor([feed,Feed(child)])
    monitor.refresh()
    a.agents[0].session_id = 'shared'
    feed.result = a
    result = monitor.refresh()
    assert result['events'][0]['execution_id'] == 'alpha'
    assert result['events'][0]['actor_id'] == 'agent:alpha'
    assert result['events'][0]['id'] == 'stable-event'


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


@pytest.mark.parametrize('suffix', [
    '.alethe/worktrees/skill-example-writer',
    '.alethe/worktrees/skill-example-writer/src',
    '.alethe/worktrees/skill-example-writer/.alethe/worktrees/skill-nested-reviewer',
])
def test_removed_alethe_worktrees_belong_to_their_original_project(tmp_path, suffix):
    root = tmp_path / 'project'
    root.mkdir()
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    source = batch(tmp_path, 'project')
    source.agents[0].cwd = str(root / suffix)
    source.executions[0].project_path = str(root / suffix)
    data = Monitor([Feed(source)]).refresh()
    assert data['projects'] == [{'id': str(root), 'name': 'project', 'path': str(root)}]
    assert data['agents'][0]['cwd'] == str(root / suffix)
    assert data['agents'][0]['project_id'] == str(root)
    assert data['executions'][0]['project_ids'] == [str(root)]


def test_removed_alethe_worktree_keeps_original_project_when_repository_is_gone(tmp_path):
    root = tmp_path / 'removed-project'
    assert resolve_project(str(root / '.alethe/worktrees/skill-example-writer')) == str(root)


def test_skill_prefix_alone_does_not_merge_unrelated_projects(tmp_path):
    first = tmp_path / 'skill-example-writer'
    second = tmp_path / 'skill-example-reviewer'
    assert resolve_project(str(first)) == str(first)
    assert resolve_project(str(second)) == str(second)


def test_existing_git_worktrees_use_common_repository(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Synthetic',
                    '-c', 'user.email=synthetic@example.invalid', 'commit', '-qm', 'Initial', '--allow-empty'], check=True)
    worktree = tmp_path / 'separate-worktree'
    subprocess.run(['git', '-C', str(root), 'worktree', 'add', '-q', '--detach', str(worktree)], check=True)
    assert resolve_project(str(worktree)) == str(root)


def test_project_directories_filter_snapshot_from_all_sources(tmp_path):
    projects = tmp_path / 'projects'
    projects.mkdir()
    other = tmp_path / 'other'
    other.mkdir()
    feeds = [Feed(batch(projects, 'alpha')), Feed(batch(other, 'beta', 'claude')),
             Feed(batch(tmp_path, 'projects-copy', 'codex'))]
    data = Monitor(feeds, project_dirs=[projects, other]).refresh()
    assert {p['name'] for p in data['projects']} == {'alpha', 'beta'}
    assert {e['id'] for e in data['executions']} == {'alpha', 'beta'}
    assert data['totals']['agents'] == 2
    assert data['totals']['running'] == 2
    assert data['totals']['active_executions'] == 2


def test_multi_project_execution_keeps_only_projects_in_configured_directories(tmp_path):
    allowed = tmp_path / 'allowed'
    allowed.mkdir()
    source = batch(tmp_path, 'excluded')
    child = batch(allowed, 'included', 'claude')
    child.agents[0].execution_id = 'excluded'
    source.agents.extend(child.agents)
    source.events = [
        Event('excluded-event', 'started', 'alethe', 'excluded', actor_id='agent:excluded'),
        Event('included-event', 'started', 'claude', 'excluded', actor_id='agent:included'),
    ]
    data = Monitor([Feed(source)], project_dirs=[allowed]).refresh()
    assert [a['id'] for a in data['agents']] == ['agent:included']
    assert data['executions'][0]['project_ids'] == [str(allowed / 'included')]
    assert data['executions'][0]['project_name'] == 'included'
    assert [e['id'] for e in data['events']] == ['included-event']


def test_project_directories_with_no_matches_produce_empty_snapshot(tmp_path):
    data = Monitor([Feed(batch(tmp_path))], project_dirs=[tmp_path / 'elsewhere']).refresh()
    assert data['projects'] == data['executions'] == data['agents'] == []
    assert data['totals']['active_executions'] == 0


def test_snapshot_contains_task_summary_while_detail_preserves_full_task(tmp_path):
    source = batch(tmp_path)
    source.agents[0].task = 'Task 8: ' + 'Acceptance details. ' * 100
    monitor = Monitor([Feed(source)])
    data = monitor.refresh()
    assert len(data['agents'][0]['task']) <= 280
    assert monitor.detail('agent:alpha', 'task') == source.agents[0].task


def test_native_token_metrics_fill_missing_alethe_metrics_without_duplicate_agent(tmp_path):
    source=batch(tmp_path,'alpha')
    source.agents[0].session_id='shared'
    native=batch(tmp_path,'beta','codex',session='shared')
    native.agents[0].session_id='shared'
    native.agents[0].tokens=123
    data=Monitor([Feed(source),Feed(native)]).refresh()
    assert len(data['agents']) == 1
    assert data['agents'][0]['tokens'] == 123


def test_resumed_worker_session_does_not_attribute_cumulative_native_tokens_to_one_wave(tmp_path):
    first=batch(tmp_path,'alpha')
    second=batch(tmp_path,'second')
    native=batch(tmp_path,'beta','codex',session='shared')
    for source in [first,second,native]:
        source.agents[0].session_id='shared'
    native.agents[0].tokens=123
    data=Monitor([Feed(first),Feed(second),Feed(native)]).refresh()
    assert len(data['agents']) == 2
    assert all(a['tokens'] is None for a in data['agents'])
