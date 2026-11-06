"""Revision-aware current-design production routes. Loopback tools only; no paid API."""

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from api.workbench import PlanRequest, RenderRequest, Revision, call
from rocketwright.agent.design_projects import DEFAULT_PROJECTS, DesignSpec, queue_operation
from rocketwright.agent.production import plan_video, queue_video
from rocketwright.agent.project_assembly import Observation

router = APIRouter(prefix="/design-projects", tags=["design-production"])


class EditRequest(Revision):
    spec: DesignSpec


class RestoreRequest(Revision):
    version: int = Field(ge=1)


class CreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec: DesignSpec


class ObservationRequest(Revision):
    observation: Observation


@router.get("")
def listing():
    return {"projects": call(DEFAULT_PROJECTS.list)}


@router.post("")
def create(request: CreateRequest):
    return call(DEFAULT_PROJECTS.create, request.spec)


@router.get("/catalog")
def catalog():
    from rocketwright.agent.project_catalog import reconciled_catalog

    return call(reconciled_catalog)


@router.get("/{project_id}")
def project(project_id: str):
    return call(DEFAULT_PROJECTS.get, project_id)


@router.post("/{project_id}/edit")
def edit(project_id: str, request: EditRequest):
    return call(DEFAULT_PROJECTS.edit, project_id, request.revision, request.spec)


@router.post("/{project_id}/restore")
def restore(project_id: str, request: RestoreRequest):
    return call(DEFAULT_PROJECTS.restore, project_id, request.revision, request.version)


@router.post("/{project_id}/analyse", status_code=202)
def analyse(project_id: str, request: Revision):
    return call(queue_operation, DEFAULT_PROJECTS, project_id, request.revision, "analyse")


@router.post("/{project_id}/adopt")
def adopt(project_id: str, request: Revision):
    return call(DEFAULT_PROJECTS.adopt, project_id, request.revision)


@router.post("/{project_id}/manual")
def manual(project_id: str, request: Revision):
    return call(DEFAULT_PROJECTS.manual, project_id, request.revision)


@router.post("/{project_id}/observe")
def observe(project_id: str, request: ObservationRequest):
    return call(DEFAULT_PROJECTS.observe, project_id, request.revision, request.observation)


@router.post("/{project_id}/print", status_code=202)
def printing(project_id: str, request: Revision):
    return call(queue_operation, DEFAULT_PROJECTS, project_id, request.revision, "print_package")


@router.post("/{project_id}/video-plan")
def direction(project_id: str, request: PlanRequest):
    state = call(DEFAULT_PROJECTS.get, project_id)
    call(DEFAULT_PROJECTS.require_adopted, state)
    return call(
        plan_video,
        DEFAULT_PROJECTS,
        project_id,
        request.revision,
        request.local,
        None,
        request.style,
    )


@router.post("/{project_id}/render-video", status_code=202)
def render(project_id: str, request: RenderRequest):
    call(DEFAULT_PROJECTS.require_adopted, call(DEFAULT_PROJECTS.get, project_id))
    return call(queue_video, DEFAULT_PROJECTS, project_id, request.revision, request.style)


@router.post("/{project_id}/archive")
def archive(project_id: str, request: Revision):
    return call(DEFAULT_PROJECTS.archive, project_id, request.revision)


@router.get("/{project_id}/v{version}/files/{key:path}")
def file(project_id: str, version: int, key: str):
    path = call(DEFAULT_PROJECTS.file, project_id, key, version)
    return FileResponse(path, filename=path.name, headers={"Cache-Control": "no-store"})
