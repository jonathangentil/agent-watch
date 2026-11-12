"""Pure, evidence-based task projection shared by monitor interfaces."""
from collections.abc import Iterable
from datetime import datetime, timezone

from .model import Agent, COLUMNS, Execution, Gate, Task, Transition

_COMPLETE = {"succeeded", "turn_complete"}
_FAILED = {"failed", "timed_out", "interrupted", "stopped", "skipped"}
_TESTERS = {"reviewer", "qa"}


def _date(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (AttributeError, TypeError, ValueError):
        return None


def _time(value):
    return value if _date(value) is not None else None


def _previous_wave(developers, tester_wave):
    return max((d.wave_index for d in developers if d.wave_index is not None
                and tester_wave is not None and d.wave_index < tester_wave), default=None)


def _tester_wave(gate, testers):
    when = _date(gate.at)
    named = set(gate.reviewers + gate.qa)
    if when is None:
        participants = {}
        for tester in testers:
            if tester.wave_index is not None:
                participants.setdefault(tester.wave_index, set()).add(tester.source_id)
        waves = sorted(wave for wave, ids in participants.items() if named and named <= ids)
        # Retests can produce more gates than waves. Once the ordered waves
        # are exhausted, subsequent gates still refer to the last wave.
        return waves[min(max(gate.number - 1, 0), len(waves) - 1)] if waves else None
    waves = [t.wave_index for t in testers if t.source_id in named and t.wave_index is not None
             and _date(t.started_at) is not None and _date(t.started_at) <= when]
    return max(waves, default=None)


def _gate_wave(gate, developers, testers):
    return _previous_wave(developers, _tester_wave(gate, testers))


def _plain(task, agent, events):
    if agent.status in _FAILED:
        task.column = "blocked"
        if agent.status == "skipped":
            task.badges.append("skipped")
    elif agent.status in _COMPLETE:
        task.column = "done"
        delivered = any(e.get("kind") == "result_delivered" and e.get("actor_id") == agent.id for e in events)
        task.badges.append("delivered" if delivered else "delivery_unconfirmed")
    elif agent.status == "running":
        task.column = "in_progress"
        task.badges.append("running")
    elif agent.status == "unknown":
        task.column = "in_progress" if _time(agent.started_at) or _time(agent.last_activity) else "backlog"
        task.badges.append("unconfirmed")


def _pipeline(task, agent, developers, potential, gates, unresolved, testers):
    linked = [t for t in potential if t.revision]
    task.testers = [t.id for t in linked]
    task.revision = next((t.revision for t in linked), None)
    task.column = "awaiting_tests"
    if agent.has_diff is False:
        task.badges.append("no_diff")
    if any(not t.revision for t in potential):
        task.badges.append("link_unconfirmed")
    failures = [t for t in linked if t.status in _FAILED]
    if failures:
        task.column = "blocked"
        task.column_evidence += "; " + failures[0].evidence
    elif any(t.status in _COMPLETE | {"running"} or _time(t.started_at) for t in linked):
        task.column = "testing"
        task.badges.append("link_by_wave")
        if all(t.status in _COMPLETE for t in linked):
            task.badges.append("tests_finished")

    unresolved_evidence = "".join(f"; divergência: gate {g.number} sem onda correspondente"
                                  for g in sorted(unresolved, key=lambda g: g.number))
    task.column_evidence += unresolved_evidence
    candidates = [g for g in gates if g.decision in {"APPROVED", "REJECTED", "BLOCKED"}]
    chosen = max(candidates, key=lambda g: g.number, default=None)
    if chosen and agent.source_id not in chosen.developers:
        task.column_evidence += f"; divergência: gate {chosen.number} sem developer correspondente"
        return linked, None
    if chosen:
        tested_wave = _tester_wave(chosen, testers)
        revisions = sorted({t.revision for t in linked if t.wave_index == tested_wave})
        mismatch = next((revision for revision in revisions if revision != chosen.revision), None)
        # Both values describe the combined wave. A developer's diff_revision
        # identifies just one patch and must not participate in this comparison.
        if chosen.revision is not None and mismatch is not None:
            task.column_evidence += (f"; divergência: gate {chosen.number} revisão {chosen.revision}"
                                     f" difere da revisão testada {mismatch}")
            return linked, None
    if chosen and chosen.decision in {"APPROVED", "REJECTED", "BLOCKED"}:
        task.gate, task.gate_decision = chosen.number, chosen.decision
        if chosen.revision is not None:
            task.revision = chosen.revision
        elif revisions:
            task.revision = revisions[0]
        task.column_evidence = chosen.evidence + unresolved_evidence
        # Gate participants confirm which testers verified this developer wave.
        names = set(chosen.reviewers + chosen.qa)
        task.testers = [t.id for t in linked if t.source_id in names and t.wave_index == tested_wave]
        task.badges = [b for b in task.badges if b not in {"link_by_wave", "link_unconfirmed", "tests_finished"}]
        if chosen.decision == "APPROVED":
            task.column = "done"
            task.badges.append("link_confirmed")
        else:
            task.column = "blocked"
            task.badges.append("gate_rejected" if chosen.decision == "REJECTED" else "gate_blocked")
            later = [d.wave_index for d in developers if d.wave_index is not None
                     and agent.wave_index is not None and d.wave_index > agent.wave_index]
            if later:
                task.badges.append("superseded")
                task.superseded_by_wave = min(later)
        return linked, chosen
    return linked, None


def _transitions(task, agent, events, testers, gate):
    def add(column, when, evidence):
        task.transitions.append(Transition(column, _time(when), evidence))

    delegated = [e for e in events if e.get("kind") == "delegated" and e.get("target_id") == agent.id]
    if delegated or agent.status == "queued":
        event = delegated[0] if delegated else {}
        add("backlog", event.get("timestamp"), event.get("evidence") or agent.evidence)
    if (_time(agent.started_at) or agent.status in _COMPLETE | (_FAILED - {"skipped"}) | {"running"}
            or (agent.status == "unknown" and _time(agent.last_activity))):
        add("in_progress", agent.started_at, agent.evidence)
    if agent.contract == "developer" and agent.status in _COMPLETE:
        add("awaiting_tests", agent.finished_at, agent.evidence)
        started = [t for t in testers if _time(t.started_at)]
        active = [t for t in testers if t.status in _COMPLETE | _FAILED | {"running"}]
        if started or active:
            first = min(started, key=lambda t: _date(t.started_at)) if started else active[0]
            add("testing", first.started_at, first.evidence)
        if gate:
            add(task.column, gate.at, gate.evidence)
        elif task.column == "blocked":
            failed = next(t for t in testers if t.status in _FAILED)
            add("blocked", failed.finished_at, failed.evidence)
    elif task.column in {"done", "blocked"}:
        add(task.column, agent.finished_at, task.column_evidence)
    if not task.transitions or task.transitions[-1].column != task.column:
        add(task.column, None, task.column_evidence)
    task.updated_at = next((t.at for t in reversed(task.transitions) if t.at is not None), _time(agent.last_activity))


def build_tasks(agents: Iterable[Agent], events: Iterable[dict], gates: Iterable[Gate],
                executions: Iterable[Execution]) -> list[Task]:
    """Project recorded facts without reading artifacts or consulting a clock."""
    agents, events, gates = list(agents), list(events), list(gates)
    leaders = {e.id: e.leader_id for e in executions}
    groups = {}
    for agent in agents:
        if agent.id != leaders.get(agent.execution_id):
            groups.setdefault(agent.execution_id, []).append(agent)
    tasks = []
    for execution_id, members in groups.items():
        developers = [a for a in members if a.contract == "developer"]
        completed_waves = {d.wave_index for d in developers if d.status in _COMPLETE and d.wave_index is not None}
        testers = [a for a in members if a.contract in _TESTERS]
        links = {t.id: _previous_wave(developers, t.wave_index) for t in testers}
        wave_gates = [(g, _gate_wave(g, developers, testers)) for g in gates
                      if g.execution_id == execution_id and g.decision in {"APPROVED", "REJECTED", "BLOCKED"}]
        for agent in members:
            if agent.contract in _TESTERS and links[agent.id] in completed_waves and agent.revision:
                continue
            task = Task(id="task:" + agent.id, execution_id=execution_id, project_id=agent.project_id,
                        agent_id=agent.id, title=agent.task or "tarefa sem descrição registrada",
                        column="backlog", column_evidence=agent.evidence)
            linked, chosen = [], None
            if agent.contract == "developer" and agent.status in _COMPLETE:
                potential = [t for t in testers if agent.wave_index is not None and links[t.id] == agent.wave_index]
                applicable = [g for g, wave in wave_gates if wave is not None and wave == agent.wave_index]
                unresolved = [g for g, wave in wave_gates if wave is None
                              and (agent.source_id in g.developers
                                   or not any(d.source_id in g.developers for d in developers))]
                linked, chosen = _pipeline(task, agent, developers, potential, applicable, unresolved, testers)
            else:
                _plain(task, agent, events)
                if agent.contract in _TESTERS:
                    task.badges.append("link_unconfirmed")
            _transitions(task, agent, events, linked, chosen)
            tasks.append(task)
    def order(task):
        when = _date(task.updated_at)
        return (COLUMNS.index(task.column), "superseded" in task.badges,
                -when.timestamp() if when else float("inf"), task.id)
    return sorted(tasks, key=order)
