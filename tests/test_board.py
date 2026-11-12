"""Evidence-only board rules, using synthetic agents and gates."""
from copy import deepcopy

import pytest

from alethe_tui.board import build_tasks
from alethe_tui.model import Agent, Execution, Gate


def agent(**kw):
    values = dict(id="a", source="alethe", source_id="dev-core", execution_id="e", project_id="p",
                  name="Synthetic worker", status="queued", task="Synthetic task", evidence="state.json: status")
    values.update(kw)
    return Agent(**values)


def dev(**kw):
    values = dict(contract="developer", wave_index=1, status="succeeded")
    values.update(kw)
    return agent(**values)


def qa_agent(**kw):
    values = dict(id="qa", source_id="qa-1", contract="qa", wave_index=2, status="running", revision="rev-x")
    values.update(kw)
    return agent(**values)


def gate(**kw):
    values = dict(execution_id="e", number=1, decision="APPROVED", revision="rev-x",
                  developers=["dev-core"], qa=["qa-1"], evidence="gate-01.json: gate 1 APPROVED")
    values.update(kw)
    return Gate(**values)


def run(*agents, gates=(), events=()):
    return build_tasks(agents, events, gates, [Execution("e", "Synthetic", "alethe", "p", "P", "/synthetic", leader_id="lead")])


def card(tasks, id="a"):
    return next(t for t in tasks if t.agent_id == id)


def at(minute):
    return f"2026-11-11T10:{minute:02}:00Z"


@pytest.mark.parametrize("status,fields,column,badge", [
    ("queued", {}, "backlog", None), ("running", {}, "in_progress", "running"),
    ("unknown", {"last_activity": at(1)}, "in_progress", "unconfirmed"),
    ("unknown", {"started_at": at(1)}, "in_progress", "unconfirmed"),
    ("unknown", {}, "backlog", "unconfirmed"),
    *[(s, {}, "blocked", None) for s in ("failed", "timed_out", "interrupted", "stopped")],
    ("skipped", {}, "blocked", "skipped")])
def test_plain_status_columns(status, fields, column, badge):
    t = run(agent(status=status, **fields))[0]
    assert t.column == column
    if badge:
        assert badge in t.badges
    assert t.column_evidence.startswith("state.json:")


def test_plain_completion_delivery_badges():
    t = run(agent(status="succeeded"), events=[{"kind": "result_delivered", "actor_id": "a"}])[0]
    assert t.column == "done" and t.badges == ["delivered"]
    t = run(agent(status="turn_complete"), events=[{"kind": "result_delivered", "actor_id": "other"}])[0]
    assert t.column == "done" and t.badges == ["delivery_unconfirmed"]


def test_leader_and_linked_testers_are_not_cards():
    assert [t.agent_id for t in run(agent(id="lead"), dev(), qa_agent())] == ["a"]


def test_developer_without_tester_awaits_tests_and_flags_missing_diff():
    t = run(dev(has_diff=False))[0]
    assert t.column == "awaiting_tests" and "no_diff" in t.badges
    assert t.testers == []


def test_running_tester_moves_developer_to_testing_by_wave():
    t = run(dev(), qa_agent())[0]
    assert t.column == "testing" and "link_by_wave" in t.badges
    assert t.testers == ["qa"] and t.revision == "rev-x"


def test_queued_tester_keeps_awaiting_tests():
    t = run(dev(), qa_agent(status="queued"))[0]
    assert t.column == "awaiting_tests"


def test_tester_without_revision_leaves_link_unconfirmed():
    t = card(run(dev(), qa_agent(revision=None)))
    assert t.column == "awaiting_tests" and "link_unconfirmed" in t.badges
    assert t.testers == [] and t.revision is None


def test_finished_tester_without_gate_stays_testing():
    t = run(dev(), qa_agent(status="succeeded"))[0]
    assert t.column == "testing" and "tests_finished" in t.badges


@pytest.mark.parametrize("status", ["failed", "timed_out", "interrupted", "stopped", "skipped"])
def test_failed_tester_blocks_developer(status):
    t = run(dev(), qa_agent(status=status, finished_at=at(4)))[0]
    assert t.column == "blocked"
    assert t.transitions[-1].at == at(4)


@pytest.mark.parametrize("decision,column,badge", [("APPROVED", "done", "link_confirmed"),
    ("REJECTED", "blocked", "gate_rejected"), ("BLOCKED", "blocked", "gate_blocked")])
