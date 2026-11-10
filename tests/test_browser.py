import json
import os
import sys

import pytest


@pytest.mark.parametrize("exit_code", [0, 1])
def test_wsl_opens_windows_browser_with_private_url_on_stdin(tmp_path, monkeypatch, exit_code):
    from alethe_tui.browser import open_browser

    executable = tmp_path / "powershell.exe"
    captured = tmp_path / "request.json"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['BROWSER_TEST_CAPTURE']).write_text(json.dumps({'args': sys.argv[1:], 'input': sys.stdin.read()}))\n"
        f"sys.exit({exit_code})\n"
    )
    executable.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("BROWSER_TEST_CAPTURE", str(captured))
    monkeypatch.setattr("platform.release", lambda: "6.0-microsoft-standard-WSL2")
    url = "http://127.0.0.1:3010/?key=synthetic-session&view=office"
    assert open_browser(url) is (exit_code == 0)
    request = json.loads(captured.read_text())
    assert request["input"] == url
    assert "synthetic-session" not in " ".join(request["args"])
    assert "Start-Process" in request["args"][-1]


def test_other_platforms_keep_system_browser(monkeypatch):
    from alethe_tui.browser import open_browser

    monkeypatch.setattr("platform.release", lambda: "6.0-linux")
    import webbrowser
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or True)
    assert open_browser("http://127.0.0.1:3010/") is True
    assert opened == ["http://127.0.0.1:3010/"]
