import copy

import pytest

from rocketwright.agent.design_projects import DesignProjects
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.schema import Precision, SearchLimits
from scripts.verify_adaptive_scenarios import isolated_spec, theorem_checks
from tests.test_analysis_harness import FixtureHarness
from tests.test_analysis_record import spec


def test_benchmark_geometry_changes_keep_the_input_design_immutable():
    original = spec()
    original.measured_printed_mass_g = 40
    before = original.model_dump()
    changed = isolated_spec(original, 3.6)
    assert original.model_dump() == before
    assert changed.geometry.fin_thickness_mm == 3.6
    assert changed.measured_printed_mass_g is None
    assert changed.design == original.design


@pytest.mark.parametrize("change", ["material", "mount"])
def test_completed_strength_modes_and_stability_are_invalidated_together(tmp_path, change):
    # These artifact fixtures test cache contracts only; native evidence is in stage 7's report.
    executable = tmp_path / "solver-fixture"
    executable.write_text("fixture; never executed")
    store = DesignProjects(tmp_path / "projects")
    state = store.create(spec())
    h = FixtureHarness(store, runtime=Runtime(calculix=str(executable)))
    h.confirmation = True
    state = h.start(
        state["id"],
        state["revision"],
        Precision(require_cfd=False),
        SearchLimits(planner="baseline", max_versions=1),
    )
    state = h.run(state["id"], state["revision"])
    before, _, _, _ = h._campaign(state)
    targets = ("fem_coarse", "fem_fine", "modes", "stability", "confirm")
    assert all(before.current(k) for k in targets)
    changed = copy.deepcopy(state)
    if change == "material":
        changed["spec"]["material"] = "Prusament PETG"
    else:
        changed["spec"]["assumptions"]["mount"] = "reinforced"
    after, _, _, _ = h._campaign(changed)
    assert after.current("geometry")
    assert not any(after.current(k) for k in targets)


def test_theorem_selection_keeps_forced_and_scheduled_models_out_of_lasalle(tmp_path):
    result = theorem_checks(tmp_path, "baseline")
    assert result["passed"]
    assert not result["full_flight_stability_proved"]
    forced = result["cases"]["forced_frozen"]
    assert not forced["next_choices"]["offered"]
    assert "frozen-origin" not in forced["results"]
    assert "finite-error-bound" in result["cases"]["scheduled"]["results"]