def test_gate_decisions(decision, column, badge):
    g = gate(decision=decision)
    t = run(dev(), qa_agent(), gates=[g])[0]
    assert t.column == column and badge in t.badges
    assert t.gate == 1 and t.gate_decision == decision
    assert t.column_evidence.startswith(g.evidence)
    assert t.testers == ["qa"] and t.revision == "rev-x"


def test_rejected_round_is_superseded_by_later_developer_wave():
    tasks = run(dev(), qa_agent(), dev(id="fix", wave_index=3, status="failed"), gates=[gate(decision="REJECTED")])
    old = card(tasks)
    assert old.column == "blocked" and "superseded" in old.badges and old.superseded_by_wave == 3
    assert [t.agent_id for t in tasks] == ["fix", "a"]


def test_repeated_worker_ids_across_waves_are_separate_cards():
    old = dev(id="wave1:dev", started_at=at(1), finished_at=at(2))
    new = dev(id="wave3:dev", wave_index=3, started_at=at(5), finished_at=at(6))
    q1 = qa_agent(id="wave2:qa", started_at=at(3), finished_at=at(4), status="succeeded")
    q2 = qa_agent(id="wave4:qa", wave_index=4, started_at=at(7), revision="rev-y")
    tasks = run(old, new, q1, q2, gates=[gate(at=at(4), decision="REJECTED"),
                 gate(number=2, at=at(8), revision="rev-y")])
    assert {t.id for t in tasks} == {"task:wave1:dev", "task:wave3:dev"}
    assert card(tasks, old.id).gate == 1 and card(tasks, old.id).column == "blocked"
    assert card(tasks, new.id).gate == 2 and card(tasks, new.id).column == "done"
    assert card(tasks, old.id).testers == [q1.id]
    assert card(tasks, new.id).testers == [q2.id]


def test_latest_gate_for_same_wave_wins():
    for gates in ([gate(number=2), gate(decision="BLOCKED")], [gate(decision="BLOCKED"), gate(number=2)]):
        t = run(dev(), qa_agent(), gates=gates)[0]
        assert t.column == "done" and t.gate == 2 and t.gate_decision == "APPROVED"


def test_gate_without_matching_developer_never_marks_done():
    t = run(dev(), qa_agent(), gates=[gate(developers=["missing"])])[0]
    assert t.column == "testing"
    assert t.column_evidence.endswith("; divergência: gate 1 sem developer correspondente")
    assert t.gate is None


def test_tester_without_previous_developer_wave_is_plain_card():
    t = run(qa_agent())[0]
    assert t.agent_id == "qa" and t.column == "in_progress" and "link_unconfirmed" in t.badges


def test_transitions_follow_recorded_times():
    t = run(dev(started_at=at(1), finished_at=at(2)), qa_agent(started_at=at(3)),
            gates=[gate(at=at(4))], events=[{"kind": "delegated", "target_id": "a", "timestamp": at(0), "evidence": "plan"}])[0]
    assert [s.column for s in t.transitions] == ["backlog", "in_progress", "awaiting_tests", "testing", "done"]
    assert [s.at for s in t.transitions] == [at(i) for i in range(5)]
    assert t.updated_at == at(4)
    assert all(s.evidence for s in t.transitions)


def test_missing_times_stay_none_and_last_transition_matches_column():
    tasks = run(dev(), qa_agent(), agent(id="plain", status="succeeded"), agent(id="queued"),
                gates=[gate()])
    for t in tasks:
        assert t.transitions[-1].column == t.column
        assert all(s.at is None for s in t.transitions)
        assert t.updated_at is None


def test_column_order_and_recency():
    tasks = run(agent(id="z", status="failed"), agent(id="done", status="succeeded"),
        agent(id="b", status="running", started_at=at(1)), agent(id="a", status="running", started_at=at(1)),
        agent(id="new", status="running", started_at="2026-11-11T08:02:00-02:00"),
        dev(id="d"), agent(id="q"), agent(id="bad", status="running", started_at="invalid"))
    assert [t.agent_id for t in tasks] == ["q", "new", "a", "b", "bad", "d", "done", "z"]
    assert card(tasks, "bad").updated_at is None


