"""Contrato do Kanban: tipos serializáveis e defaults que não inventam fatos."""
from dataclasses import asdict

from alethe_tui.model import COLUMNS, Agent, Gate, ScanResult, Task, Transition


def test_task_contract_serializes_with_defaults():
    task = Task(id="task:a", execution_id="e", project_id="p", agent_id="a", title="t",
                column="backlog", column_evidence="x")
    data = asdict(task)
    assert data["badges"] == [] and data["testers"] == [] and data["transitions"] == []
    assert data["gate"] is None and data["gate_decision"] is None and data["superseded_by_wave"] is None
    assert COLUMNS == ("backlog", "in_progress", "awaiting_tests", "testing", "done", "blocked")
    first = Task(id="1", execution_id="e", project_id="p", agent_id="a", title="t", column="done", column_evidence="")
    first.badges.append("delivered")
    assert task.badges == []


def test_transition_and_gate_shapes():
    assert asdict(Transition(column="done", at=None, evidence="x")) == {"column": "done", "at": None, "evidence": "x"}
    gate = Gate(execution_id="e", number=1, decision="APPROVED")
    assert (gate.revision, gate.developers, gate.reviewers, gate.qa, gate.at, gate.evidence) == (None, [], [], [], None, "")


def test_agent_pipeline_fields_default_to_unknown():
    agent = Agent(id="a", source="alethe", source_id="w", execution_id="e", project_id="p", name="w")
    assert agent.contract is None and agent.revision is None and agent.diff_revision is None
    assert agent.has_diff is None and agent.wave_index is None


def test_scan_result_has_gates():
    assert ScanResult().gates == []
