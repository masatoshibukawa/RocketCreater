"""Local detached production workers and OS-backed locks, without a cloud queue."""

import contextlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from rocketwright.agent.local_runtime import LocalRuntimeError
from rocketwright.agent.workbench import Conflict


@contextlib.contextmanager
def file_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as file:
        if file.seek(0, 2) == 0:
            file.write(b"0")
            file.flush()
        file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise Conflict("同じ案件または機材を別の作業プロセスが使用中です。") from exc
        try:
            yield
        finally:
            file.seek(0)
            if os.name == "nt":
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def locked(path):
    try:
        with file_lock(path):
            return False
    except Conflict:
        return True


def cancel_path(store, project_id, job_id):
    return store.base(project_id) / "jobs" / (job_id + ".cancel")


def progress(store, project_id, active):
    if active.get("analysis_folder"):
        base = store.base(project_id).resolve()
        folder = (base / active["analysis_folder"]).resolve()
        if folder.is_relative_to(base) and not folder.is_symlink():
            phase = active.get("phase", "running")
            name = active.get("analysis_name", "analysis")
            elapsed = max(0, time.time() - active.get("analysis_started_at", time.time()))
            total = None
            if name.startswith("cfd"):
                folder = folder / "tunnel" if name != "cfd_audit" else folder
                try:
                    config = json.loads((folder / "table-config.json").read_text(encoding="utf-8"))
                    total = len(config["speeds_mps"]) * len(config["angles_deg"])
                except (OSError, ValueError, KeyError):
                    total = 6 if name == "cfd_audit" else None
            completed = sum(p.is_file() and not p.is_symlink() for p in folder.glob("*/case.json"))
            remaining = elapsed / completed * (total - completed) if total and completed else None
            return dict(
                phase=phase if phase.startswith("waiting_") else name,
                completed=completed,
                total=total,
                elapsed_s=elapsed,
                eta_s=[max(0, remaining * 0.7), max(0, remaining * 1.6)]
                if remaining is not None and not phase.startswith("waiting_")
                else None,
            )
    directory = store.directory(project_id)
    style = active.get("style", "engineering")
    directory /= active.get("video_directory") or (
        "video-photographic" if style == "photographic" else "video"
    )
    path = directory / "progress.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("job_id") == active.get("id"):
            return value
    except (OSError, ValueError):
        pass
    return dict(
        phase=active.get("phase", "running"),
        completed=0,
        total=None,
        elapsed_s=max(0, time.time() - active["started_at"]),
        eta_s=None,
    )


def queue(
    store,
    project_id,
    revision,
    operation,
    style="engineering",
    *,
    regenerate=False,
    quality="final",
):
    from rocketwright.agent.design_projects import ROOT, implementation_fingerprint
    from rocketwright.manufacturing import fingerprint

    if operation not in {
        "analyse",
        "print_package",
        "render_video",
        "adaptive_step",
        "adaptive_run",
    }:
        raise ValueError("Unknown production operation")
    if style not in {"engineering", "photographic"}:
        raise ValueError("Unknown render style")
    if regenerate and operation != "render_video":
        raise ValueError("Only video production can be regenerated")
    if quality not in {"preview", "final"} or (
        quality == "preview" and (operation != "render_video" or style != "photographic")
    ):
        raise ValueError("Lightweight previews require photographic video production")
    store.get(project_id)  # Reconcile an abandoned checkpoint before claiming it.
    with file_lock(store.base(project_id) / "operation.lock"):
        state = store.load(project_id)
        if state["revision"] != revision or state["active"]:
            raise Conflict("この版には処理があるか、版が変わりました。状態を読み直してください。")
        job_id = uuid.uuid4().hex
        state["active"] = dict(
            id=job_id,
            name=operation,
            style=style,
            regenerate=regenerate,
            quality=quality,
            phase="queued",
            started_at=time.time(),
            owner="detached",
            input_sha256=fingerprint(state["spec"]),
            implementation_sha256=implementation_fingerprint(),
        )
        state["error"] = None
        store._write(state)
        directory = store.base(project_id) / "jobs"
        directory.mkdir(exist_ok=True)
        env = os.environ.copy()
        env["ROCKETWRIGHT_JOB_ID"] = job_id
        env["PYTHONUTF8"] = "1"
        command = [
            sys.executable,
            "-m",
            "rocketwright.agent.project_jobs",
            str(store.root.resolve()),
            project_id,
            str(revision),
            operation,
            style,
            job_id,
        ]
        try:
            with (directory / (job_id + ".log")).open("w", encoding="utf-8") as log:
                child = subprocess.Popen(
                    command,
                    cwd=ROOT,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
                    )
                    if os.name == "nt"
                    else 0,
                    start_new_session=os.name != "nt",
                )
            state["active"]["pid"] = child.pid
            store._write(state)
        except OSError as exc:
            state.update(active=None, error="作業プロセスを開始できません。", revision=revision + 1)
            store._write(state)
            raise LocalRuntimeError(state["error"]) from exc
    return store.get(project_id)


def resource(store, state, name):
    """Wait for a shared local resource while retaining the per-project OS lock."""
    while True:
        if cancelled(store, state):
            raise LocalRuntimeError(
                "このジョブは中断されました。保存したフレームから再試行できます。"
            )
        try:
            lock = file_lock(store.root / "resources" / (name + ".lock"))
            lock.__enter__()
            return lock
        except Conflict:
            state["active"]["phase"] = "waiting_" + name
            store._write(state)
            time.sleep(0.25)


def cancelled(store, state):
    job_id = state.get("active", {}).get("id")
    return bool(job_id and cancel_path(store, state["id"], job_id).exists())


@contextlib.contextmanager
def resource_lease(store, state, name):
    lease = resource(store, state, name)
    try:
        state["active"]["phase"] = "running_" + name
        store._write(state)
        yield
        if cancelled(store, state):
            raise LocalRuntimeError("ジョブを中断しました。保存した入力から再試行できます。")
    finally:
        lease.__exit__(None, None, None)


def main():
    from rocketwright.agent.design_projects import DesignProjects, implementation_fingerprint
    from rocketwright.agent.production import render_video
    from rocketwright.manufacturing import fingerprint

    root, project_id, revision, operation, style, job_id = sys.argv[1:]
    store = DesignProjects(Path(root))
    state = store.load(project_id)
    active = state.get("active") or {}
    try:
        if (
            active.get("id") != job_id
            or active.get("input_sha256") != fingerprint(state["spec"])
            or active.get("implementation_sha256") != implementation_fingerprint()
        ):
            raise Conflict("Queued input or implementation changed")
        if operation == "render_video":
            render_video(
                store,
                project_id,
                int(revision),
                style,
                regenerate=bool(active.get("regenerate")),
                quality=active.get("quality", "final"),
            )
        else:
            completed = getattr(store, operation)(project_id, int(revision))
            if operation == "analyse" and completed.get("airframe_template"):
                from rocketwright.agent.airframe_parts import publish_parts

                try:
                    publish_parts(store, completed)
                except (OSError, ValueError) as exc:
                    print("Optional airframe cache publication failed; analysis retained:", exc)
    except Exception as exc:
        with file_lock(store.base(project_id) / "operation.lock"):
            state = store.load(project_id)
            if (state.get("active") or {}).get("id") == job_id:
                state.update(active=None, error=str(exc), revision=state["revision"] + 1)
                store._write(state)
        raise


if __name__ == "__main__":
    main()
