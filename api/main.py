"""FastAPI entry point. POST /design streams agent progress as server-sent events."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from rocketwright import __version__
from rocketwright.agent.loop import run_design_loop
from rocketwright.schema import Env

CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

app = FastAPI(title="RocketWright", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DesignRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    seed: int | None = None
    env: Env | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


async def _sse(request: DesignRequest) -> AsyncIterator[str]:
    # `run_design_loop` is looked up at call time so tests can monkeypatch it on this module.
    async for event in run_design_loop(request.text, seed=request.seed, env=request.env):
        yield f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


@app.post("/design")
async def design(request: DesignRequest) -> StreamingResponse:
    return StreamingResponse(
        _sse(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
