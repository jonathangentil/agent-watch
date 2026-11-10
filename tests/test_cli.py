import json

from alethe_tui.cli import main, build_monitor
from alethe_tui.config import load_config


def test_demo_snapshot_uses_all_three_synthetic_sources(capsys):
    assert main(["--demo", "--snapshot"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["demo"] is True
    assert {a["source"] for a in data["agents"]} == {"alethe", "claude", "codex"}
    assert data["totals"]["projects"] == 2
    assert data["totals"]["executions"] == 3


def test_invalid_interval_returns_actionable_error(capsys):
    assert main(["--interval", "-1", "--snapshot"]) == 2
    assert "interval" in capsys.readouterr().err


def test_build_monitor_applies_dotenv_project_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text('AGENT_WATCH_PROJECT_DIRS= ["./allowed"]\n')
    run = tmp_path / 'runs/example'
    run.mkdir(parents=True)
    (run / 'state.json').write_text(json.dumps({'workers': {
        'worker': {'status': 'succeeded', 'cwd': str(tmp_path / 'excluded')},
    }}))
    config = load_config(path=tmp_path / 'missing.toml', environ={'HOME': str(tmp_path)}, roots=[tmp_path / 'runs'])
    data = build_monitor(config).refresh()
    assert data['executions'] == []
