"""Visão comum às interfaces; não controla os processos monitorados."""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import subprocess
import threading

from .model import ScanResult


def _iso_now():
    return datetime.now(timezone.utc).isoformat()


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).timestamp()
    except (ValueError, TypeError, AttributeError):
        return None


@lru_cache(maxsize=1024)
def resolve_project(cwd: str) -> str:
    path = Path(cwd).expanduser().resolve()
    try:
        result = subprocess.run(["git", "-C", str(path), "rev-parse", "--path-format=absolute", "--git-common-dir", "--show-toplevel"],
                                capture_output=True, text=True, timeout=1, check=False)
        if result.returncode == 0:
            common, top, *_ = result.stdout.strip().splitlines()
            return str(Path(common).parent if Path(common).name == ".git" else Path(top))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return str(path)


class Monitor:
    def __init__(self, adapters: list, interval: float = 1.0):
        if interval < 0.1:
            raise ValueError("interval deve ser >= 0.1")
        self.adapters = adapters
        self.demo = False
        self.interval = interval
        self._lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._cache = {}
        self._seen_events = set()
        self._events = OrderedDict()
        self._started = datetime.now(timezone.utc).timestamp()
        self._initial = True
        self._agents_by_id = {}
        self._snapshot = self._empty()

    @staticmethod
    def _empty():
        return {"version": 1, "generated_at": _iso_now(), "connected": True, "agents": [], "executions": [],
                "events": [], "diagnostics": [], "projects": [], "totals": {"projects": 0, "executions": 0, "agents": 0,
                "running": 0, "queued": 0, "completed": 0, "failed": 0}}

    def refresh(self) -> dict:
        with self._refresh_lock:
            batches, diagnostics = [], []
            for index, adapter in enumerate(self.adapters):
                try:
                    batch = adapter.scan()
                    if not isinstance(batch, ScanResult):
                        raise TypeError("Leitor não devolveu ScanResult")
                    self._cache[index] = deepcopy(batch)
                except Exception as error:
                    batch = self._cache.get(index, ScanResult())
                    diagnostics.append({"source": type(adapter).__name__, "path": "", "status": "stale", "message": str(error)[:500]})
                batches.append(batch)
                diagnostics.extend(deepcopy(batch.diagnostics))
            agents = {a.id: replace(a) for b in batches for a in b.agents}
            executions = {e.id: replace(e, project_ids=list(e.project_ids)) for b in batches for e in b.executions}
            worker_sessions = {a.session_id: a for a in agents.values() if a.source == "alethe" and a.session_id}
            execution_alias, actor_alias = {}, {}
            for execution in list(executions.values()):
                worker = worker_sessions.get(execution.session_id)
                if execution.source != "alethe" and worker:
                    execution_alias[execution.id] = worker.execution_id
                    if execution.leader_id:
                        actor_alias[execution.leader_id] = worker.id
                    executions.pop(execution.id, None)
            for actor in list(agents.values()):
                worker = worker_sessions.get(actor.session_id)
                if actor.source != "alethe" and worker and actor.id != worker.id:
                    actor_alias[actor.id] = worker.id
                    agents.pop(actor.id, None)

            def canonical(value, aliases):
                seen = set()
                while value in aliases and value not in seen:
                    seen.add(value)
                    value = aliases[value]
                return value

            for actor in agents.values():
                actor.execution_id = canonical(actor.execution_id, execution_alias)
                actor.parent_id = canonical(actor.parent_id, actor_alias)
                execution = executions.get(actor.execution_id)
                cwd = actor.cwd or (execution.project_path if execution else "") or actor.project_id
                if cwd:
                    actor.project_id = resolve_project(cwd)
            for execution in executions.values():
                if execution.project_path:
                    execution.project_id = resolve_project(execution.project_path)
                    execution.project_path = execution.project_id
                    execution.project_name = Path(execution.project_path).name or execution.project_name
                execution.project_ids = list(dict.fromkeys([execution.project_id] + [a.project_id for a in agents.values() if a.execution_id == execution.id]))
            active = {a.execution_id for a in agents.values() if a.status in {"running", "queued"}}
            ordered = sorted(executions.values(), key=lambda e: e.started_at or "", reverse=True)
            retained = [e for e in ordered if e.id in active] + [e for e in ordered if e.id not in active][:50]
            executions = {e.id: e for e in retained}
            agents = {key: a for key, a in agents.items() if a.execution_id in executions}
            for batch in batches:
                for event in batch.events:
                    if event.id in self._seen_events:
                        continue
                    self._seen_events.add(event.id)
                    item = asdict(event)
                    item["execution_id"] = canonical(event.execution_id, execution_alias)
                    item["actor_id"] = canonical(event.actor_id, actor_alias)
                    item["target_id"] = canonical(event.target_id, actor_alias)
                    instant = _timestamp(event.timestamp)
                    item["is_live"] = not self._initial and instant is not None and instant >= self._started
                    self._events[event.id] = item
            for item in self._events.values():
                item['execution_id'] = canonical(item['execution_id'], execution_alias)
                item['actor_id'] = canonical(item['actor_id'], actor_alias)
                item['target_id'] = canonical(item['target_id'], actor_alias)
            self._initial = False
            while len(self._events) > 500:
                self._events.popitem(last=False)
            if len(self._seen_events) > 100_000:
                self._seen_events = set(self._events)
            projects = {}
            for execution in executions.values():
                for key in execution.project_ids:
                    projects[key] = {"id": key, "name": Path(key).name or execution.project_name, "path": key}
            data = self._empty()
            data["demo"] = self.demo
            statuses = [a.status for a in agents.values()]
            data.update(agents=[asdict(a) for a in agents.values()], executions=[asdict(e) for e in executions.values()],
                        events=list(self._events.values()), projects=sorted(projects.values(), key=lambda p: p["name"].casefold()),
                        diagnostics=diagnostics, generated_at=_iso_now())
            data["totals"] = {"projects": len(projects), "executions": len(executions), "active_executions": len(active), "agents": len(agents),
                              "running": statuses.count("running"), "queued": statuses.count("queued"),
                              "completed": sum(s in {"succeeded", "turn_complete"} for s in statuses),
                              "failed": sum(s in {"failed", "timed_out", "interrupted"} for s in statuses)}
            with self._lock:
                self._agents_by_id = agents
                self._snapshot = data
            return deepcopy(data)

    def snapshot(self) -> dict:
        with self._lock:
            return deepcopy(self._snapshot)

    def detail(self, agent_id: str, kind: str = "output") -> str:
        from .details import read_agent_detail
        if kind not in {"output", "error", "result", "task"}:
            raise ValueError("Tipo de detalhe inválido")
        with self._lock:
            actor = self._agents_by_id.get(agent_id)
        if actor is None:
            raise KeyError("Agente não encontrado")
        return read_agent_detail(actor, kind)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="alethe-monitor", daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            self.refresh()
            self._stop.wait(self.interval)

    def stop(self):
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)