def test_linking_uses_nearest_developer_wave_in_same_execution():
    tasks = run(dev(), dev(id="fix", wave_index=3), qa_agent(wave_index=4),
                qa_agent(id="foreign", execution_id="other", wave_index=2))
    assert card(tasks).column == "awaiting_tests"
    assert card(tasks, "fix").testers == ["qa"]
    assert card(tasks, "foreign").column == "in_progress"


def test_failure_takes_priority_over_another_running_qa_agent():
    t = run(dev(), qa_agent(), qa_agent(id="review", source_id="r", contract="reviewer", status="failed"))[0]
    assert t.column == "blocked"


def test_gate_requires_tester_started_before_gate_and_matching_execution():
    for g in [gate(at=at(1)), gate(execution_id="other")]:
        t = run(dev(), qa_agent(started_at=at(2)), gates=[g])[0]
        assert t.column == "testing" and t.gate is None


def test_build_tasks_is_pure_and_accepts_iterables():
    inputs = ([dev()], [{"kind": "delegated", "target_id": "a", "timestamp": at(0)}], [gate()], [])
    before = deepcopy(inputs)
    result = build_tasks(*(iter(items) for items in inputs))
    assert result[0].id == "task:a" and result[0].title == "Synthetic task"
    assert inputs == before
    assert run(agent(task=""))[0].title == "tarefa sem descrição registrada"


def test_failed_tester_evidence_preserves_developer_context():
    t = run(dev(evidence="dev/outcome.json: succeeded"),
            qa_agent(status="failed", evidence="qa/outcome.json: failed"))[0]
    assert t.column_evidence.startswith("dev/outcome.json: succeeded")
    assert "qa/outcome.json: failed" in t.column_evidence


def test_latest_gate_resolves_wave_using_datetime_offsets():
    # Same source IDs, but the later tester had not started at the first gate.
    tasks = run(dev(), dev(id="new", wave_index=3),
        qa_agent(id="old-qa", started_at="2026-11-11T07:00:00-03:00"),
        qa_agent(id="new-qa", wave_index=4, started_at="2026-11-11T12:00:00Z"),
        gates=[gate(at="2026-11-11T11:00:00+00:00")])
    assert card(tasks).column == "done"
    assert card(tasks, "new").column == "testing" and card(tasks, "new").gate is None


def test_developer_still_running_does_not_take_gate_decision():
    t = run(dev(status="running"), qa_agent(), gates=[gate()])[0]
    assert t.column == "in_progress" and t.gate is None


def test_invalid_dates_stay_none_in_transitions():
    t = run(dev(started_at="invalid", finished_at="invalid", last_activity="invalid"),
            qa_agent(started_at="invalid"), gates=[gate(at="invalid")])[0]
    assert t.column == "done" and t.updated_at is None
    assert all(step.at is None for step in t.transitions)


def test_leader_exclusion_is_scoped_to_its_execution():
    executions = [Execution("e", "E", "alethe", "p", "P", "/synthetic", leader_id="shared"),
                  Execution("other", "Other", "alethe", "p", "P", "/synthetic", leader_id="other-lead")]
    tasks = build_tasks([agent(id="shared", execution_id="other")], [], [], executions)
    assert [t.agent_id for t in tasks] == ["shared"]


@pytest.mark.parametrize("decision", ["APPROVED", "REJECTED", "BLOCKED"])
def test_gate_revision_mismatch_uses_no_gate_rules(decision):
    t = run(dev(diff_revision="rev-patch"), qa_agent(revision="rev-tested"),
            gates=[gate(decision=decision, revision="rev-other")])[0]
    assert t.column == "testing" and t.gate is None and t.gate_decision is None
    assert t.revision == "rev-tested" and "link_confirmed" not in t.badges
    assert t.column_evidence.endswith("; divergência: gate 1 revisão rev-other difere da revisão testada rev-tested")


def test_gate_matches_combined_tester_revision_not_individual_patch():
    t = run(dev(diff_revision="rev-patch"), qa_agent(revision="rev-combined"),
            gates=[gate(revision="rev-combined")])[0]
    assert t.column == "done" and t.gate == 1 and t.revision == "rev-combined"
    assert "link_confirmed" in t.badges and "divergência" not in t.column_evidence


def test_mixed_completed_and_queued_testers_stay_testing_without_regression():
    t = run(dev(started_at=at(0), finished_at=at(1)),
            qa_agent(status="succeeded", started_at=at(2), finished_at=at(3)),
            qa_agent(id="review", source_id="r", contract="reviewer", status="queued"))[0]
    columns = [transition.column for transition in t.transitions]
    assert columns == ["in_progress", "awaiting_tests", "testing"]
    assert t.column == "testing" and "link_by_wave" in t.badges
    assert "tests_finished" not in t.badges
    assert "awaiting_tests" not in columns[columns.index("testing") + 1:]


