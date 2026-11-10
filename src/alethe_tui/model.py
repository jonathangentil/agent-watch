"""Contrato compartilhado dos leitores, monitor e interfaces.

Horários são strings ISO 8601 ou None; métricas ausentes nunca viram zero.
Os leitores retornam observações, sem alterar os arquivos de origem.
"""
from dataclasses import dataclass, field


@dataclass
class Agent:
    id: str
    source: str
    source_id: str
    execution_id: str
    project_id: str
    name: str
    status: str = "unknown"
    parent_id: str | None = None
    provider: str | None = None
    model: str | None = None
    task: str = ""
    cwd: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    last_activity: str | None = None
    idle_seconds: float | None = None
    session_id: str | None = None
    tokens: int | None = None
    cost_usd: float | None = None
    evidence: str = "estado não confirmado"
    output_path: str | None = None
    error_path: str | None = None
    result_path: str | None = None
    error: str | None = None
    role: str | None = None
    role_evidence: str = ""
    wave: str | None = None
    effort: str | None = None
    task_path: str | None = None
    tokens_partial: bool = False


@dataclass
class Execution:
    id: str
    title: str
    source: str
    project_id: str
    project_name: str
    project_path: str
    status: str = "unknown"
    started_at: str | None = None
    session_id: str | None = None
    leader_id: str | None = None
    leader_name: str = "principal"
    leader_status: str = "unknown"
    project_ids: list[str] = field(default_factory=list)


@dataclass
class Event:
    id: str
    kind: str
    source: str
    execution_id: str
    timestamp: str | None = None
    actor_id: str | None = None
    target_id: str | None = None
    label: str = ""
    evidence: str = ""


@dataclass
class ScanResult:
    agents: list[Agent] = field(default_factory=list)
    executions: list[Execution] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    diagnostics: list[dict] = field(default_factory=list)
