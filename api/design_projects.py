"""Revision-aware current-design production routes. Loopback tools only; no paid API."""

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from api.workbench import PlanRequest, RenderRequest, Revision, call
from rocketwright.agent.design_projects import DEFAULT_PROJECTS, DesignSpec, queue_operation
from rocketwright.agent.production import plan_video
from rocketwright.agent.project_assembly import Observation
from rocketwright.agent.project_jobs import queue
from rocketwright.analysis.schema import Precision, SearchLimits
from rocketwright.analysis.service import Harness

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


class CampaignRequest(Revision):
    precision: Precision = Field(default_factory=Precision)
    limits: SearchLimits = Field(default_factory=SearchLimits)


class IntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=4000)
    project_id: str | None = None


class AcceptIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket_id: str
    candidate_id: str


@router.post("/intent")
def intent(request: IntentRequest):
    from rocketwright.agent.project_intake import propose

    return call(propose, DEFAULT_PROJECTS, request.text, request.project_id)


@router.post("/intent/accept")
def accept_intent(request: AcceptIntent):
    from rocketwright.agent.project_intake import accept

    return call(accept, DEFAULT_PROJECTS, request.ticket_id, request.candidate_id)


@router.post("/{project_id}/adaptive/start")
def adaptive_start(project_id: str, request: CampaignRequest):
    return call(
        Harness(DEFAULT_PROJECTS).start,
        project_id,
        request.revision,
        request.precision,
        request.limits,
    )


@router.get("/{project_id}/adaptive/options")
def adaptive_options(project_id: str):
    return call(Harness(DEFAULT_PROJECTS).options, project_id)


@router.post("/{project_id}/adaptive/step", status_code=202)
def adaptive_step(project_id: str, request: Revision):
    return call(queue_operation, DEFAULT_PROJECTS, project_id, request.revision, "adaptive_step")


@router.post("/{project_id}/adaptive/run", status_code=202)
def adaptive_run(project_id: str, request: Revision):
    return call(queue_operation, DEFAULT_PROJECTS, project_id, request.revision, "adaptive_run")


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


@router.get("/{project_id}/compare/{version}")
def compare(project_id: str, version: int):
    return call(DEFAULT_PROJECTS.compare, project_id, version)


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
    return call(
        queue, DEFAULT_PROJECTS, project_id, request.revision, "render_video", request.style
    )


@router.post("/{project_id}/cancel")
def cancel(project_id: str, request: Revision):
    return call(DEFAULT_PROJECTS.cancel, project_id, request.revision)


@router.post("/{project_id}/archive")
def archive(project_id: str, request: Revision):
    return call(DEFAULT_PROJECTS.archive, project_id, request.revision)


@router.get("/{project_id}/v{version}/files/{key:path}")
def file(project_id: str, version: int, key: str):
    path = call(DEFAULT_PROJECTS.file, project_id, key, version)
    return FileResponse(path, filename=path.name, headers={"Cache-Control": "no-store"})
