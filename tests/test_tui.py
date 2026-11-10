from dataclasses import replace

from textual.widgets import DataTable, Input, Select

from alethe_tui.model import Agent, Execution, ScanResult
from alethe_tui.monitor import Monitor
from alethe_tui.tui import AgentApp


class Feed:
    def __init__(self, root):
        execution = Execution("run-a", "Trabalho A", "alethe", str(root), "Projeto", str(root), status="running")
        actor = Agent("a", "alethe", "a", "run-a", str(root), "dev-core", status="running", cwd=str(root))
        self.result = ScanResult([actor, replace(actor, id="b", source_id="b", name="reviewer", status="succeeded")], [execution])

    def scan(self):
        return self.result


async def test_refresh_keeps_selected_agent_and_search(tmp_path):
    feed = Feed(tmp_path)
    monitor = Monitor([feed])
    monitor.refresh()
    app = AgentApp(monitor)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        table = app.query_one("#agents", DataTable)
        assert table.row_count == 2
        table.focus()
        await pilot.press("down")
        await pilot.pause()
        assert app.selected_agent_id == "b"

        feed.result.agents[0].status = "succeeded"
        monitor.refresh()
        app.sync_snapshot()
        await pilot.pause()
        assert app.selected_agent_id == "b"
        search = app.query_one("#search", Input)
        search.value = "reviewer"
        await pilot.pause()
        assert table.row_count == 1
        assert app.selected_agent_id == "b"


async def test_empty_sources_and_active_filter(tmp_path):
    monitor = Monitor([])
    app = AgentApp(monitor)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert app.query_one("#agents", DataTable).row_count == 0
        await pilot.press("a")
        await pilot.press("q")
    assert not app.is_running


async def test_project_and_execution_choices_are_explicit(tmp_path):
    feed = Feed(tmp_path)
    second = tmp_path / "other"
    second.mkdir()
    feed.result.executions.append(Execution("run-b", "Trabalho B", "codex", str(second), "Outro", str(second)))
    feed.result.agents.append(Agent("c", "codex", "c", "run-b", str(second), "reviewer", cwd=str(second)))
    monitor = Monitor([feed])
    monitor.refresh()
    app = AgentApp(monitor)
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause()
        app.query_one("#project", Select).value = str(second)
        await pilot.pause()
        assert app.query_one("#execution", Select).value == "run-b"
        assert app.query_one("#agents", DataTable).row_count == 1
        assert app.selected_agent_id == "c"


async def test_quick_selection_then_close_has_no_unawaited_detail(tmp_path, recwarn):
    import gc
    monitor = Monitor([Feed(tmp_path)])
    monitor.refresh()
    app = AgentApp(monitor)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        table = app.query_one("#agents", DataTable)
        for _ in range(8):
            table.move_cursor(row=1)
            table.move_cursor(row=0)
        await pilot.press("q")
    gc.collect()
    assert not [w for w in recwarn if "never awaited" in str(w.message)]
