"""Read Alethe waves and worker artifacts without importing its executor."""
import os
import re
from pathlib import Path

from ..model import Agent, Event, Execution, Gate, ScanResult
from ._io import JsonCache, TextCache, diagnostic, discover, mapping, safe_text, sequence, stable_id, string
from ._metadata import ROLE_NAMES, identify_role
from ._usage import reported_tokens

STATUSES = {"queued", "running", "succeeded", "turn_complete", "failed", "timed_out",
            "interrupted", "stopped", "skipped", "unknown"}


def status(value):
    return "succeeded" if value == "done" else value if isinstance(value, str) and value in STATUSES else "unknown"


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def existing(path):
    try:
        return str(path) if path.is_file() else None
    except OSError:
        return None


class AletheAdapter:
    def __init__(self, roots: list[Path], verify_pids: bool = True):
        self.roots = list(dict.fromkeys(Path(root).expanduser().resolve() for root in roots))
        self.verify_pids = verify_pids
        self.cache = JsonCache("alethe")
        self.prompts = TextCache('alethe')
        self.known = set()

    def _gates(self, group, execution_id, result):
        for path in discover(group, "gate-[0-9][0-9]*.json", "alethe", result.diagnostics):
            errors = []
            value = self.cache.read(path, errors, optional=True)
            valid = (type(value.get("gate")) is int and isinstance(value.get("decision"), str)
                     and all(isinstance(value.get(key, []), list)
                             and all(isinstance(item, str) for item in value.get(key, []))
                             for key in ("developers", "reviewers", "qa")))
            # JsonCache normally retains the last valid value. Gates fail closed:
            # a damaged decision must never keep approving a card from the cache.
            if errors or not valid:
                result.diagnostics.append(diagnostic("alethe", path, "invalid", "gate ignorado"))
                continue
            decision = value["decision"] if value["decision"] in {"APPROVED", "REJECTED", "BLOCKED"} else "unknown"
            gate_number = value["gate"]
            result.gates.append(Gate(
                execution_id=execution_id, number=gate_number, decision=decision,
                revision=safe_text(value.get("revision")) or None,
                developers=list(value.get("developers", [])),
                reviewers=list(value.get("reviewers", [])),
                qa=list(value.get("qa", [])),
                at=string(value.get("at")) or None,
                evidence=f"{path}: gate {gate_number} {decision}"))

    def _runner(self, state, path, diagnostics):
        pid = state.get("runnerPid")
        if not self.verify_pids or state.get("status") != "running" or not isinstance(pid, int) or pid <= 0:
            return ""
        try:
            os.kill(pid, 0)
            return "processo presente; identidade não verificada"
        except ProcessLookupError:
            return "runner ausente"
        except OSError:
            diagnostics.append(diagnostic("alethe", path, "unverifiable", "PID não verificável"))
            return "PID não verificável"

    def scan(self) -> ScanResult:
        result = ScanResult()
        paths = set(self.known)
        for root in self.roots:
            if not root.is_dir():
                result.diagnostics.append(diagnostic("alethe", root, "unavailable", "raiz não acessível"))
                continue
            if (root / "state.json").is_file():
                paths.add(root / "state.json")
            paths.update(discover(root, "*/state.json", "alethe", result.diagnostics))
            paths.update(discover(root, "*/*/state.json", "alethe", result.diagnostics))
        self.known.update(paths)
        groups = {}
        candidates = []
        for state_path in sorted(paths):
            state = self.cache.read(state_path, result.diagnostics, validate=lambda value: isinstance(value.get("workers"), dict))
            if not isinstance(state.get("workers"), dict):
                if state:
                    result.diagnostics.append(diagnostic("alethe", state_path, "invalid", "workers incompatíveis"))
                continue
            folder = state_path.parent
            parent_meta = folder.parent / "orchestration.json"
            own_meta = folder / "orchestration.json"
            group = folder.parent if parent_meta.is_file() or parent_meta in self.cache.values else folder
            candidates.append((state_path, state, folder, group))
        group_states = {}
        for _, state, _, group in candidates:
            group_states.setdefault(group, []).append(state)
        terminal = {"succeeded", "turn_complete", "failed", "timed_out", "interrupted", "stopped", "skipped"}
        historical = [group for group, states in group_states.items() if all(status(state.get("status")) in terminal for state in states)]
        historical.sort(key=lambda group: max(string(state.get("startedAt")) for state in group_states[group]), reverse=True)
        excluded = set(historical[50:])
        if excluded:
            result.diagnostics.append(diagnostic("alethe", "", "limited", "histórico limitado às 50 execuções mais recentes; ativas preservadas"))
        for state_path, state, folder, group in candidates:
            if group in excluded:
                continue
            parent_meta = folder.parent / "orchestration.json"
            own_meta = folder / "orchestration.json"
            meta = self.cache.read(parent_meta if group != folder else own_meta, result.diagnostics, optional=True)
            plan = self.cache.read(folder / "plan.json", result.diagnostics, optional=True)
            intentions = {entry["id"]: entry for entry in sequence(plan.get("workers"))
                          if isinstance(entry, dict) and isinstance(entry.get("id"), str)}
            execution_id = "alethe:" + stable_id(str(group))
            runner = self._runner(state, state_path, result.diagnostics)
            wave_status = "interrupted" if runner == "runner ausente" else status(state.get("status"))
            lead = mapping(meta.get("lead"))
            lead_source_id = string(lead.get("sessionId")) or string(lead.get("id"))
            # A generic node identifies this observed executor, not a claimed
            # Codex/Claude conversation when no native lead ID is recorded.
            lead_id = "alethe:leader:" + lead_source_id if lead_source_id else execution_id + ":orchestrator"
            agents = []
            for worker_id, entry in state["workers"].items():
                if not isinstance(entry, dict) or not isinstance(worker_id, str):
                    continue
                if worker_id in (".", "..") or "/" in worker_id or "\\" in worker_id:
                    continue
                worker_dir = folder / "workers" / worker_id
                outcome_path = worker_dir / "outcome.json"
                outcome = self.cache.read(outcome_path, result.diagnostics, optional=True)
                values = {**entry, **outcome}
                intent = intentions.get(worker_id, {})
                prompt_path = worker_dir / 'prompt.txt'
                task = self.prompts.read(prompt_path, result.diagnostics) or safe_text(intent.get('task'))
                declared_role = string(intent.get('contract')) or string(mapping(values.get('contract')).get('role')) or string(intent.get('role'))
                role, role_evidence = identify_role(declared_role, task, worker_id)
                if role_evidence == 'função declarada nos metadados':
                    role_path = folder / 'plan.json' if string(intent.get('contract')) or string(intent.get('role')) else outcome_path
                elif role_evidence == 'atribuição explícita na tarefa':
                    role_path = prompt_path if prompt_path in self.prompts.values else folder / 'plan.json'
                else:
                    role_path = state_path
                worker_status = status(values.get("status"))
                if runner == "runner ausente" and worker_status in ("queued", "running"):
                    worker_status = "interrupted"
                cwd = string(values.get("cwd")) or string(intent.get("cwd"))
                metrics = mapping(values.get("metrics"))
                usage = mapping(metrics.get("usage"))
                token_count = reported_tokens(usage)
                evidence_path = outcome_path if outcome else state_path
                agent = Agent(
                    id="alethe:" + stable_id(str(folder), worker_id), source="alethe", source_id=worker_id,
                    execution_id=execution_id, project_id=cwd or execution_id + ":unknown-project",
                    name=ROLE_NAMES.get(role, safe_text(worker_id)), status=worker_status, parent_id=lead_id,
                    provider=safe_text(values.get("provider") or intent.get("provider")) or None,
                    model=safe_text(intent.get("model")) or None, task=task, cwd=cwd,
                    role=role, role_evidence=f'{role_path}: {role_evidence}' if role else '',
                    wave=safe_text(folder.name), effort=safe_text(intent.get('effort')) or None,
                    contract=intent.get("contract") if intent.get("contract") in ("developer", "reviewer", "qa") else None,
                    revision=safe_text(intent.get("revision")) or None,
                    diff_revision=safe_text(outcome.get("diffRevision")) or None,
                    has_diff=existing(worker_dir / "diff.patch") is not None,
                    wave_index=int(match[1]) if (match := re.match(r"^(\d+)-", folder.name)) else None,
                    task_path=str(prompt_path) if prompt_path in self.prompts.values else None,
                    started_at=string(values.get("startedAt")) or None,
                    finished_at=string(values.get("finishedAt")) or None,
                    last_activity=string(values.get("lastOutputAt")) or None,
                    idle_seconds=number(values.get("idleSeconds")),
                    session_id=string(values.get("sessionId")) or None,
                    tokens=token_count, cost_usd=number(metrics.get("totalCostUsd")),
                    evidence=f"{evidence_path}: workers/{worker_id}/status={worker_status}" + (f"; {runner}" if runner else ""),
                    output_path=existing(worker_dir / "stdout.log"), error_path=existing(worker_dir / "stderr.log"),
                    result_path=existing(worker_dir / "result.md"), error=safe_text(values.get("error")) or None,
                )
                agents.append(agent)
                def event(kind, timestamp, path, actor=None, target=None):
                    result.events.append(Event(
                        id="alethe:" + stable_id(str(folder), worker_id, kind, timestamp), kind=kind, source="alethe",
                        execution_id=execution_id, timestamp=timestamp, actor_id=actor or agent.id, target_id=target,
                        evidence=f"{path}: {kind} ({worker_id})"))
                if lead_id and task:
                    event("delegated", string(state.get("startedAt")) or None, prompt_path if agent.task_path else folder / "plan.json", lead_id, agent.id)
                if agent.started_at:
                    event("started", agent.started_at, state_path)
                if worker_status in ("succeeded", "turn_complete") and (agent.finished_at or agent.result_path):
                    event("result_available", agent.finished_at, evidence_path)
                elif worker_status in ("failed", "timed_out"):
                    event("failed", agent.finished_at, evidence_path)
            groups.setdefault(execution_id, []).append((group, meta, plan, state, wave_status, agents, lead_id))
            result.agents.extend(agents)
        for execution_id, waves in groups.items():
            group, meta, plan, state, _, _, lead_id = waves[0]
            self._gates(group, execution_id, result)
            agents = [agent for wave in waves for agent in wave[5]]
            project_ids = list(dict.fromkeys(agent.project_id for agent in agents))
            cwd = next((agent.cwd for agent in agents if agent.cwd), "")
            states = [wave[4] for wave in waves]
            execution_status = next((value for value in ("running", "queued", "unknown", "interrupted", "failed", "timed_out", "stopped") if value in states), states[-1])
            result.executions.append(Execution(
                id=execution_id, title=safe_text(meta.get("title") or plan.get("title") or group.name), source="alethe",
                project_id=project_ids[0] if project_ids else execution_id + ":unknown-project",
                project_name=safe_text(Path(cwd).name) if cwd else "não informado", project_path=cwd,
                project_ids=project_ids, status=execution_status,
                started_at=string(meta.get("createdAt") or state.get("startedAt")) or None,
                leader_id=lead_id, leader_name=(safe_text(mapping(meta.get("lead")).get("name") or mapping(meta.get("lead")).get("provider")) if not lead_id.endswith(":orchestrator") else "orquestrador") or "orquestrador"))
        return result
