"""The flight/CFD loop on a free-request design, without a workbench project.

A run takes minutes with a CFD backend, longer than a request should stay open, so `AeroJobs`
runs one at a time on a worker thread and keeps the result for polling. Jobs live in this
process only: a restarted API has forgotten them, and the browser is told so by a 404.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from rocketwright import aero
from rocketwright.agent.tools import DISPERSION_DEFAULT_N, execute_tool
from rocketwright.agent.workbench import AERO_BACKEND_ENV
from rocketwright.bottle_candidates import CONFIRMATION_SEED, PRESSURE_KPA
from rocketwright.physics import solid
from rocketwright.schema import (
    AmateurDesign,
    BottleDesign,
    Design,
    Env,
    GoalKind,
    Requirement,
)

__all__ = [
    "DEFAULT_AERO_JOBS",
    "AeroJobs",
    "JobQueueFull",
    "bottle_pressures_kpa",
    "configured_backend",
    "run_design_aero",
]

MAX_KEPT_JOBS = 32
MAX_PENDING_JOBS = 4
MAX_ERROR_CHARS = 500

logger = logging.getLogger(__name__)


def configured_backend() -> str:
    backend = os.getenv(AERO_BACKEND_ENV, "auto")
    if backend not in aero.BACKEND_NAMES:
        raise ValueError(f"{AERO_BACKEND_ENV} must be one of {aero.BACKEND_NAMES}")
    return backend


def bottle_pressures_kpa(design: BottleDesign) -> list[float]:
    """Pressures the loop may pick: the listed ones below the design's own, then its own. A free
    design names no launcher or rating here, so the loop must not raise what the design chose."""
    own = design.initial_gauge_pressure_pa / 1000.0
    return [*(float(p) for p in PRESSURE_KPA if p < own), own]


def _loop_requirement(
    design: BottleDesign, target_altitude_m: float, requirement: Requirement | None
) -> Requirement:
    """The request's target decides. The budget does not: the loop moves pressure and Cd only,
    and cost.py's estimate could contradict the parts bill the design passed on."""
    base = requirement or Requirement(
        goal_kind=GoalKind.ALTITUDE,
        target_altitude_m=target_altitude_m,
        payload_mass_kg=design.payload_mass_kg,
        recovery_required=design.has_parachute,
    )
    return base.model_copy(update={"target_altitude_m": target_altitude_m, "budget_jpy": None})


def _spread(
    design: BottleDesign, env: Env, requirement: Requirement, seed: int, n: int
) -> dict[str, Any]:
    spread = execute_tool(
        "run_dispersion",
        {
            "design": design.model_dump(mode="json"),
            "env": env.model_dump(mode="json"),
            "requirement": requirement.model_dump(mode="json"),
            "seed": seed,
            "n": n,
        },
        "aero-loop",
    )
    if "error" in spread:
        raise RuntimeError(spread["error"])
    return {
        "n": n,
        "seed": seed,
        "success_rate": spread["success_rate"],
        "passes": round(n * spread["success_rate"]),
        "failure_counts": spread["failure_counts"],
    }


def run_design_aero(
    design: Design,
    target_altitude_m: float,
    *,
    env: Env,
    requirement: Requirement | None = None,
    backend: str = "auto",
    seed: int | None = None,
    n: int | None = None,
) -> dict[str, Any]:
    """Loop result for the UI. On a bottle it is a CFD-based alternative beside the design, which
    stays as it is. `artifacts_dir` is the server's own path and stays out of AeroJobs.view."""
    common = {"tier": design.tier, "target_altitude_m": target_altitude_m}
    if isinstance(design, AmateurDesign):
        result = aero.run_amateur_aero_loop(
            design, env, target_apogee_m=target_altitude_m, backend=backend
        )
        baseline = {"pressure_kpa": None, "cd": solid.DEFAULT_CD}
        spread = None  # AmateurDesign has no Cd field, so a dispersion cannot fly the CFD Cd
    elif isinstance(design, BottleDesign):
        result = aero.run_aero_loop(
            design,
            env,
            target_apogee_m=target_altitude_m,
            pressures_kpa=bottle_pressures_kpa(design),
            backend=backend,
        )
        baseline = {
            "pressure_kpa": design.initial_gauge_pressure_pa / 1000.0,
            "cd": design.axial_drag_coefficient,
        }
        spread = _spread(
            result.final_design,
            env,
            _loop_requirement(design, target_altitude_m, requirement),
            CONFIRMATION_SEED if seed is None else seed,
            DISPERSION_DEFAULT_N if n is None else n,
        )
    else:
        raise ValueError("the aero loop covers the bottle and amateur tiers only")
    return result.model_dump(mode="json") | common | {
        "backend_requested": backend,
        "baseline": baseline,
        "dispersion": spread,
    }


