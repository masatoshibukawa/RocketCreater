import pytest

from rocketwright.agent.design_projects import sha, write_json
from scripts.report_local_learning_stages import portable, verified_tree


def test_nested_stage_manifests_are_verified_and_tampering_rejected(tmp_path):
    for stage in ("stage5", "stage6", "stage7/branch-case"):
        folder = tmp_path / stage / "projects" / "example"
        folder.mkdir(parents=True)
        write_json(folder / "case.json", {"native": True})
        write_json(folder / "manifest.json", {"case.json": sha(folder / "case.json")})
    assert verified_tree(tmp_path) == {"manifests": 3, "unique_files": 3, "gpu_cases": 3}
    write_json(folder / "case.json", {"native": False})
    with pytest.raises(ValueError, match="Changed native evidence"):
        verified_tree(tmp_path)


def test_public_report_removes_windows_host_paths_and_keeps_identifiers():
    result = portable({"rows": [{"artifact": "C:\\private\\data.json", "sha256": "abc"}]})
    assert result == {"rows": [{"artifact": "local-evidence/data.json", "sha256": "abc"}]}
