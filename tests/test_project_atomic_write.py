import json
from pathlib import Path

import pytest

from rocketwright.agent import design_projects as module


def test_atomic_json_publish_retries_reader_sharing_conflict(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    target.write_text('{"version":1}', encoding="utf-8")
    original = Path.replace
    calls = []

    def sharing_conflict(source, destination):
        calls.append(source)
        assert json.loads(target.read_text()) == {"version": 1}
        if len(calls) < 3:
            raise PermissionError("reader temporarily disallows replacement")
        return original(source, destination)

    monkeypatch.setattr(Path, "replace", sharing_conflict)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    module.write_json(target, {"version": 2, "日本語": "保存"})
    assert len(calls) == 3
    assert json.loads(target.read_text(encoding="utf-8")) == {"version": 2, "日本語": "保存"}


def test_permanent_publish_failure_is_bounded_and_preserves_previous_json(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    target.write_text('{"version":1}', encoding="utf-8")
    calls = []

    def denied(source, destination):
        calls.append(source)
        raise PermissionError("permanently denied")

    monkeypatch.setattr(Path, "replace", denied)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    with pytest.raises(PermissionError, match="permanently"):
        module.write_json(target, {"version": 2})
    assert 1 < len(calls) <= 10
    assert json.loads(target.read_text()) == {"version": 1}
