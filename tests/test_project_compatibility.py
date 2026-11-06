import copy
import json

import pytest

from rocketwright.agent.design_projects import DesignSpec
from tests.test_design_projects import adopted, spec
from tests.test_design_projects import store as project_store

store = project_store


def test_legacy_rail_is_moved_without_mutating_saved_input():
    old = spec().model_dump(mode="json")
    old["assumptions"]["rail_m"] = 2.25
    del old["env"]["rail_length_m"]
    original = copy.deepcopy(old)
    current = DesignSpec.model_validate(old)
    assert current.env.rail_length_m == 2.25
    assert "rail_m" not in current.assumptions.model_dump()
    assert old == original
    old["env"]["rail_length_m"] = 1.5
    with pytest.raises(ValueError, match="ガイド長"):
        DesignSpec.model_validate(old)


def test_old_record_is_readable_editable_and_does_not_reuse_old_pass(store):
    state = adopted(store)
    state["spec"]["assumptions"]["rail_m"] = state["spec"]["env"]["rail_length_m"]
    state["analysis"]["implementation_sha256"] = "older-implementation"
    store._write(state)
    path = store.base(state["id"]) / "state.json"
    original = path.read_bytes()
    viewed = store.get(state["id"])
    assert viewed["analysis_stale"] and viewed["input_migration"]
    assert path.read_bytes() == original
    old_file = store.file(state["id"], "production/report.json").read_bytes()
    edited = store.edit(state["id"], state["revision"], DesignSpec.model_validate(viewed["spec"]))
    assert edited["version"] == 2 and not edited["adopted"] and not edited["analysis"]
    assert "rail_m" not in edited["spec"]["assumptions"]
    snapshot = json.loads(
        (store.base(state["id"]) / "v1/snapshot.json").read_text(encoding="utf-8")
    )
    assert snapshot["spec"] == state["spec"]
    assert store.file(state["id"], "production/report.json", 1).read_bytes() == old_file
