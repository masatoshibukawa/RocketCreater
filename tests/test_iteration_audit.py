from pathlib import Path

import pytest

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis import experience, policy
from rocketwright.analysis.schema import Precision
from scripts.audit_iteration_learning import audit
from tests.test_analysis_record import spec


def dataset(root):
    s = spec()
    change = dict(section="geometry", field="fin_thickness_mm", value=3.6)
    p = Precision().model_dump()
    rows = []
    for seed, delta in (("A", 1), ("A", -100), ("B", 2)):
        folder = root / "projects" / str(len(rows))
        artifact = folder / "data.json"
        write_json(artifact, dict(apogee_m=delta))
        write_json(folder / "manifest.json", {"data.json": sha(artifact)})
        outcome = dict(
            code="solver",
            precision_hash=digest(p),
            status="measured",
            from_spec_hash=policy.identity(s),
            signature=experience.signature(change, s),
            features=experience.features(s),
            delta=dict(apogee_m=delta),
            cost_s=20,
            evidence_id=sha(artifact),
            evidence=dict(
                artifact=str(artifact),
                sha256=sha(artifact),
                manifest_sha256=sha(folder / "manifest.json"),
            ),
        )
        rows.append(
            dict(
                seed=seed,
                project_id=seed,
                fit_eligible=True,
                outcome=outcome,
                selected="change",
                input=dict(
                    context=dict(precision=p),
                    choices=dict(change=dict(target=change, prediction=dict(delta_height_m=3))),
                ),
            )
        )
    write_json(root / "learning.json", rows)
    write_json(
        root / "report.json", dict(source_hash="solver", observations=[dict(spec=s.model_dump())])
    )


def test_prediction_audit_excludes_every_revision_from_held_out_seed(tmp_path):
    dataset(tmp_path)
    result = audit(tmp_path)
    held_out = [r for r in result["rows"] if r["seed"] == "A"]
    assert len(held_out) == 2
    # The other A revision (-100 m) must not influence either held-out A prediction.
    assert all(r["matched_samples"] == 1 for r in held_out)
    assert all(r["history_adjusted_prediction_m"] == 2.75 for r in held_out)
    assert not result["general_efficiency_improvement_proved"]


def test_prediction_audit_rejects_tampered_solver_evidence(tmp_path):
    dataset(tmp_path)
    Path(tmp_path / "projects/0/data.json").write_text("{}")
    with pytest.raises(ValueError, match="Invalid evidence"):
        audit(tmp_path)
