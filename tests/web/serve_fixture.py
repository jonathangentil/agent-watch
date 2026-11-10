"""Servidor real com fontes sintéticas; usado apenas pelo smoke de navegador."""
import json
import os
from pathlib import Path
import signal
import sys
import threading
from alethe_tui.demo import Demo
from alethe_tui.config import Config
from alethe_tui.cli import build_monitor
from alethe_tui.server import LocalServer

demo = Demo()
monitor = build_monitor(Config([demo.alethe_root], demo.claude_root, demo.codex_root, .2), demo=True)
monitor.refresh()
server = LocalServer(monitor).start()
monitor.start()
done = threading.Event()
signal.signal(signal.SIGTERM, lambda *_: done.set())
signal.signal(signal.SIGINT, lambda *_: done.set())
info = Path(sys.argv[1])
info.write_text(json.dumps({'url':server.url('office'),'root':str(demo.root)}))
os.chmod(info, 0o600)
try:
    done.wait()
finally:
    monitor.stop()
    server.stop()
    demo.close()
    info.unlink(missing_ok=True)