def test_untimed_gates_follow_repeated_tester_wave_order():
    agents = [dev(id="old"), dev(id="new", wave_index=3),
              qa_agent(id="old-qa", status="succeeded"),
              qa_agent(id="new-qa", wave_index=4)]
    # Even a single first gate belongs to the first matching tester wave.
    tasks = run(*reversed(agents), gates=[gate(decision="REJECTED")])
    assert card(tasks, "old").column == "blocked" and card(tasks, "old").gate == 1
    assert card(tasks, "new").column == "testing" and card(tasks, "new").gate is None
    tasks = run(*agents, gates=[gate(number=2), gate(decision="REJECTED")])
    assert card(tasks, "old").gate == 1 and card(tasks, "old").column == "blocked"
    assert card(tasks, "new").gate == 2 and card(tasks, "new").column == "done"


def test_unresolved_gate_reports_divergence_for_named_developers():
    tasks = run(dev(), dev(id="other", source_id="other-dev"), qa_agent(),
                gates=[gate(qa=["qa-typo"])])
    t = card(tasks)
    assert t.column == "testing" and t.gate is None
    assert t.column_evidence.endswith("; divergência: gate 1 sem onda correspondente")
    assert "divergência" not in card(tasks, "other").column_evidence


def test_gate_omitting_sibling_developer_reports_divergence():
    tasks = run(dev(), dev(id="ui", source_id="dev-ui"), qa_agent(), gates=[gate()])
    assert card(tasks).column == "done"
    t = card(tasks, "ui")
    assert t.column == "testing" and t.gate is None
    assert t.column_evidence.endswith("; divergência: gate 1 sem developer correspondente")


def test_latest_gate_omitting_developer_does_not_reuse_previous_approval():
    tasks = run(dev(), dev(id="ui", source_id="dev-ui"), qa_agent(),
                gates=[gate(developers=["dev-core", "dev-ui"]), gate(number=2)])
    assert card(tasks).column == "done" and card(tasks).gate == 2
    t = card(tasks, "ui")
    assert t.column == "testing" and t.gate is None
    assert t.column_evidence.endswith("; divergência: gate 2 sem developer correspondente")


@pytest.mark.parametrize("decision", ["unknown", "PENDING"])
def test_unknown_gate_decision_does_not_override_valid_gate(decision):
    t = run(dev(), qa_agent(), gates=[gate(), gate(number=2, decision=decision)])[0]
    assert t.column == "done" and t.gate == 1 and t.gate_decision == "APPROVED"


@pytest.mark.parametrize("status", ["queued", "running", "failed", "skipped"])
def test_tester_without_completed_developer_is_plain_card(status):
    tasks = run(dev(status=status), qa_agent())
    t = card(tasks, "qa")
    assert t.column == "in_progress" and "link_unconfirmed" in t.badges
    assert card(tasks).testers == []


def test_skipped_worker_without_start_has_no_in_progress_transition():
    t = run(agent(status="skipped"), events=[{"kind": "delegated", "target_id": "a", "timestamp": at(0)}])[0]
    assert t.column == "blocked" and "skipped" in t.badges
    assert [step.column for step in t.transitions] == ["backlog", "blocked"]
    assert [step.at for step in t.transitions] == [at(0), None]


def test_gate_without_revision_keeps_tester_revision():
    t = run(dev(), qa_agent(revision="rev-tested"), gates=[gate(revision=None)])[0]
    assert t.column == "done" and t.gate == 1 and t.revision == "rev-tested"


def test_gate_revision_and_testers_use_selected_tester_wave():
    tasks = run(dev(diff_revision="rev-patch"),
                qa_agent(id="first-qa", status="succeeded", revision="rev-first"),
                qa_agent(id="second-qa", wave_index=3, revision="rev-second"),
                gates=[gate(decision="REJECTED", revision="rev-first"),
                       gate(number=2, revision="rev-second")])
    t = card(tasks)
    assert t.column == "done" and t.gate == 2 and t.revision == "rev-second"
    assert t.testers == ["second-qa"]
    assert "divergência" not in t.column_evidence
