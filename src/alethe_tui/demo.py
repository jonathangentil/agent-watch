"""Fontes fictícias locais para demonstrar a aplicação sem chamar modelos."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import threading


def _now():
    return datetime.now(timezone.utc).isoformat()


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _append(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


class Demo:
    def __init__(self):
        self._temp = tempfile.TemporaryDirectory(prefix="alethe-demo-")
        self.root = Path(self._temp.name)
        self.alethe_root = self.root / "alethe"
        self.claude_root = self.root / "claude"
        self.codex_root = self.root / "codex"
        self._stop = threading.Event()
        self._thread = None
        self._phase = 0
        self._build()

    def _build(self):
        self.project_a = self.root / "projetos/catalogo"
        self.project_b = self.root / "projetos/integracao"
        self.project_a.mkdir(parents=True)
        self.project_b.mkdir(parents=True)
        self.wave = self.alethe_root / "demonstracao/01-build"
        _write(self.wave.parent / "orchestration.json", {"title": "DEMONSTRAÇÃO · Catálogo", "createdAt": _now(), "lead": {"id": "demo-lead", "name": "Lead da demonstração"}})
        names = ["dev-core", "reviewer", "test-suite", "scout", "docs", "checks", "ui"]
        states = ["running", "running", "queued", "succeeded", "queued", "succeeded", "running"]
        workers = {}
        plan = []
        for index, (name, status) in enumerate(zip(names, states)):
            workers[name] = {"status": status, "cwd": str(self.project_a), "provider": "codex" if index % 2 == 0 else "claude"}
            if status != "queued":
                workers[name]["startedAt"] = _now()
            if status == "succeeded":
                workers[name]["finishedAt"] = _now()
            plan.append({"id": name, "task": f"Tarefa fictícia de {name}; nenhuma chamada a modelos", "model": "modelo de exemplo", "cwd": str(self.project_a)})
            folder = self.wave / "workers" / name
            folder.mkdir(parents=True)
            (folder / "stdout.log").write_text("DEMONSTRAÇÃO\nSaída pública fictícia do agente.\n", encoding="utf-8")
            if status == "succeeded":
                (folder / "result.md").write_text("Resultado fictício disponível.\n", encoding="utf-8")
        self.state = {"status": "running", "runnerPid": os.getpid(), "startedAt": _now(), "workers": workers}
        _write(self.wave / "state.json", self.state)
        _write(self.wave / "plan.json", {"title": "Demonstração", "workers": plan})
        self.claude_parent = self.claude_root / "projeto-demo/demo-session.jsonl"
        for index in range(2):
            identity = f"demo-claude-{index}"
            tool_id = f"demo-tool-{index}"
            path = self.claude_root / "projeto-demo/demo-session/subagents" / f"agent-{identity}.jsonl"
            _append(self.claude_parent, {"type": "assistant", "sessionId": "demo-session", "timestamp": _now(), "message": {"content": [{"type": "tool_use", "id": tool_id, "name": "Agent", "input": {}}]}})
            _write(path.with_suffix(".meta.json"), {"agentType": "Reviewer" if index == 0 else "Explore", "toolUseId": tool_id})
            common = {"agentId": identity, "sessionId": "demo-session", "isSidechain": True, "cwd": str(self.project_b), "timestamp": _now()}
            _append(path, {**common, "type": "user", "message": {"content": [{"type": "text", "text": "Tarefa fictícia do subagente Claude"}]}})
            if index:
                _append(path, {**common, "type": "assistant", "message": {"model": "Claude de exemplo", "stop_reason": "end_turn", "content": [{"type": "text", "text": "Resultado fictício do turno"}]}})
            else:
                self.claude_child = path
        _append(self.codex_root / "rollout-parent.jsonl", {"type": "session_meta", "timestamp": _now(), "payload": {"id": "demo-codex-parent", "source": "cli", "cwd": str(self.project_b)}})
        for index in range(2):
            identity = f"demo-codex-{index}"
            path = self.codex_root / f"rollout-{identity}.jsonl"
            _append(path, {"type": "session_meta", "timestamp": _now(), "payload": {"id": identity, "cwd": str(self.project_b), "agent_nickname": "Codex reviewer" if index == 0 else "Codex tests", "source": {"subagent": {"thread_spawn": {"parent_thread_id": "demo-codex-parent"}}}}})
            _append(path, {"type": "event_msg", "timestamp": _now(), "payload": {"type": "task_started", "turn_id": f"demo-turn-{index}"}})
            _append(path, {"type": "turn_context", "payload": {"model": "Codex de exemplo"}})
            if index:
                _append(path, {"type": "event_msg", "timestamp": _now(), "payload": {"type": "task_complete", "turn_id": "demo-turn-1", "last_agent_message": "Teste fictício concluído"}})
            else:
                self.codex_child = path

    def advance(self):
        self._phase += 1
        if self._phase == 1:
            self.state["workers"]["test-suite"].update(status="running", startedAt=_now())
            _write(self.wave / "state.json", self.state)
        elif self._phase == 2:
            self.state["workers"]["dev-core"].update(status="succeeded", finishedAt=_now())
            _write(self.wave / "state.json", self.state)
            _append(self.codex_child, {"type": "event_msg", "timestamp": _now(), "payload": {"type": "task_complete", "turn_id": "demo-turn-0", "last_agent_message": "Resultado fictício disponível"}})
        elif self._phase == 3:
            _append(self.claude_child, {"type": "assistant", "agentId": "demo-claude-0", "isSidechain": True, "sessionId": "demo-session", "timestamp": _now(), "message": {"stop_reason": "end_turn", "content": [{"type": "text", "text": "Resultado fictício disponível"}]}})
            _append(self.claude_parent, {"type": "user", "sessionId": "demo-session", "timestamp": _now(), "message": {"content": [{"type": "tool_result", "tool_use_id": "demo-tool-0", "content": "Resultado fictício entregue"}]}})

    def start(self):
        def run():
            while not self._stop.wait(4):
                self.advance()
        self._thread = threading.Thread(target=run, name="alethe-demo", daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        self._temp.cleanup()
