"""Flow analysis of a free-request design. The loop takes minutes, so a request only starts a
job: POST answers at once and the browser polls GET until the job ends."""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from rocketwright import aero
from rocketwright.agent.design_aero import (
    DEFAULT_AERO_JOBS,
    JobQueueFull,
    configured_backend,
    run_design_aero,
)
from rocketwright.agent.tools import DISPERSION_MAX_N
from rocketwright.schema import AmateurDesign, BottleDesign, Design, Env, Requirement

router = APIRouter(prefix="/aero", tags=["aero"])


class AeroLoopRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    design: Design
    target_altitude_m: float = Field(gt=0, allow_inf_nan=False)
    requirement: Requirement | None = None
    env: Env | None = None
    seed: int | None = None  # dispersion seed and size, so a run of the agent can be repeated
    n: int | None = Field(default=None, ge=1, le=DISPERSION_MAX_N)


@router.post("/loop", status_code=202)
def start_loop(request: AeroLoopRequest):
    if not isinstance(request.design, AmateurDesign | BottleDesign):
        raise HTTPException(422, "流体解析はボトルとアマチュアの案だけです")
    try:
        backend = configured_backend()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    def work() -> dict:
        return run_design_aero(
            request.design,
            request.target_altitude_m,
            env=request.env or Env(),
            requirement=request.requirement,
            backend=backend,
            seed=request.seed,
            n=request.n,
        )

    key = json.dumps([request.model_dump(mode="json"), backend], sort_keys=True)
    try:
        return DEFAULT_AERO_JOBS.submit(key, work)
    except JobQueueFull as exc:
        raise HTTPException(429, str(exc)) from exc


@router.get("/loop/{job_id}")
def loop_status(job_id: str):
    try:
        return DEFAULT_AERO_JOBS.view(job_id)
    except KeyError as exc:
        raise HTTPException(404, "解析の記録がありません") from exc


@router.get("/loop/{job_id}/images/{name}")
def loop_image(job_id: str, name: str):
    try:
        path = aero.flow_image_path(DEFAULT_AERO_JOBS.artifacts_dir(job_id), name)
    except KeyError as exc:
        raise HTTPException(404, "画像がありません") from exc
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})
