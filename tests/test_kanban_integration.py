"""Synthetic end-to-end coverage of the board snapshot, CLI and demo."""
from copy import deepcopy
from unittest.mock import Mock

from alethe_tui import cli
from alethe_tui.config import Config
from alethe_tui.demo import Demo
from alethe_tui.model import Agent, Event, Execution, Gate, ScanResult
from alethe_tui.monitor import Monitor


class Feed:
    def __init__(self, result):
        self.result = result

    def scan(self):
        return deepcopy(self.result)


def batch(root, name='run', source='alethe', status='succeeded'):
    path = str(root / name)
    actor = Agent('agent:' + name, source, 'dev-core', name, path, 'Developer',
                  status=status, cwd=path, task='Task: ' + 'synthetic description ' * 40,
                  contract='developer', wave_index=1, has_diff=True)
    execution = Execution(name, name, source, path, name, path, status=status)
    return ScanResult(agents=[actor], executions=[execution])


def test_snapshot_publishes_tasks_from_board(tmp_path):
    source = batch(tmp_path)
    tester = Agent('qa', 'alethe', 'qa-1', 'run', source.agents[0].project_id, 'QA',
                   status='succeeded', contract='qa', wave_index=2, revision='rev-demo')
    source.agents.append(tester)
    source.gates.append(Gate('run', 1, 'APPROVED', revision='rev-demo',
                             developers=['dev-core'], qa=['qa-1'], evidence='synthetic gate'))
    monitor = Monitor([Feed(source)])
    data = monitor.refresh()
    assert data['version'] == 1
    assert len(data['tasks']) == 1
    assert data['tasks'][0]['column'] == 'done'
    assert data['tasks'][0]['gate'] == 1
    assert data['tasks'][0]['title'] == data['agents'][0]['task']
    assert len(data['tasks'][0]['title']) <= 280
    assert data['tasks'][0]['testers'] == ['qa']
    assert data['tasks'][0]['badges'] == ['link_confirmed']
    assert data['tasks'][0]['transitions'][-1]['column'] == 'done'
    assert monitor.detail('agent:run', 'task') == source.agents[0].task
    data['tasks'].clear()
    assert monitor.snapshot()['tasks']


def test_tasks_follow_retention_and_project_filter(tmp_path):
    sources = [batch(tmp_path / 'allowed', f'{i:02}') for i in range(52)]
    sources.append(batch(tmp_path / 'excluded', 'other'))
    sources.append(batch(tmp_path / 'allowed', 'active', status='running'))
    for index, source in enumerate(sources):
        source.executions[0].started_at = f'2026-11-11T10:00:{index:02}Z'
        source.gates = [Gate(source.executions[0].id, 1, 'APPROVED')]
    data = Monitor([Feed(s) for s in sources], project_dirs=[tmp_path / 'allowed']).refresh()
    retained = {e['id'] for e in data['executions']}
    assert len(retained) == 51
    assert 'active' in retained and 'other' not in retained and '00' not in retained
    assert {t['execution_id'] for t in data['tasks']} == retained
    assert {t['agent_id'] for t in data['tasks']} == {a['id'] for a in data['agents']}


def test_tasks_use_canonical_events_for_delivery(tmp_path):
    source = batch(tmp_path, status='succeeded')
    source.agents[0].contract = None
    source.agents[0].session_id = 'shared'
    native = batch(tmp_path, 'native', source='codex')
    native.agents[0].session_id = 'shared'
    native.executions[0].session_id = 'shared'
    native.events = [Event('delivered', 'result_delivered', 'codex', 'native',
                           actor_id='agent:native', evidence='synthetic delivery')]
    data = Monitor([Feed(source), Feed(native)]).refresh()
    assert data['events'][0]['actor_id'] == 'agent:run'
    assert len(data['tasks']) == 1
    assert 'delivered' in data['tasks'][0]['badges']


def test_empty_snapshot_has_tasks_list():
    monitor = Monitor([])
    assert monitor.snapshot()['tasks'] == []
    assert monitor.refresh()['tasks'] == []


def test_cli_kanban_flag_opens_kanban_view(monkeypatch):
    from alethe_tui import server
    fake = Mock()
    fake.start.return_value = fake
    fake.url.side_effect = lambda *, view: 'http://localhost/?view=' + view
    monkeypatch.setattr(server, 'LocalServer', Mock(return_value=fake))
    opened = Mock(return_value=True)
    monkeypatch.setattr(cli, 'open_browser', opened)
    # Stop the web wait without creating a socket or reading real agent sources.
    monkeypatch.setattr(cli.threading.Event, 'wait', Mock(side_effect=KeyboardInterrupt))
    monkeypatch.setattr(cli, 'build_monitor', Mock(return_value=Mock()))
    monkeypatch.setattr(Demo, 'start', lambda self: None)
    assert cli.main(['--demo', '--web', '--office', '--kanban']) == 0
    opened.assert_called_once_with('http://localhost/?view=kanban')


def test_demo_pipeline_covers_board_columns():
    demo = Demo()
    try:
        monitor = cli.build_monitor(Config([demo.alethe_root], demo.claude_root, demo.codex_root))
        data = monitor.refresh()
        assert any(t['column'] == 'blocked' and 'superseded' in t['badges'] for t in data['tasks'])
        assert {'blocked', 'in_progress', 'done'} <= {t['column'] for t in data['tasks']}
        actor = next(a for a in data['agents'] if a['source_id'] == 'dev-core' and a['wave_index'] == 3)
        previous = next(t for t in data['tasks'] if t['agent_id'] == actor['id'])
        assert previous['column'] == 'in_progress'
        demo.advance()
        current = next(t for t in monitor.refresh()['tasks'] if t['id'] == previous['id'])
        assert current['column'] == 'awaiting_tests'
    finally:
        demo.close()
