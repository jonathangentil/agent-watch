"""Controle local do monitor em segundo plano (Linux/WSL)."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

from alethe_tui.browser import open_browser


ROOT = Path(__file__).resolve().parents[1]


def identity(pid):
    try:
        # comm pode conter espaços e parênteses; os campos seguintes são fixos.
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        if fields[0] == "Z":
            return None
        command = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        if b"alethe_tui" not in command or b"--web" not in command:
            return None
        return fields[19]  # campo 22: starttime
    except (OSError, IndexError, ValueError):
        return None


def alive(state):
    return bool(state and state.get("start_time") and identity(state["pid"]) == state["start_time"])


def open_session(directory, state):
    prefix = f"http://127.0.0.1:{state['port']}/?key="
    urls = [line for line in (directory / "service.log").read_text().splitlines() if line.startswith(prefix)]
    if not urls:
        raise RuntimeError("URL de sessão indisponível no log privado do monitor.")
    if not open_browser(urls[0]):
        raise RuntimeError(f"Não foi possível abrir o navegador. Abra a URL de sessão no log privado: {directory / 'service.log'}")
    print("Sessão do Agent Watch aberta no navegador.")


def main():
    parser = argparse.ArgumentParser(description="Agent Watch em segundo plano")
    parser.add_argument("action", choices=["start", "open", "stop", "status"])
    parser.add_argument("--port", type=int, default=3010)
    parser.add_argument("--no-open", action="store_true", help="não abrir navegador ao iniciar")
    parser.add_argument("--demo", action="store_true", help="fontes fictícias, sem modelos")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("a porta deve estar entre 1 e 65535")
    os.umask(0o077)
    directory = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "agent-watch"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    state_file = directory / "service.json"
    with (directory / "service.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            state = json.loads(state_file.read_text())
        except (OSError, ValueError):
            state = None
        running = alive(state)
        if args.action == "open":
            if not running:
                print("Agent Watch parado. Inicie com ./service.sh start")
                return 1
            open_session(directory, state)
            return 0
        if args.action == "status":
            if running:
                print(f"Agent Watch rodando · PID {state['pid']} · porta {state['port']}. Para abrir: ./service.sh open")
                return 0
            print("Agent Watch parado.")
            return 1
        if args.action == "stop":
            if running:
                try:
                    # pidfd impede que um PID reutilizado receba o sinal.
                    descriptor = os.pidfd_open(state["pid"])
                    try:
                        if alive(state):
                            signal.pidfd_send_signal(descriptor, signal.SIGTERM)
                    finally:
                        os.close(descriptor)
                except ProcessLookupError:
                    pass
                for _ in range(50):
                    if not alive(state):
                        break
                    time.sleep(.1)
                if alive(state):
                    raise RuntimeError("O monitor ainda não encerrou; consulte status.")
            state_file.unlink(missing_ok=True)
            print("Agent Watch parado. Agentes monitorados não foram afetados.")
            return 0
        if running:
            print(f"Agent Watch já está rodando · PID {state['pid']} · porta {state['port']}.")
            if not args.no_open:
                open_session(directory, state)
            return 0
        state_file.unlink(missing_ok=True)
        log_path = directory / "service.log"
        command = [str(ROOT / ".venv/bin/python"), "-m", "alethe_tui", "--web", "--office", "--port", str(args.port)]
        if args.no_open:
            command.append("--no-open")
        if args.demo:
            command.append("--demo")
        with log_path.open("w") as log:
            log_path.chmod(0o600)
            process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, start_new_session=True, close_fds=True)
        try:
            # O log privado contém a URL de autorização. Nunca imprimi-la aqui.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor())
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError(f"Não foi possível iniciar na porta {args.port}. Consulte o log privado: {log_path}")
                urls = [line for line in log_path.read_text().splitlines() if line.startswith(f"http://127.0.0.1:{args.port}/?key=")]
                if urls:
                    try:
                        with opener.open(urls[0], timeout=1) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        pass
                time.sleep(.1)
            else:
                raise RuntimeError(f"Tempo esgotado ao iniciar. Consulte o log privado: {log_path}")
            start_time = identity(process.pid)
            if not start_time:
                raise RuntimeError("O processo encerrou durante a inicialização.")
            state_file.write_text(json.dumps({"pid": process.pid, "start_time": start_time, "port": args.port}))
        except BaseException:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            raise
        print(f"Agent Watch iniciado em segundo plano · PID {process.pid} · porta {args.port}. Para abrir: ./service.sh open")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        sys.exit(2)
