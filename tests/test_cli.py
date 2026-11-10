import json

from alethe_tui.cli import main


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
