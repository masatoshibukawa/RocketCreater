"""Local production workbench routes; each mutation acknowledges one revision."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from rocketwright.agent.library import DEFAULT_LIBRARY
from rocketwright.agent.local_runtime import LocalDirector, LocalJSON, LocalRuntimeError
from rocketwright.agent.production import collect_wan, plan_video, render_video, submit_wan
from rocketwright.agent.video_appearance import appearance_runtime
from rocketwright.agent.workbench import DEFAULT_WORKBENCH, Conflict, StepChoice
from rocketwright.bottle_assembly import Workshop

router = APIRouter(prefix="/workbench", tags=["workbench"])


@router.get("/library")
def library():
    return call(DEFAULT_LIBRARY.view)


@router.get("/library/assets/{asset_id}")
def library_asset(asset_id: str):
    path = call(DEFAULT_LIBRARY.file, asset_id)
    return FileResponse(path, filename=path.name, headers={"Cache-Control": "no-store"})


@router.get("/references")
def references(
    q: str = Query(default="", max_length=200),
    category: str = Query(default="all", pattern="^(all|water|model)$"),
):
    return call(DEFAULT_LIBRARY.references, q, category)


class ProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workshop: Workshop | None = None


class Revision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)


class StepRequest(Revision):
    id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=2000)


class PlanRequest(Revision):
    local: bool = True
    style: Literal["engineering", "photographic"] = "engineering"


class RenderRequest(Revision):
    style: Literal["engineering", "photographic"] = "engineering"


def call(operation, *args):
    try:
        return operation(*args)
    except KeyError as exc:
        raise HTTPException(404, "Project or artifact not found") from exc
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except LocalRuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/runtime")
def runtime():
    result = {"ollama": {"available": False, "models": []}, "comfyui": {"available": False}}
    try:
        result["ollama"] = {"available": True, "models": LocalDirector().models()}
    except LocalRuntimeError:
        pass
    try:
        import os

        client = LocalJSON(os.getenv("ROCKETWRIGHT_COMFY_URL", "http://127.0.0.1:8188"))
        stats = client.request("/system_stats", timeout=3)
        result["comfyui"] = {
            "available": True,
            "version": stats.get("system", {}).get("comfyui_version"),
        }
    except LocalRuntimeError:
        pass
    result["photographic"] = appearance_runtime()
    return result


@router.post("/projects")
def create(request: ProjectRequest):
    return call(DEFAULT_WORKBENCH.create, request.workshop)


@router.get("/projects/{project_id}")
def get_project(project_id: str):
    return call(DEFAULT_WORKBENCH.get, project_id)


@router.post("/projects/{project_id}/steps")
def step(project_id: str, request: StepRequest):
    choice = StepChoice(id=request.id, reason=request.reason)
    return call(DEFAULT_WORKBENCH.step, project_id, request.revision, choice)


@router.post("/projects/{project_id}/proposal")
def propose(project_id: str, request: Revision):
    return call(DEFAULT_WORKBENCH.propose, project_id, request.revision)


@router.post("/projects/{project_id}/exports")
def export(project_id: str, request: Revision):
    return call(DEFAULT_WORKBENCH.export, project_id, request.revision)


@router.post("/projects/{project_id}/aero-loop")
def aero_loop(project_id: str, request: Revision):
    try:
        return call(DEFAULT_WORKBENCH.aero_loop, project_id, request.revision)
    except RuntimeError as exc:  # CFD backend missing, timed out or failed
        raise HTTPException(503, str(exc)) from exc


@router.post("/projects/{project_id}/print-package")
def print_package(project_id: str, request: Revision):
    return call(DEFAULT_WORKBENCH.print_package, project_id, request.revision)


@router.get("/projects/{project_id}/trajectory")
def trajectory(project_id: str):
    try:
        return call(DEFAULT_WORKBENCH.trajectory, project_id)
    except RuntimeError as exc:  # the simulation tool reported an error
        raise HTTPException(503, str(exc)) from exc


@router.get("/projects/{project_id}/aero-images/{name}")
def aero_image(project_id: str, name: str):
    path = call(DEFAULT_WORKBENCH.aero_image, project_id, name)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/projects/{project_id}/assembly-pdf")
def assembly_pdf(project_id: str, request: Revision):
    return call(DEFAULT_WORKBENCH.manual, project_id, request.revision)


@router.post("/projects/{project_id}/video-plan")
def video_plan(project_id: str, request: PlanRequest):
    return call(
        plan_video,
        DEFAULT_WORKBENCH,
        project_id,
        request.revision,
        request.local,
        None,
        request.style,
    )


@router.post("/projects/{project_id}/render-video")
def video_render(project_id: str, request: RenderRequest):
    return call(render_video, DEFAULT_WORKBENCH, project_id, request.revision, request.style)


@router.post("/projects/{project_id}/wan")
def wan_submit(project_id: str, request: Revision):
    return call(submit_wan, DEFAULT_WORKBENCH, project_id, request.revision)


@router.post("/projects/{project_id}/wan-result")
def wan_result(project_id: str, request: Revision):
    return call(collect_wan, DEFAULT_WORKBENCH, project_id, request.revision)


@router.get("/projects/{project_id}/files/{key:path}")
def artifact(project_id: str, key: str):
    path = call(DEFAULT_WORKBENCH.file, project_id, key)
    return FileResponse(path, filename=path.name, headers={"Cache-Control": "no-store"})
