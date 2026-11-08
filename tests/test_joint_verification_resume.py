import pytest

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.schema import Precision
from scripts import verify_joint_candidate as runner
from tests.test_analysis_record import spec


def parent(root):
    folder = root / "geometry"
    write_json(folder / "data.json", {"metrics": {"geometry_valid": True}})
    write_json(folder / "manifest.json", {"data.json": sha(folder / "data.json")})
    write_json(
        root / "report.json",
        dict(
            source_hash="fixed",
            source_unchanged=True,
            spec=spec().model_dump(mode="json"),
            precision=Precision().model_dump(),
            runtime=Runtime(calculix="old-transport").model_dump(mode="json"),
            results=[
                dict(
                    method="geometry",
                    status="completed",
                    manifest_sha256=sha(folder / "manifest.json"),
                )
            ],
        ),
    )


def test_resume_reuses_only_verified_same_source_inputs(tmp_path, monkeypatch):
    original = tmp_path / "original"
    parent(original)
    monkeypatch.setattr(runner, "code_hash", lambda: "fixed")
    monkeypatch.setattr(runner, "METHODS", ("geometry", "confirm"))
    executed = []

    def fake_process(command, **kwargs):
        executed.append(command[-1])
        write_json(runner.Path(command[-2]), {"metrics": {"criteria_met": False}})

    monkeypatch.setattr(runner, "run_process", fake_process)
    result = runner.verify(
        spec(), Runtime(calculix="new-transport"), tmp_path / "resumed", resume=original
    )
    assert executed == ["confirm"]
    assert result["complete"] and result["source_unchanged"]
    assert not result["confirmation"]["metrics"]["criteria_met"]
    assert result["results"][0]["reused_from"] == str(original / "geometry")


@pytest.mark.parametrize("changed", ["source", "payload", "artifact"])
def test_resume_rejects_changes_instead_of_inheriting_results(tmp_path, monkeypatch, changed):
    original = tmp_path / "original"
    parent(original)
    s = spec()
    monkeypatch.setattr(
        runner, "code_hash", lambda: "different" if changed == "source" else "fixed"
    )
    if changed == "payload":
        s.design = s.design.model_copy(update={"payload_mass_kg": 0.1})
    if changed == "artifact":
        write_json(original / "geometry/data.json", {})
    with pytest.raises(ValueError):
        runner.verify(s, Runtime(calculix="new-transport"), tmp_path / "resumed", resume=original)
