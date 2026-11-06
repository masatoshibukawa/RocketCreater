import pytest

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import sha, write_json
from scripts.report_design_search import summary


@pytest.mark.parametrize("failed_retry", [False, True])
def test_requested_refinement_is_not_reported_as_completed_confirmation(tmp_path, failed_retry):
    folder = tmp_path / "projects" / "final"
    artifact = folder / "confirm" / "data.json"
    old = dict(cfd_cells_fine=20, calculix="private/solver.exe")
    requested = dict(cfd_cells_fine=24, calculix="private/solver.exe")
    write_json(
        artifact,
        dict(
            checks=dict(aero_grid=False),
            unmet=["aero_grid"],
            flight=dict(apogee_m=22),
            static_margin_cal=0.4,
        ),
    )
    write_json(artifact.parent / "input.json", dict(runtime=old))
    write_json(
        artifact.parent / "manifest.json",
        {"data.json": sha(artifact), "input.json": sha(artifact.parent / "input.json")},
    )
    completed = dict(
        execution_status="completed",
        value=dict(artifact=str(artifact), sha256=sha(artifact)),
    )
    completed["artifact_hash"] = digest(completed)
    write_json(artifact.parent / "result.json", completed)
    write_json(folder / "unfinished" / "case.json", {"partial_attempt": True})
    write_json(
        folder / "state.json",
        dict(
            adaptive=dict(
                runtime=requested,
                decisions=[],
                history=[
                    dict(
                        action="confirm",
                        execution_status="completed",
                        artifact_hash=completed["artifact_hash"],
                    )
                ],
                results=dict(
                    confirm=dict(execution_status="failed", value=dict(error="timeout"))
                    if failed_retry
                    else completed
                ),
            )
        ),
    )
    write_json(
        tmp_path / "report.json",
        dict(
            campaigns=[dict(project_id="final", label="detailed-confirmation")],
            observations=[],
            final=dict(
                project_id="final",
                status="unresolved",
                confirmation=None,
                unresolved_precision=["aero_grid"],
            ),
            source_hash="source",
            requirement_hash="requirement",
            precision={},
            limits={},
            selected=dict(start="initial", version=2, spec={}, metrics={}),
            elapsed_s=20,
        ),
    )
    result = summary(tmp_path)
    final = result["final"]
    assert final["checks"] is None and final["apogee_m"] is None
    assert final["accepted_spec_hash"] is None
    assert final["latest_requested_runtime"]["cfd_cells_fine"] == 24
    reported = final["last_completed_artifacts"]["confirm"]
    assert reported["runtime"]["cfd_cells_fine"] == 20
    assert reported["checks"]["aero_grid"] is False
    assert reported["apogee_m"] == 22
    assert "private/solver.exe" not in str(result)
    assert result["evidence"]["referenced_files"] == 2
    assert result["evidence"]["verified_gpu_case_files"] == 0
    assert final["gpu_case_files_saved"] == 1 and final["completed_gpu_case_files"] == 0
    completed["value"]["sha256"] = "altered-after-completion"
    write_json(artifact.parent / "result.json", completed)
    with pytest.raises(ValueError, match="Invalid archived"):
        summary(tmp_path)
