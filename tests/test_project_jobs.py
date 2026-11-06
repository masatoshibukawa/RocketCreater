import json
import subprocess
import sys

import pytest

from rocketwright.agent.design_projects import DesignProjects
from rocketwright.agent.project_jobs import file_lock, progress
from rocketwright.agent.workbench import Conflict
from scripts.render_checkpoint import Checkpoint
from tests.test_project_equipment import spec


def test_cfd_progress_counts_completed_cases_and_keeps_queue_eta_unknown(tmp_path):
    store = DesignProjects(tmp_path)
    state = store.create(spec())
    folder = store.base(state["id"]) / "v1/adaptive/trial/tunnel"
    folder.mkdir(parents=True)
    (folder / "table-config.json").write_text(
        json.dumps(dict(speeds_mps=[1, 35], angles_deg=[0, 5]))
    )
    active = dict(
        analysis_folder="v1/adaptive/trial",
        analysis_name="cfd_fine",
        phase="waiting_renderer",
        analysis_started_at=0,
    )
    first = progress(store, state["id"], active)
    assert first["total"] == 4 and first["completed"] == 0 and first["eta_s"] is None
    (folder / "v01-a000").mkdir()
    (folder / "v01-a000/case.json").write_text("{}")
    active["phase"] = "running_renderer"
    result = progress(store, state["id"], active)
    assert result["completed"] == 1 and result["total"] == 4 and result["eta_s"][0] > 0


def test_os_lock_survives_store_restart_and_rejects_second_process(tmp_path):
    store = DesignProjects(tmp_path)
    state = store.create(spec())
    state["active"] = {"id": "abc", "name": "analyse", "owner": "other API", "started_at": 0}
    store._write(state)
    lock = store.base(state["id"]) / "operation.lock"
    with file_lock(lock):
        restarted = DesignProjects(tmp_path)
        assert restarted.get(state["id"])["active"]["id"] == "abc"
        command = [
            sys.executable,
            "-c",
            "from pathlib import Path;from rocketwright.agent.project_jobs import locked;"
            "import sys;sys.exit(0 if locked(Path(sys.argv[1])) else 1)",
            str(lock),
        ]
        assert subprocess.run(command, check=False).returncode == 0
        with pytest.raises(Conflict):
            restarted.edit(state["id"], state["revision"], spec())
    # An actually abandoned process releases the OS lock, then can be retried.
    result = DesignProjects(tmp_path).get(state["id"])
    assert result["active"] is None and result["error"]


def test_render_resume_rejects_changed_inputs_corrupt_frames_and_cancel(tmp_path):
    path = tmp_path / "design-frames/0000.png"
    path.parent.mkdir()
    path.write_bytes(b"rendered-frame-fixture")
    job = {"render_identity": "input-A", "job_id": "job-A", "plan": {"frames_per_clip": 2}}
    checkpoint = Checkpoint(tmp_path, job)
    assert not checkpoint.valid(path)
    checkpoint.finished(path, 2)
    resumed = Checkpoint(tmp_path, {**job, "job_id": "job-B"})
    assert resumed.valid(path)
    progress = json.loads((tmp_path / "progress.json").read_text())
    assert progress["job_id"] == "job-B" and progress["reused"] == 1
    assert not Checkpoint(tmp_path, {**job, "render_identity": "different"}).valid(path)
    path.write_bytes(b"incomplete")
    assert not resumed.valid(path)
    cancel = tmp_path / "cancel"
    cancel.touch()
    with pytest.raises(RuntimeError, match="cancelled"):
        Checkpoint(tmp_path, {**job, "cancel_file": str(cancel)}).valid(path)
