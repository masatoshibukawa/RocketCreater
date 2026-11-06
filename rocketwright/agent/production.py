"""Fixed render recipes, typed local direction and a pinned ComfyUI handoff."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field

from rocketwright.agent.local_runtime import LocalDirector, LocalJSON, LocalRuntimeError
from rocketwright.agent.project_jobs import cancel_path, cancelled, resource
from rocketwright.agent.video_appearance import freeze_assets, plan_key, recipe
from rocketwright.agent.video_cache import digest
from rocketwright.agent.workbench import ROOT, SKILLS, Conflict


class Direction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    design_focus: Literal["payload_and_recovery", "fins_and_stability", "assembly_dimensions"]
    launch_focus: Literal["trajectory_replay", "ascent_and_recovery"]
    camera: Literal["orbit", "slow_orbit"]
    launch_motion: Literal["tracking_ascent", "stationary_inspection"]
    reason: str = Field(min_length=1, max_length=500)


def bind_direction(direction: Direction) -> dict:
    """Bind a model's finite choices to factual copy and a non-combustion scene recipe."""
    captions = {
        "payload_and_recovery": "搭載室と回収装置の配置を確認する",
        "fins_and_stability": "フィンの配置と機体の構成を確認する",
        "assembly_dimensions": "機体の配置と寸法を確認する",
        "trajectory_replay": "計算した飛行軌跡を再生する",
        "ascent_and_recovery": "上昇と降下の計算結果を確認する",
    }
    motion = {
        "tracking_ascent": "The water rocket lifts vertically with a brief water spray, "
        "then coasts smoothly. The camera tracks its ascent.",
        "stationary_inspection": "The water rocket remains stationary while the camera "
        "makes a slow lateral inspection move.",
    }
    return direction.model_dump() | {
        "design_caption": captions[direction.design_focus],
        "launch_caption": captions[direction.launch_focus],
        "launch_prompt": "A PET bottle water rocket with rigid fins on an outdoor field. "
        + motion[direction.launch_motion]
        + " Natural daylight, stable geometry, unchanged proportions, realistic materials. "
        "Preserve the reference assembly. A single continuous shot.",
    }


def validate_bound_direction(plan: dict) -> None:
    direction = Direction.model_validate({key: plan.get(key) for key in Direction.model_fields})
    expected = bind_direction(direction)
    if any(
        plan.get(key) != expected[key]
        for key in ("design_caption", "launch_caption", "launch_prompt")
    ):
        raise Conflict("Video direction changed. Review a new plan before continuing.")


def media_settings():
    media_root = Path(os.getenv("ROCKETWRIGHT_MEDIA_ROOT", ROOT / "AIvideo"))
    return {
        "blender": Path(
            os.getenv(
                "ROCKETWRIGHT_BLENDER",
                "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe",
            )
        ),
        "python": Path(os.getenv("ROCKETWRIGHT_VIDEO_PYTHON", sys.executable)),
        "libs": media_root / "Test project/tools/python",
    }


def plan_video(bench, project_id, revision, local=True, director=None, style="engineering"):
    key = plan_key(style)
    kind = "photographic_video" if style == "photographic" else "video"

    def worker(state):
        if not any(f["kind"] == "production" for f in state["files"]):
            raise Conflict("Export the confirmed design before planning its videos")
        if any(f["kind"] == kind for f in state["files"]):
            raise Conflict("Videos already exist. Keep their approved direction unchanged.")
        report = json.loads(
            bench.file(project_id, "production/report.json").read_text(encoding="utf-8")
        )
        assembly = json.loads(
            bench.file(project_id, "production/assembly.json").read_text(encoding="utf-8")
        )
        if local:
            skills = [
                {"path": p, "instructions": (ROOT / p).read_text(encoding="utf-8")}
                for p in SKILLS["video"]
            ]
            context = {
                "design": report["design"],
                "dimensions_mm": assembly["dimensions_mm"],
                "evidence": state["history"][-2:],
                "skills": skills,
                "output": "separate design explanation and simulated launch CG",
                "rocket_type": "PET bottle water rocket, no combustion",
            }
            data, model = (director or LocalDirector()).generate(
                context,
                Direction.model_json_schema(),
                "Select the registered focus, camera and motion IDs for this water rocket. "
                "Explain your selection briefly in Japanese. Scripts own all captions, "
                "measurements, physics and image prompts. Do not invent performance or "
                "request any new capabilities. Return only the requested JSON.",
            )
            direction = Direction.model_validate(data)
        else:
            model = "deterministic_recipe"
            direction = Direction(
                design_focus="payload_and_recovery",
                launch_focus="trajectory_replay",
                camera="slow_orbit",
                launch_motion="tracking_ascent",
                reason="採用案の構成と計算した軌跡を順に確認する。",
            )
        state[key] = (
            bind_direction(direction)
            | recipe(style)
            | {
                "model": model,
                "skills": SKILLS["video"],
                "audio": "none",
                "design_source": report["sim_source_id"],
                "status": "planned",
                "wan_status": "not_submitted",
            }
        )

    return bench._run(project_id, revision, "video_direction", worker)


