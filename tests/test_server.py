import http.client
import json
from urllib.parse import urlsplit

import pytest

from alethe_tui.server import LocalServer


class Data:
    def snapshot(self):
        return {"version": 1, "agents": [{"id": "known", "task": "<script>untrusted</script>"}]}

    def detail(self, actor, kind):
        if actor != "known":
            raise KeyError(actor)
        if kind not in {"output", "task", "error", "result"}:
            raise ValueError(kind)
        return "public output"


@pytest.fixture
def server(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><html>local UI</html>")
    (tmp_path / "app.js").write_text("console.log('local')")
    server = LocalServer(Data(), asset_dir=tmp_path)
    server.start()
    yield server
    server.stop()


def request(server, path, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=3)
    conn.request("GET", path, headers=headers or {})
    response = conn.getresponse()
    data = response.read()
    result = response.status, dict(response.getheaders()), data
    conn.close()
    return result


def login(server):
    parsed = urlsplit(server.url(view="office"))
    status, headers, _ = request(server, parsed.path + "?" + parsed.query)
    assert status == 303
    assert headers["Location"] == "/?view=office"
    assert "HttpOnly" in headers["Set-Cookie"]
    assert "SameSite=Strict" in headers["Set-Cookie"]
    return {"Cookie": headers["Set-Cookie"].split(";", 1)[0]}


def test_authentication_and_local_assets(server):
    assert request(server, "/api/snapshot")[0] == 401
    assert request(server, "/?key=wrong")[0] == 401
    cookie = login(server)
    assert request(server, "/", cookie)[0] == 200
    status, headers, data = request(server, "/api/snapshot", cookie)
    assert status == 200
    assert json.loads(data)["agents"][0]["task"] == "<script>untrusted</script>"
    assert headers["Cache-Control"] == "no-store"
    assert "Access-Control-Allow-Origin" not in headers
    assert request(server, "/assets/app.js", cookie)[0] == 200


def test_missing_or_expired_browser_session_has_recovery_instructions(server):
    for headers in ({}, {"Cookie": "alethe_session=expired"}, {"Host": f"localhost:{server.port}"}):
        status, response_headers, body = request(server, "/", headers)
        assert status == 401
        assert response_headers["Content-Type"].startswith("text/html")
        assert b"./service.sh open" in body
        assert "Set-Cookie" not in response_headers
        assert server._token.encode() not in body
    assert request(server, "/api/snapshot")[0] == 401
    assert request(server, "/assets/app.js")[0] == 401


def test_paths_and_details_are_restricted(server):
    cookie = login(server)
    assert request(server, "/assets/../index.html", cookie)[0] == 404
    assert request(server, "/assets/%2e%2e/index.html", cookie)[0] == 404
    assert request(server, "/api/detail?agent=unknown", cookie)[0] == 404
    assert request(server, "/api/detail?agent=known&kind=../../../etc/passwd", cookie)[0] == 400
    assert json.loads(request(server, "/api/detail?agent=known&kind=output", cookie)[2]) == {"text": "public output"}


def test_foreign_host_is_rejected(server):
    assert request(server, "/", {"Host": "evil.example"})[0] == 403


def test_server_only_binds_loopback():
    with pytest.raises(ValueError, match="127.0.0.1"):
        LocalServer(Data(), host="0.0.0.0")


@pytest.mark.parametrize(('view', 'expected'), [
    ('kanban', 'kanban'), ('panel', 'panel'), ('office', 'office'), ('evil', 'office'),
])
def test_login_preserves_supported_view_and_defaults_unknown_to_office(server, view, expected):
    parsed = urlsplit(server.url(view=view))
    status, headers, _ = request(server, parsed.path + '?' + parsed.query)
    assert status == 303
    assert headers['Location'] == '/?view=' + expected
    cookie = {'Cookie': headers['Set-Cookie'].split(';', 1)[0]}
    assert request(server, headers['Location'], cookie)[0] == 200
