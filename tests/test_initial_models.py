import threading

import pytest

from rocketwright.analysis import seed_survey, seeds
from rocketwright.analysis.schema import Precision
from tests.test_analysis_record import spec


def test_controlled_comparison_deduplicates_labels_and_preserves_mission():
    s = spec()
    s.measured_printed_mass_g = 24
    candidates, aliases = seed_survey.comparable_starts(s)
    assert len(candidates) == 8 and len(aliases) == 3
    assert len({c.geometry.model_dump_json() for c in candidates.values()}) == 8
    for c in candidates.values():
        assert c.requirement == s.requirement and c.env == s.env
        assert c.measured_printed_mass_g is None
        assert c.design.geometry.model_dump() == c.geometry.model_dump()
        assert all(getattr(c.design, k) == getattr(s.design, k) for k in seed_survey.CONTROLLED)
    assert s.measured_printed_mass_g == 24
    assert {c.geometry.fin_count for c in candidates.values()} == {3, 4, 5}
    assert {c.design.bottle_volume_m3 for c in candidates.values()} == {0.0005, 0.0015, 0.002}


def test_reference_conversions_do_not_claim_exact_replication():
    c = seeds.catalog()
    assert len(c["models"]) == 6 and len(c["sources"]) == 3
    for row in c["models"]:
        assert row["assumptions"] and row["conversion"] and row["documented"]
        assert not row["geometry"]["dimensions_measured"]
        assert all(len(f["sha256"]) == 64 for f in c["sources"][row["family"]]["files"])
    broad = next(x for x in c["models"] if x["id"] == "reference/D09-broad3")
    assert broad["geometry"]["fin_root_mm"] == pytest.approx(60 - 30 * 46 / 90)
    narrow = next(x for x in c["models"] if x["id"] == "reference/D09-narrow5")
    assert narrow["chord_scale"] > 1 and narrow["cfd_blocker"]
    assert narrow["geometry"]["fin_root_mm"] == pytest.approx(35)


def test_parallel_dispatch_is_bounded_and_keeps_failure_and_budget(tmp_path, monkeypatch):
    choices = {f"candidate-{i}": spec() for i in range(4)}
    monkeypatch.setattr(seed_survey, "comparable_starts", lambda s: (choices, {}))
    monkeypatch.setattr(seed_survey, "code_hash", lambda: "frozen")
    barrier = threading.Barrier(2)
    shares, active, maximum = [], 0, 0
    lock = threading.Lock()

    def worker(job):
        nonlocal active, maximum
        label, s, folder, source, precision, share, deadline = job
        with lock:
            active += 1
            maximum = max(active, maximum)
            shares.append(share)
        barrier.wait(timeout=5)
        with lock:
            active -= 1
        if label == "candidate-1":
            return dict(label=label, status="failed", elapsed_s=1, error="solver failure")
        return dict(
            label=label,
            status="completed",
            elapsed_s=1,
            spec=s.model_dump(),
            aero_domain_pass=True,
            temporal_pass=True,
            detailed_cfd_available=True,
            metrics=dict(apogee_m=20, static_margin_cal=1, incidence_deg=2),
        )

    monkeypatch.setattr(seed_survey, "_case", worker)
    r = seed_survey.run(spec(), tmp_path / "parallel", workers=2, budget_s=120, emit=lambda r: None)
    assert maximum == 2 and sum(shares) == 120
    assert [x["label"] for x in r["results"]] == list(choices)
    assert r["results"][1]["status"] == "failed"
    assert r["selected"] == "candidate-0"
    assert r["charged_case_s"] == 4
    assert not r["acceptance_performed"] and r["precision"] == Precision().model_dump()


def test_source_change_excludes_all_results_from_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(seed_survey, "comparable_starts", lambda s: ({"one": s}, {}))
    source = iter(["before", "after"])
    monkeypatch.setattr(seed_survey, "code_hash", lambda: next(source))
    monkeypatch.setattr(
        seed_survey,
        "_case",
        lambda job: dict(
            label="one", status="completed", elapsed_s=1, aero_domain_pass=True, temporal_pass=True
        ),
    )
    r = seed_survey.run(spec(), tmp_path / "changed", emit=lambda r: None)
    assert not r["source_unchanged"] and not r["ranked_ids"]
    assert not (tmp_path / "changed/selected.json").exists()


def test_failed_precision_or_domain_never_becomes_selected(tmp_path, monkeypatch):
    monkeypatch.setattr(seed_survey, "comparable_starts", lambda s: ({"one": s}, {}))
    monkeypatch.setattr(seed_survey, "code_hash", lambda: "unchanged")
    monkeypatch.setattr(
        seed_survey,
        "_case",
        lambda job: dict(
            label="one", status="completed", elapsed_s=1, aero_domain_pass=False, temporal_pass=True
        ),
    )
    r = seed_survey.run(spec(), tmp_path / "domain", emit=lambda r: None)
    assert r["selected"] is None and len(r["results"]) == 1
