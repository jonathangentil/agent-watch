"""Behavioral QA checks for the stage 2 Kanban backend contract."""
from copy import deepcopy
from unittest.mock import Mock

from alethe_tui import cli
from alethe_tui.demo import Demo
from alethe_tui.model import Agent, Execution, ScanResult
from alethe_tui.monitor import Monitor


class Source:
    def __init__(self, result):
        self.result = result

    def scan(self):
        return deepcopy(self.result)


def synthetic_run(tmp_path, name="qa-run", *, status="succeeded", task="A synthetic task"):
    path = str(tmp_path / name)
    agent = Agent("agent:" + name, "alethe", "dev-core", name, path, "Developer",
                  status=status, cwd=path, task=task, contract="developer")
    execution = Execution(name, name, "alethe", path, name, path, status=status)
    return ScanResult(agents=[agent], executions=[execution])


def test_snapshot_task_records_are_serialized_board_tasks(tmp_path):
    result = synthetic_run(tmp_path, task="Task: " + "synthetic detail " * 40)
    snapshot = Monitor([Source(result)]).refresh()
    assert snapshot["version"] == 1
    assert isinstance(snapshot["tasks"], list) and len(snapshot["tasks"]) == 1
    task = snapshot["tasks"][0]
    assert {"id", "agent_id", "execution_id", "column", "title"} <= task.keys()
    assert task["title"] == snapshot["agents"][0]["task"]
    assert len(task["title"]) <= 280


def test_task_collection_obeys_project_filter_and_history_retention(tmp_path):
    root = tmp_path / "included"
    sources = [synthetic_run(root, f"run-{i:02}") for i in range(52)]
    sources.append(synthetic_run(tmp_path / "excluded", "outside"))
    for i, source in enumerate(sources):
        source.executions[0].started_at = f"2026-11-11T10:00:{i:02}Z"
    snapshot = Monitor([Source(s) for s in sources], project_dirs=[root]).refresh()
    retained = {execution["id"] for execution in snapshot["executions"]}
    assert len(retained) == 50
    assert "outside" not in retained and "run-00" not in retained
    assert {task["execution_id"] for task in snapshot["tasks"]} == retained


def test_empty_monitor_always_publishes_an_empty_task_list():
    monitor = Monitor([])
    assert monitor.snapshot()["tasks"] == []
    assert monitor.refresh()["tasks"] == []


def test_cli_kanban_selection_opens_matching_url(monkeypatch):
    from alethe_tui import server
    instance = Mock()
    instance.start.return_value = instance
    instance.url.side_effect = lambda *, view: f"http://localhost/?view={view}"
    monkeypatch.setattr(server, "LocalServer", Mock(return_value=instance))
    opened = Mock(return_value=True)
    monkeypatch.setattr(cli, "open_browser", opened)
    monkeypatch.setattr(cli.threading.Event, "wait", Mock(side_effect=KeyboardInterrupt))
    monkeypatch.setattr(cli, "build_monitor", Mock(return_value=Mock()))
    monkeypatch.setattr(Demo, "start", lambda self: None)
    assert cli.main(["--demo", "--web", "--kanban"]) == 0
    opened.assert_called_once_with("http://localhost/?view=kanban")


def test_demo_moves_synthetic_task_to_next_column(tmp_path, monkeypatch):
    demo = Demo()
    try:
        monitor = cli.build_monitor(__import__("alethe_tui.config", fromlist=["Config"]).Config(
            [demo.alethe_root], demo.claude_root, demo.codex_root))
        before = monitor.refresh()
        assert {"blocked", "in_progress", "done"} <= {task["column"] for task in before["tasks"]}
        assert any(task["column"] == "blocked" and "superseded" in task["badges"]
                   for task in before["tasks"])
        actor = next(agent for agent in before["agents"]
                     if agent["source_id"] == "dev-core" and agent["wave_index"] == 3)
        task = next(task for task in before["tasks"] if task["agent_id"] == actor["id"])
        assert task["column"] == "in_progress"
        moving_task_id = task["id"]
        demo.advance()
        after = next(current for current in monitor.refresh()["tasks"] if current["id"] == moving_task_id)
        assert after["column"] == "awaiting_tests"
    finally:
        demo.close()
