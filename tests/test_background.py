import json
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_open_reuses_existing_session_without_starting_monitor(tmp_path, monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("background", ROOT / "scripts/background.py")
    background = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(background)
    directory = tmp_path / "agent-watch"
    directory.mkdir()
    state_file = directory / "service.json"
    original_state = json.dumps({"pid": os.getpid(), "start_time": "synthetic", "port": 3010})
    state_file.write_text(original_state)
    url = "http://127.0.0.1:3010/?key=synthetic-session&view=office"
    (directory / "service.log").write_text("Agent Watch\n" + url + "\n")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(background, "identity", lambda pid: "synthetic")
    monkeypatch.setattr(sys, "argv", ["background.py", "open"])
    opened = []
    monkeypatch.setattr(background, "open_browser", lambda address: opened.append(address) or True)
    assert background.main() == 0
    assert opened == [url]
    assert state_file.read_text() == original_state
    assert "synthetic-session" not in capsys.readouterr().out


def test_open_when_stopped_does_not_start_monitor(tmp_path):
    result = control(tmp_path, "open")
    assert result.returncode == 1
    assert "./service.sh start" in result.stdout
    assert not (tmp_path / "agent-watch/service.json").exists()


def control(state, *args):
    return subprocess.run(
        ["sh", str(ROOT / "service.sh"), *args], cwd=ROOT,
        env={**os.environ, "XDG_STATE_HOME": str(state)},
        capture_output=True, text=True, timeout=20,
    )


def test_background_lifecycle_and_duplicate_start(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    try:
        started = control(tmp_path, "start", "--port", str(port), "--demo", "--no-open")
        assert started.returncode == 0, started.stderr
        state_file = tmp_path / "agent-watch/service.json"
        first = json.loads(state_file.read_text())
        assert control(tmp_path, "status").returncode == 0
        again = control(tmp_path, "start", "--no-open")
        assert again.returncode == 0, again.stderr
        assert json.loads(state_file.read_text())["pid"] == first["pid"]
        assert control(tmp_path, "stop").returncode == 0
        assert control(tmp_path, "status").returncode == 1
        assert control(tmp_path, "stop").returncode == 0
    finally:
        control(tmp_path, "stop")


def test_stop_does_not_signal_reused_pid(tmp_path):
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        directory = tmp_path / "agent-watch"
        directory.mkdir()
        (directory / "service.json").write_text(json.dumps({"pid": sleeper.pid, "start_time": "invalid", "port": 3010}))
        result = control(tmp_path, "stop")
        assert result.returncode == 0, result.stderr
        assert sleeper.poll() is None
    finally:
        sleeper.terminate()
        sleeper.wait()


def test_occupied_port_does_not_register_a_service(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        result = control(tmp_path, "start", "--port", str(sock.getsockname()[1]), "--demo", "--no-open")
        assert result.returncode == 2
        assert "Não foi possível iniciar" in result.stderr
        assert control(tmp_path, "status").returncode == 1
        assert not (tmp_path / "agent-watch/service.json").exists()
