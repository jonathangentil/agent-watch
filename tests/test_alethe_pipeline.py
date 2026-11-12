"""Pipeline observations from synthetic artifacts only."""
import json
from pathlib import Path

import pytest

from alethe_tui.adapters.alethe import AletheAdapter


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def wave(group, name="01-build", worker="dev-core", **intent):
    put(group / "orchestration.json", {"title": "Synthetic pipeline"})
    folder = group / name
    put(folder / "state.json", {"status": "running", "workers": {
        worker: {"status": "succeeded", "cwd": "/synthetic/project"}}})
    put(folder / "plan.json", {"workers": [{"id": worker, "task": "Synthetic task", **intent}]})
    return folder / "workers" / worker


def scan(group):
    return AletheAdapter([group], verify_pids=False).scan()


def gate_data(**kw):
    return {"gate": 1, "at": "2026-11-11T10:00:00Z", "decision": "REJECTED",
            "revision": "rev-x", "developers": ["dev-core"], "reviewers": [], "qa": ["qa-1"], **kw}


def test_pipeline_fields_from_plan_outcome_and_wave_name(tmp_path):
    worker = wave(tmp_path, contract="developer")
    put(worker / "outcome.json", {"diffRevision": "rev-a"})
    put(worker / "diff.patch", "synthetic diff")
    wave(tmp_path, "02-check", "qa-1", contract="qa", revision="rev-x")
    dev, qa = scan(tmp_path).agents
    assert (dev.contract, dev.diff_revision, dev.has_diff, dev.wave_index) == ("developer", "rev-a", True, 1)
    assert (qa.contract, qa.revision, qa.has_diff, qa.wave_index) == ("qa", "rev-x", False, 2)


def test_unknown_contract_and_unnumbered_wave_are_none(tmp_path):
    wave(tmp_path, "adhoc", contract="writer")
    a = scan(tmp_path).agents[0]
    assert a.contract is None and a.wave_index is None


def test_gates_are_read_from_orchestration_folder(tmp_path, monkeypatch):
    wave(tmp_path, contract="developer")
    wave(tmp_path, "02-check", "qa-1", contract="qa", revision="rev-x")
    path = put(tmp_path / "gate-01.json", gate_data(notes=["segredo"], blocked=["segredo"],
        rejected=["segredo"], incomplete=["segredo"], findingsPath="segredo"))
    original = Path.open
    opened = []
    def guarded(self, *args, **kw):
        if self == path:
            opened.append(self)
        return original(self, *args, **kw)
    monkeypatch.setattr(Path, "open", guarded)
    result = scan(tmp_path)
    assert len(result.gates) == 1
    g = result.gates[0]
    assert (g.number, g.at, g.decision, g.revision) == (1, "2026-11-11T10:00:00Z", "REJECTED", "rev-x")
    assert (g.developers, g.reviewers, g.qa) == (["dev-core"], [], ["qa-1"])
    assert g.execution_id == result.agents[0].execution_id
    assert g.evidence == f"{path}: gate 1 REJECTED"
    assert "segredo" not in repr(result.gates)
    assert len(opened) == 1


@pytest.mark.parametrize("content", ['{"gate":', '{"gate":true,"decision":"APPROVED"}',
    '{"gate":"2","decision":"APPROVED"}', '{"gate":2}'])
def test_partial_gate_is_diagnostic_and_skipped(tmp_path, content):
    wave(tmp_path)
    path = tmp_path / "gate-02.json"
    path.write_text(content)
    result = scan(tmp_path)
    assert result.gates == []
    assert any(d["status"] == "invalid" and d["message"] == "gate ignorado" and d["path"] == str(path)
               for d in result.diagnostics)


def test_invalid_gate_does_not_reuse_cached_approval(tmp_path):
    wave(tmp_path)
    path = put(tmp_path / "gate-01.json", gate_data(decision="APPROVED"))
    reader = AletheAdapter([tmp_path], verify_pids=False)
    assert len(reader.scan().gates) == 1
    path.write_text('{"gate":')
    assert reader.scan().gates == []


def test_diff_patch_content_is_never_opened(tmp_path, monkeypatch):
    worker = wave(tmp_path, contract="developer")
    patch = put(worker / "diff.patch", "synthetic diff")
    put(worker / "contract.json", {"findings": "private synthetic findings"})
    patch.chmod(0)
    original = Path.open
    def guarded(self, *args, **kw):
        assert self.name not in {"diff.patch", "contract.json"}, "private artifact was opened"
        return original(self, *args, **kw)
    monkeypatch.setattr(Path, "open", guarded)
    result = scan(tmp_path)
    assert result.agents[0].has_diff is True
    assert not any(d["path"] == str(patch) for d in result.diagnostics)


def test_sources_remain_unmodified(tmp_path):
    worker = wave(tmp_path, contract="developer")
    put(worker / "outcome.json", {"diffRevision": "rev-a"})
    put(worker / "diff.patch", "synthetic")
    put(tmp_path / "gate-01.json", gate_data())
    def contents():
        return {str(p): (p.stat().st_mtime_ns, p.read_bytes()) for p in tmp_path.rglob("*") if p.is_file()}
    before = contents()
    scan(tmp_path)
    assert contents() == before


def test_gate_participant_ids_preserve_source_identity(tmp_path):
    wave(tmp_path, worker="dev[core]", contract="developer")
    put(tmp_path / "gate-01.json", gate_data(developers=["dev[core]"]))
    result = scan(tmp_path)
    assert result.gates[0].developers == [result.agents[0].source_id]
