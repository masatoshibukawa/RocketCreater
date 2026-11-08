import json

from rocketwright.agent.design_projects import write_json
from rocketwright.analysis.worker import Worker, serial
from tests.test_analysis_record import VOLUMES, spec


def test_real_cpu_analysis_chain_transfers_state_and_rejects_unmet_goal(tmp_path):
    s = spec()
    s.assumptions.gust_mps = 0
    s.assumptions.warm_wait_s = 10
    artifacts = {}
    geo = tmp_path / "geometry.json"
    write_json(geo, {"cad_metrics": VOLUMES})
    artifacts["geometry"] = str(geo)
    for kind in (
        "benchmarks",
        "thermal",
        "propulsion",
        "screen",
        "refine",
        "modes",
        "stability",
        "confirm",
    ):
        folder = tmp_path / kind
        folder.mkdir()
        context = dict(
            spec=s.model_dump(mode="json"),
            precision={"require_cfd": False, "require_fem": False},
            artifacts=artifacts,
            runtime={},
            timeout_s=120,
        )
        result = serial(Worker(context, folder).run(kind))
        path = folder / "result.json"
        write_json(path, result)
        artifacts[kind] = str(path)
    final = json.loads(path.read_text())
    assert not final["physical_qualification"]
    assert final["metrics"]["criteria_met"] == all(final["checks"].values())
    assert final["flight"]["completed"]
    assert final["flight"]["quaternion_norm_error"] < 1e-5
    assert final["flight"]["max_section_equilibrium_residual"] < 1e-6
    stability = json.loads((tmp_path / "stability/result.json").read_text())
    assert not stability["full_flight_stability_proved"]
    assert not stability["barbalat"]["W_to_zero_proved"]


def test_static_margin_applies_to_unconstrained_ascent_and_missing_interval_stays_unknown():
    from rocketwright.analysis.worker import free_ascent_margin

    t = dict(
        rail_exit_s=1,
        apogee_s=3,
        trace=dict(
            time_s=[0, 1, 2, 3, 4], q_pa=[0, 5, 100, 50, 20], cg_m=[0.4, 0.3, 0.17, 0.15, 0.4]
        ),
    )
    assert abs(free_ascent_margin(t, 0.3, 0.1) - 1.3) < 1e-12
    t["rail_exit_s"] = 3
    assert free_ascent_margin(t, 0.3, 0.1) is None
