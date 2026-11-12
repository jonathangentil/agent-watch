"""Servidor da janela local; autenticação de sessão e nenhuma operação de escrita."""
from __future__ import annotations

from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import secrets
import threading
from urllib.parse import parse_qs, unquote, urlencode, urlsplit


class LocalServer:
    def __init__(self, monitor, host: str = "127.0.0.1", port: int = 0, asset_dir: Path | None = None):
        if host != "127.0.0.1":
            raise ValueError("O servidor local deve usar 127.0.0.1")
        self.monitor = monitor
        self.assets = (asset_dir or Path(__file__).parent / "web").resolve()
        self._token = secrets.token_urlsafe(32)
        self._thread = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "AletheLocal/0.1"

            def log_message(self, *_):
                # Nunca registrar o caminho de bootstrap com a chave de sessão.
                pass

            def send_data(self, status, body=b"", content_type="application/json; charset=utf-8", extra=None):
                if isinstance(body, str):
                    body = body.encode("utf-8")
                self.send_response(status)
                headers = {"Content-Type": content_type, "Content-Length": str(len(body)), "Cache-Control": "no-store",
                           "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
                           "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"}
                headers.update(extra or {})
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def error(self, status, message):
                self.send_data(status, json.dumps({"error": message}, ensure_ascii=False))

            def authenticated(self):
                try:
                    cookie = SimpleCookie(self.headers.get("Cookie", ""))
                    value = cookie["alethe_session"].value if "alethe_session" in cookie else ""
                    return secrets.compare_digest(value, owner._token)
                except (CookieError, TypeError):
                    return False

            def do_GET(self):
                if self.headers.get("Host", "") not in {f"127.0.0.1:{owner.port}", f"localhost:{owner.port}"}:
                    self.error(HTTPStatus.FORBIDDEN, "Host não permitido")
                    return
                parsed = urlsplit(self.path)
                route = unquote(parsed.path)
                query = parse_qs(parsed.query)
                if route == "/" and "key" in query:
                    if not secrets.compare_digest(query["key"][0], owner._token):
                        self.error(HTTPStatus.UNAUTHORIZED, "Sessão local inválida")
                        return
                    view = query.get("view", ["office"])[0]
                    params = {"view": view if view in {"office", "panel", "kanban"} else "office"}
                    if query.get("compact") == ["1"]:
                        params["compact"] = "1"
                    self.send_data(HTTPStatus.SEE_OTHER, b"", extra={"Location": "/?" + urlencode(params),
                        "Set-Cookie": f"alethe_session={owner._token}; HttpOnly; SameSite=Strict; Path=/"})
                    return
                if not self.authenticated():
                    if route == "/":
                        self.send_data(HTTPStatus.UNAUTHORIZED, """<!doctype html>
<html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent Watch · Abrir sessão</title>
<body><main><h1>Agent Watch</h1><p>Este navegador ainda não está autorizado para a sessão atual.</p>
<p>Na pasta do projeto, execute <code>./service.sh open</code> para abrir o monitor em segundo plano.</p>
<p>Se iniciou com <code>./run.sh</code>, abra a URL completa exibida no terminal.</p>
<p>Use o endereço completo com a chave de sessão. Abrir apenas <code>localhost:3010</code> ou trocar
<code>127.0.0.1</code> por <code>localhost</code> não transfere a autorização entre endereços.</p>
</main></body></html>""", "text/html; charset=utf-8")
                        return
                    self.error(HTTPStatus.UNAUTHORIZED, "Abra o endereço de sessão exibido pelo aplicativo")
                    return
                if route == "/api/snapshot":
                    self.send_data(200, json.dumps(owner.monitor.snapshot(), ensure_ascii=False, allow_nan=False))
                elif route == "/api/detail":
                    kind = query.get("kind", ["output"])[0]
                    if kind not in {"output", "error", "result", "task"}:
                        self.error(400, "Tipo de detalhe inválido")
                        return
                    try:
                        detail = owner.monitor.detail(query.get("agent", [""])[0], kind)
                    except KeyError:
                        self.error(404, "Agente não encontrado")
                        return
                    except ValueError as error:
                        self.error(400, str(error))
                        return
                    self.send_data(200, json.dumps({"text": detail}, ensure_ascii=False))
                elif route == "/" or route.startswith("/assets/"):
                    relative = "index.html" if route == "/" else route[len("/assets/"):]
                    file = (owner.assets / relative).resolve()
                    allowed = route == "/" or file.suffix in {".js", ".mjs", ".css", ".svg", ".png", ".ico"}
                    if not allowed or ".." in Path(relative).parts or not file.is_relative_to(owner.assets) or not file.is_file():
                        self.error(404, "Arquivo não encontrado")
                        return
                    kind = {".mjs": "text/javascript", ".js": "text/javascript"}.get(file.suffix) or mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                    self.send_data(200, file.read_bytes(), kind + ("; charset=utf-8" if kind.startswith("text/") else ""))
                else:
                    self.error(404, "Rota não encontrada")

        self._http = ThreadingHTTPServer((host, port), Handler)
        self._http.daemon_threads = True
        self.port = self._http.server_address[1]

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.port}"

    def url(self, view="office", compact=False):
        params = {"key": self._token, "view": view}
        if compact:
            params["compact"] = "1"
        return self.base_url + "/?" + urlencode(params)

    def start(self):
        if self._thread and self._thread.is_alive():
            return self
        self._thread = threading.Thread(target=self._http.serve_forever, kwargs={"poll_interval": .2}, name="alethe-http", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self._thread and self._thread.is_alive():
            self._http.shutdown()
            self._thread.join(timeout=3)
        self._http.server_close()