def render_video(
    bench,
    project_id,
    revision,
    style="engineering",
    *,
    started=None,
    regenerate=False,
    quality="final",
):
    key = plan_key(style)
    execution_recipe = recipe(style, quality)
    kind = "photographic_video" if style == "photographic" else "video"
    if quality == "preview":
        kind = "photographic_preview"

    def worker(state):
        settings = media_settings()
        if not settings["blender"].is_file() or not settings["python"].is_file():
            raise LocalRuntimeError("Configure the installed Blender and video Python executables")
        approved_plan = state.get(key, {})
        if approved_plan.get("status") != "planned" and not (
            (regenerate or quality == "preview") and approved_plan.get("status") == "rendered"
        ):
            raise Conflict("Approve a shot plan before rendering")
        validate_bound_direction(approved_plan)
        expected_recipe = recipe(style)
        if any(approved_plan.get(k, v) != v for k, v in expected_recipe.items()):
            raise Conflict("Render settings changed; review a new plan")
        plan = dict(approved_plan) | execution_recipe | {"quality": quality}
        existing = any(f["kind"] == kind for f in state["files"])
        if existing and not regenerate:
            raise Conflict("Videos already exist for this design")
        base_name = "video-photographic" if style == "photographic" else "video"
        if quality == "preview":
            base_name += "-preview"
        pending_key = "pending_preview_directory" if quality == "preview" else "pending_directory"
        directory_name = base_name
        if existing:
            directory_name = approved_plan.get(pending_key) or base_name + "-" + uuid.uuid4().hex
            if not re.fullmatch(re.escape(base_name) + r"-[a-f0-9]{32}", directory_name):
                raise Conflict("Invalid pending video directory")
            approved_plan[pending_key] = directory_name
        directory = bench.directory(project_id) / directory_name
        state["active"].update(style=style, quality=quality, video_directory=directory_name)
        directory.mkdir(exist_ok=True)
        # Bind the same frozen production snapshot as the print exports.
        assembly = json.loads(
            bench.file(project_id, "production/assembly.json").read_text(encoding="utf-8")
        )
        report = json.loads(
            bench.file(project_id, "production/report.json").read_text(encoding="utf-8")
        )
        job = {
            "dimensions_mm": assembly["dimensions_mm"],
            "plan": plan,
            "design": report["design"],
            "source_id": report["sim_source_id"],
            "evidence": state["history"][-2:],
            "trace": json.loads(
                bench.file(project_id, "production/trace.json").read_text(encoding="utf-8")
            ),
        }
        if report["design"].get("geometry"):
            # Registered, hash-checked CAD paths only. Never a path chosen by the model.
            job["cad_files"] = {
                "nose": str(bench.file(project_id, "cad/nose-mm.stl").resolve()),
                "fin": str(bench.file(project_id, "cad/fin-assembly-mm.stl").resolve()),
            }
        if style == "photographic":
            job["appearance_sha256"] = digest(freeze_assets(directory))
        job["cache_directory"] = str(
            Path(os.getenv("ROCKETWRIGHT_RENDER_CACHE", ROOT / "output/render-cache")).resolve()
        )
        job["render_identity"] = hashlib.sha256(
            json.dumps(
                {
                    "job": job,
                    "code": {
                        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                        for name in [
                            "scripts/render_workbench_scene.py",
                            "scripts/render_checkpoint.py",
                            "scripts/compose_workbench_video.py",
                            "AIvideo/pet-rocket/realism/appearance.py",
                        ]
                    },
                    "cad": {
                        k: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                        for k, p in job.get("cad_files", {}).items()
                    },
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        if state.get("active", {}).get("id"):
            job["job_id"] = state["active"]["id"]
            job["cancel_file"] = str(cancel_path(bench, project_id, job["job_id"]).resolve())
        job_path = directory / "job.json"
        job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        commands = [
            [
                str(settings["blender"]),
                "--background",
                "--python-exit-code",
                "1",
                "--python",
                str(ROOT / "scripts/render_workbench_scene.py"),
                "--",
                str(job_path),
            ],
            [
                str(settings["python"]),
                str(ROOT / "scripts/compose_workbench_video.py"),
                str(job_path),
                "--libs",
                str(settings["libs"]),
            ],
        ]
        lease = resource(bench, state, "renderer")
        try:
            state["active"]["phase"] = "rendering"
            bench._write(state)
            with (directory / "render.log").open("w", encoding="utf-8") as log:
                for command in commands:
                    if cancelled(bench, state):
                        raise LocalRuntimeError(
                            "ジョブを中断しました。保存したフレームから再試行できます。"
                        )
                    try:
                        subprocess.run(
                            command,
                            cwd=ROOT,
                            env=env,
                            check=True,
                            timeout=3600 if style == "photographic" else 900,
                            stdout=log,
                            stderr=subprocess.STDOUT,
                            creationflags=flags,
                        )
                    except (OSError, subprocess.SubprocessError) as exc:
                        raise LocalRuntimeError(
                            "Video render failed or was cancelled; verified frames retained"
                        ) from exc
        finally:
            lease.__exit__(None, None, None)
        verification = json.loads((directory / "verification.json").read_text())
        if not verification["passed"]:
            raise LocalRuntimeError("Video verification did not pass")
        if "Traceback (most recent call last)" in (directory / "render.log").read_text(
            encoding="utf-8"
        ):
            raise LocalRuntimeError("Video render log contains an exception")
        if quality == "final":
            state[key]["status"] = "rendered"
            state[key]["output_directory"] = directory_name
        else:
            state[key]["preview_status"] = "rendered"
            state[key]["preview_directory"] = directory_name
        state[key].pop(pending_key, None)
        for row in state["files"]:
            if row["kind"] == kind:
                row["kind"] = kind + "_history"
        bench.register_files(state, directory, kind)
        # Logs and executable scene files are local implementation details.
        state["files"] = [f for f in state["files"] if f["name"] not in {"render.log", "job.json"}]

    return bench._run(
        project_id, revision, "render_design_and_launch", worker, started_event=started
    )


def queue_video(bench, project_id, revision, style="engineering"):
    """Acknowledge the persisted running checkpoint before a long local render."""
    recipe(style)
    state = bench.get(project_id)
    if state["revision"] != revision or state["active"]:
        raise Conflict("Project revision changed or another operation is running")
    started = threading.Event()
    errors = []

    def work():
        try:
            render_video(bench, project_id, revision, style, started=started)
        except Exception as exc:
            errors.append(exc)  # _run also persists tool failures for the browser poll.
        finally:
            started.set()  # Setup failures must also release the acknowledgement wait.

    threading.Thread(target=work, name="local-video-render", daemon=True).start()
    if not started.wait(timeout=5):
        raise LocalRuntimeError("Render startup did not acknowledge; reload its saved status")
    if errors:
        raise errors[0]
    return bench.get(project_id)


def comfy_client():
    return LocalJSON(os.getenv("ROCKETWRIGHT_COMFY_URL", "http://127.0.0.1:8188"))


def submit_wan(bench, project_id, revision):
    def worker(state):
        plan = state.get("video_plan", {})
        if plan.get("status") != "rendered" or plan.get("wan_status") != "not_submitted":
            raise Conflict("Render a reference first; do not submit duplicate video jobs")
        validate_bound_direction(plan)
        reference = bench.file(project_id, "video/launch-reference.png")
        client = comfy_client()
        boundary = uuid.uuid4().hex
        image_name = project_id + ".png"
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="image"; '
            f'filename="{image_name}"\r\nContent-Type: image/png\r\n\r\n'
        ).encode()
        body += reference.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        import urllib.request

        request = urllib.request.Request(
            client.address + "/upload/image",
            body,
            {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with client.opener.open(request, timeout=30) as response:
                upload = json.load(response)
        except OSError as exc:
            raise LocalRuntimeError("Could not upload the reference to local ComfyUI") from exc
        graph = copy.deepcopy(
            json.loads((ROOT / "AIvideo/local-runtime/workflow-api.json").read_text())
        )
        # Only fields of the repository's tested graph are writable. No model-generated nodes.
        graph["4"]["inputs"]["image"] = upload["name"]
        graph["5"]["inputs"]["text"] = plan["launch_prompt"]
        graph["6"]["inputs"]["text"] = "text, watermark, logos, geometry changes, flames, explosion"
        graph["7"]["inputs"].update(width=832, height=480, length=49)
        graph["9"]["inputs"].update(seed=20261104, steps=20)
        graph["12"]["inputs"]["filename_prefix"] = "rocketwright_" + project_id
        available = client.request("/object_info")
        if {n["class_type"] for n in graph.values()} - available.keys():
            raise LocalRuntimeError("Local ComfyUI is missing required Wan2.2 nodes")
        response = client.request("/prompt", {"prompt": graph, "client_id": project_id})
        prompt_id = response.get("prompt_id", "")
        if not re.fullmatch(r"[a-f0-9-]{36}", prompt_id):
            raise LocalRuntimeError("ComfyUI did not accept the workflow")
        plan.update(wan_status="queued", prompt_id=prompt_id)
        (bench.directory(project_id) / "video/wan-workflow.json").write_text(
            json.dumps(graph, indent=2)
        )

    return bench._run(project_id, revision, "submit_wan22", worker)


def collect_wan(bench, project_id, revision):
    def worker(state):
        plan = state.get("video_plan", {})
        if plan.get("wan_status") not in {"queued", "running"}:
            raise Conflict("No pending Wan2.2 job")
        client = comfy_client()
        result = client.request("/history/" + plan["prompt_id"]).get(plan["prompt_id"])
        if result is None:
            plan["wan_status"] = "running"
            return
        if result.get("status", {}).get("status_str") != "success":
            plan["wan_status"] = "failed"
            raise LocalRuntimeError("Wan2.2 job failed; inspect ComfyUI history")
        videos = [
            v
            for output in result.get("outputs", {}).values()
            for v in output.get("images", []) + output.get("gifs", [])
            if v.get("filename", "").lower().endswith(".mp4")
        ]
        if not videos:
            raise LocalRuntimeError("Successful workflow returned no MP4 artifact")
        # The server reports an output descriptor, never a caller-supplied URL or local path.
        descriptor = videos[0]
        query = urlencode({k: descriptor.get(k, "") for k in ("filename", "subfolder", "type")})
        with client.opener.open(client.address + "/view?" + query, timeout=60) as response:
            data = response.read(100 * 1024 * 1024 + 1)
        if len(data) > 100 * 1024 * 1024 or b"ftyp" not in data[:32]:
            raise LocalRuntimeError("ComfyUI output is not a bounded MP4")
        directory = bench.directory(project_id) / "wan"
        directory.mkdir(exist_ok=True)
        (directory / "launch-ai.mp4").write_bytes(data)
        (directory / "generation.json").write_text(
            json.dumps(
                {
                    "prompt_id": plan["prompt_id"],
                    "descriptor": descriptor,
                    "status": "generated",
                    "validation": "container_only",
                    "engineering_geometry": "not_verified",
                    "audio": "none",
                },
                indent=2,
            )
        )
        bench.register_files(state, directory, "ai_video")
        plan["wan_status"] = "generated"

    return bench._run(project_id, revision, "collect_wan22", worker)
