import copy

import pytest

from rocketwright.agent.design_projects import sha, write_json
from scripts.report_initial_models import compare, verified


def test_different_inputs_or_failed_cases_cannot_claim_speedup():
    base = dict(
        source_hash="same",
        requirement={},
        precision={},
        controlled_fields=[],
        budget_s=100,
        elapsed_s=10,
        ranked_ids=["a"],
        results=[dict(label="a", status="completed", spec={"mass": 1}, metrics=dict(apogee_m=10))],
    )
    other = copy.deepcopy(base)
    other["elapsed_s"] = 20
    result = compare(base, other)
    assert result["numerically_equivalent"]
    assert result["wall_time_ratio_serial_over_parallel"] == 2
    other["results"][0]["spec"]["mass"] = 2
    with pytest.raises(ValueError, match="candidates differ"):
        compare(base, other)
    other = copy.deepcopy(base)
    other["results"][0]["status"] = "failed"
    assert compare(base, other)["wall_time_ratio_serial_over_parallel"] is None


def test_changed_summary_or_artifact_is_rejected(tmp_path):
    folder = tmp_path / "s00"
    result = dict(label="a", status="completed", metrics=dict(apogee_m=10))
    write_json(folder / "result.json", result)
    write_json(folder / "manifest.json", {"result.json": sha(folder / "result.json")})
    row = dict(
        result, evidence=dict(directory="s00", manifest_sha256=sha(folder / "manifest.json"))
    )
    report = dict(source_unchanged=True, results=[row])
    write_json(tmp_path / "report.json", report)
    assert verified(tmp_path)[1] == 1
    row["metrics"] = dict(apogee_m=20)
    write_json(tmp_path / "report.json", report)
    with pytest.raises(ValueError, match="Summary differs"):
        verified(tmp_path)
    write_json(folder / "result.json", {})
    with pytest.raises(ValueError, match="Changed case artifact"):
        verified(tmp_path)
