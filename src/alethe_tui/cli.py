"""Ponto de entrada do monitor local."""
import argparse
from dataclasses import replace
import json
import math
from pathlib import Path
import sys
import threading

from .browser import open_browser

from .config import Config, load_config
from .monitor import Monitor


def build_monitor(config, demo=False):
    from .adapters import AletheAdapter, ClaudeAdapter, CodexAdapter
    monitor = Monitor([AletheAdapter(config.roots, config.verify_pids), ClaudeAdapter(config.claude_root), CodexAdapter(config.codex_root)], config.interval, project_dirs=config.project_dirs)
    monitor.demo = demo
    return monitor


def parser():
    result = argparse.ArgumentParser(description="Agent Watch: acompanhe agentes Alethe, Claude Code e Codex no terminal ou em uma janela local.")
    result.add_argument("--web", action="store_true", help="servidor gráfico sem interface de terminal")
    result.add_argument("--office", action="store_true", help="abrir o escritório visual ao iniciar")
    result.add_argument("--no-open", action="store_true", help="não abrir o navegador automaticamente")
    result.add_argument("--port", type=int, default=0, help="porta local (0 escolhe uma disponível)")
    result.add_argument("--root", type=Path, action="append", help="raiz Alethe adicional; pode repetir")
    result.add_argument("--claude-root", type=Path, help="pasta projects do Claude Code")
    result.add_argument("--codex-root", type=Path, help="pasta sessions do Codex")
    result.add_argument("--config", type=Path, help="arquivo TOML de configuração")
    result.add_argument("--interval", type=float, help="intervalo de atualização em segundos (mínimo 0.1)")
    result.add_argument("--no-pid-check", action="store_true", help="não verificar PIDs locais em fontes copiadas de outra máquina")
    result.add_argument("--snapshot", action="store_true", help="imprimir um snapshot JSON e encerrar")
    result.add_argument("--demo", action="store_true", help="usar somente fontes fictícias temporárias, sem modelos")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    demo = monitor = server = None
    try:
        if args.interval is not None and (not math.isfinite(args.interval) or args.interval < .1):
            raise ValueError("interval deve ser um número finito maior ou igual a 0.1")
        if not 0 <= args.port <= 65535:
            raise ValueError("port deve estar entre 0 e 65535")
        if args.demo:
            from .demo import Demo
            demo = Demo()
            config = Config([demo.alethe_root], demo.claude_root, demo.codex_root, args.interval or 1)
        else:
            config = load_config(args.config, roots=args.root, claude_root=args.claude_root, codex_root=args.codex_root)
            config = replace(config, interval=args.interval or config.interval, verify_pids=False if args.no_pid_check else config.verify_pids)
        monitor = build_monitor(config, demo=bool(demo))
        data = monitor.refresh()
        if args.snapshot:
            print(json.dumps(data, ensure_ascii=False, allow_nan=False))
            return 0
        if not args.web and not sys.stdin.isatty():
            raise ValueError("A TUI precisa de um terminal interativo. Use --web ou --snapshot neste ambiente.")
        from .server import LocalServer
        server = LocalServer(monitor, port=args.port).start()
        view = "office" if args.office else "panel"
        print("Agent Watch · " + ("DEMONSTRAÇÃO · dados fictícios\n" if demo else "Monitor local · somente leitura\n") + server.url(view=view), flush=True)
        monitor.start()
        if demo:
            demo.start()
        if not args.no_open and (args.web or args.office):
            if not open_browser(server.url(view=view)):
                print("O navegador não abriu. Use a URL de sessão exibida acima.", file=sys.stderr)
        if args.web:
            while True:
                threading.Event().wait(.5)
        else:
            from .tui import AgentApp
            AgentApp(monitor, server).run()
        return 0
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    finally:
        if monitor:
            monitor.stop()
        if server:
            server.stop()
        if demo:
            demo.close()