class JobQueueFull(RuntimeError):
    pass


@dataclass(frozen=True)
class _Job:
    id: str
    key: str
    status: str = "queued"  # queued | running | done | failed
    started_at: float | None = None
    finished_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class AeroJobs:
    """One worker, bounded queue, finished jobs forgotten oldest first. An identical request
    shares the job that is running or done; a failed one starts afresh."""

    def __init__(self, max_kept: int = MAX_KEPT_JOBS, max_pending: int = MAX_PENDING_JOBS) -> None:
        self._jobs: OrderedDict[str, _Job] = OrderedDict()
        self._max_kept = max_kept
        self._max_pending = max_pending
        self._lock = threading.Lock()
        self._queue: queue.SimpleQueue[tuple[str, Callable[[], dict[str, Any]]]] = (
            queue.SimpleQueue()
        )
        self._worker: threading.Thread | None = None

    def submit(self, key: str, work: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            shared = next(
                (j for j in self._jobs.values() if j.key == key and j.status != "failed"), None
            )
            if shared is not None:
                return self._view(shared)
            pending = sum(j.status in ("queued", "running") for j in self._jobs.values())
            if pending >= self._max_pending:
                raise JobQueueFull("流体解析の待ちがいっぱいです。終わってから実行してください")
            job = _Job(id=uuid.uuid4().hex, key=key)
            self._jobs[job.id] = job
            self._forget_finished()
            if self._worker is None:
                # daemon: an API stopped in the middle of a solve must not wait for it
                self._worker = threading.Thread(target=self._serve, daemon=True, name="aero-jobs")
                self._worker.start()
        self._queue.put((job.id, work))
        return self._view(job)

    def _forget_finished(self) -> None:
        finished = [j.id for j in self._jobs.values() if j.status in ("done", "failed")]
        while len(self._jobs) > self._max_kept and finished:
            del self._jobs[finished.pop(0)]

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            self._jobs[job_id] = replace(self._jobs[job_id], **changes)

    def _serve(self) -> None:
        while True:
            job_id, work = self._queue.get()
            self._update(job_id, status="running", started_at=time.time())
            try:
                result = work()
            except Exception as exc:  # a failed job reports; the worker must outlive it
                logger.exception("aero job %s failed", job_id)
                self._update(
                    job_id,
                    status="failed",
                    finished_at=time.time(),
                    error=str(exc)[:MAX_ERROR_CHARS] or type(exc).__name__,
                )
            else:
                self._update(job_id, status="done", finished_at=time.time(), result=result)

    def _view(self, job: _Job) -> dict[str, Any]:
        result = None if job.result is None else dict(job.result)
        artifacts = None if result is None else result.pop("artifacts_dir", None)
        elapsed = None
        if job.started_at is not None:
            elapsed = (job.finished_at or time.time()) - job.started_at
        return {
            "id": job.id,
            "status": job.status,
            "elapsed_s": elapsed,
            "result": result,
            "error": job.error,
            "live": aero.live.snapshot() if job.status == "running" else None,
            "images": [
                image | {"url": f"/aero/loop/{job.id}/images/{image['name']}"}
                for image in aero.flow_images(artifacts)
            ],
        }

    def view(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            return self._view(self._jobs[job_id])

    def artifacts_dir(self, job_id: str) -> str | None:
        with self._lock:
            result = self._jobs[job_id].result
        return None if result is None else result.get("artifacts_dir")


DEFAULT_AERO_JOBS = AeroJobs()
