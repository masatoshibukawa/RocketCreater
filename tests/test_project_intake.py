from types import SimpleNamespace

import pytest

from rocketwright.agent.design_projects import DesignProjects
from rocketwright.agent.project_intake import accept, grounded_fields, propose
from rocketwright.agent.workbench import Conflict


class Director:
    api = SimpleNamespace(timeout=0)

    def __init__(self, **fields):
        self.fields = dict(name="日本語の試作案", reason="依頼の数値を整理", **fields)

    def generate(self, *args):
        return self.fields, "fixture-local-model"


def test_missing_facts_ask_questions_without_creating_fictional_project(tmp_path):
    store = DesignProjects(tmp_path)
    p = propose(store, "ロケットを作りたい", director=Director())
    assert len(p["questions"]) == 3 and not p["candidates"] and not store.list()
    with pytest.raises(ValueError):
        propose(store, "invalid", director=Director(payload_g=float("nan")))


def test_confirmed_local_candidate_and_midstream_change_keep_requirements(tmp_path):
    store = DesignProjects(tmp_path)
    p = propose(
        store,
        "1.5 L、80 g、15 m以上、回収",
        director=Director(
            target_altitude_m=15,
            payload_g=80,
            bottle_l=1.5,
            recovery_required=True,
            altitude_rule="minimum",
        ),
    )
    s = accept(store, p["id"], "base")
    assert s["spec"]["requirement"]["payload_mass_kg"] == 0.08
    assert s["spec"]["altitude_rule"] == "minimum"
    q = propose(store, "搭載物を100 gへ", s["id"], director=Director(payload_g=100))
    t = accept(store, q["id"], "base")
    assert t["version"] == 2 and t["spec"]["design"]["payload_mass_kg"] == 0.1
    assert t["spec"]["requirement"]["target_altitude_m"] == 15
    assert t["spec"]["altitude_rule"] == "minimum"
    assert len(t["intake"]) == 2
    with pytest.raises(Conflict):
        accept(store, q["id"], "base")
    with pytest.raises(KeyError):
        accept(store, p["id"], "shell")


def test_unmentioned_numbers_cannot_change_previous_requirements():
    fields = grounded_fields(
        dict(
            target_altitude_m=20,
            payload_g=100,
            pressure_kpa=300,
            recovery_required=True,
            altitude_rule="band_10pct",
        ),
        "搭載物を100 gに変更。他は同じ。",
    )
    assert fields["payload_g"] == 100
    assert fields["target_altitude_m"] is None and fields["pressure_kpa"] is None
    assert fields["recovery_required"] is None and fields["altitude_rule"] is None
    assert grounded_fields({"budget_jpy": 5000}, "予算5,000円")["budget_jpy"] == 5000
