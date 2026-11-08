import pytest

from rocketwright.agent.design_projects import sha, write_json
from scripts import run_learning_stages as stages


def test_report_resume_counts_both_stages_without_running_solvers(tmp_path, monkeypatch):
    for stage in ("stage5", "stage6"):
        folder = tmp_path / stage / "projects" / "example" / "runs" / "one"
        folder.mkdir(parents=True)
        write_json(folder / "data.json", {"complete": True})
        write_json(folder / "manifest.json", {"data.json": sha(folder / "data.json")})
    project = tmp_path / "stage6" / "projects" / "example"
    write_json(project / "state.json", {"id": "example", "adaptive": {"status": "unresolved"}})
    monkeypatch.setattr(stages, "code_hash", lambda: "fixed")
    monkeypatch.setattr(
        stages, "summary", lambda *args: ({"checks": {}, "unmet": ["aero_grid"]}, {}, {})
    )
    monkeypatch.setattr(stages.Harness, "options", lambda *args: {"offered": {}, "rejected": {}})
    result = stages.finish_stage6({"source_hash": "fixed"}, tmp_path, "fixed")
    assert result["evidence"]["stage5"]["referenced_files"] == 1
    assert result["evidence"]["stage6"]["referenced_files"] == 1
    assert result["stage6"]["unmet"] == ["aero_grid"]
    assert (tmp_path / "stage6-summary.json").exists()


@pytest.mark.parametrize("failure", ["source", "running"])
def test_report_resume_rejects_wrong_source_or_unfinished_project(tmp_path, monkeypatch, failure):
    project = tmp_path / "stage6" / "projects" / "example"
    project.mkdir(parents=True)
    write_json(project / "state.json", {"adaptive": {"status": "running"}})
    monkeypatch.setattr(stages, "code_hash", lambda: "fixed")
    with pytest.raises(ValueError):
        stages.finish_stage6(
            {"source_hash": "different" if failure == "source" else "fixed"}, tmp_path, "fixed"
        )
