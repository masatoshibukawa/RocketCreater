"""Tests for what the user stated that the code keeps, whatever the model does (no network)."""

import pytest

from rocketwright.agent.constraints import UserConstraints, constrain, read_constraints

BOTTLE_15 = "pet_bottle_1p5l"


@pytest.mark.parametrize(
    ("text", "bottle"),
    [
        ("卵を割らずに 20 m まで上げて回収したい。1.5 L のボトルで、予算は 3000 円", BOTTLE_15),
        ("1.5L ペットボトルで 20 m", BOTTLE_15),
        ("ボトルは 500 mL にしたい", "pet_bottle_500ml"),
        ("２Ｌのペットボトルで飛ばしたい", "pet_bottle_2l"),
        ("a 1 L bottle to 15 m", "pet_bottle_1l"),
        ("1500 ml のボトル", BOTTLE_15),
    ],
)
def test_a_stated_bottle_size_is_read(text, bottle):
    assert read_constraints(text).bottle_id == bottle


@pytest.mark.parametrize(
    "text",
    [
        "卵を割らずに 30 m まで上げて回収したい",
        "水 1 L を入れて、ボトルで 20 m",
        "1.5 L か 2 L のボトルで",
        "3 L のボトルで",  # no such bottle in the catalog: the model is told, not held to it
    ],
)
def test_no_size_or_an_unclear_one_holds_nothing(text):
    assert read_constraints(text).bottle_id is None


HELD = UserConstraints(bottle_id=BOTTLE_15, said="1.5 L")


def test_auto_design_starts_from_the_stated_bottle():
    inp = {"tier": "bottle", "requirement": {}}

    out, refusal = constrain("auto_design", inp, HELD)

    assert refusal is None
    assert out["fixed"] == {"bottle": BOTTLE_15}
    assert "fixed" not in inp


def test_design_stage_keeps_the_stated_bottle_upstream():
    inp = {"stage": "nozzle", "chosen": [{"stage": "bottle", "value": "pet_bottle_500ml"}]}

    out, refusal = constrain("design_stage", inp, HELD)

    assert refusal is None
    assert out["chosen"] == [{"stage": "bottle", "value": BOTTLE_15}]


def test_design_stage_on_the_bottle_itself_offers_only_the_stated_bottle():
    out, refusal = constrain("design_stage", {"stage": "bottle", "chosen": []}, HELD)

    assert refusal is None
    assert out["only_option"] == BOTTLE_15


def test_a_build_or_design_with_another_bottle_is_refused():
    build = {"build": {"tier": "bottle", "bottle_id": "pet_bottle_500ml"}}
    design = {"design": {"tier": "bottle", "bottle_volume_m3": 0.0005}}

    assert constrain("design_from_parts", build, HELD)[1]
    assert constrain("simulate_design", design, HELD)[1]
    assert constrain("run_dispersion", design, HELD)[1]


def test_the_stated_bottle_passes():
    build = {"build": {"tier": "bottle", "bottle_id": BOTTLE_15}}
    design = {"design": {"tier": "bottle", "bottle_volume_m3": 0.0015}}

    assert constrain("design_from_parts", build, HELD) == (build, None)
    assert constrain("simulate_design", design, HELD) == (design, None)


def test_nothing_stated_changes_nothing():
    inp = {"tier": "bottle"}

    assert constrain("auto_design", inp, UserConstraints()) == (inp, None)
