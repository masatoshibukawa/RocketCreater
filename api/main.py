"""FastAPI entry point. POST /design streams agent progress as SSE (added in phase 1B)."""

from fastapi import FastAPI

from rocketwright import __version__

app = FastAPI(title="RocketWright", version=__version__)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
