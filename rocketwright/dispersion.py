"""Monte Carlo dispersion runner shared by all physics models (CLAUDE.md section 7).

`run_dispersion` perturbs a design/environment `n` times, simulates every sample and reduces the
`SimResult`s to a `DispersionResult`: success rate, p05/p50/p95 of every metric, bucketed
failure reasons, and the tier-specific block (landing scatter + 95 % ellipse for bottle/amateur,
orbit-insertion error distribution for commercial/heavy).

Determinism: sample `i` draws from `numpy.random.default_rng([seed, i])`, so the result depends
only on (design, env, n, seed) and not on the execution order or the worker count.

The nominal (unperturbed) run is simulated once more alongside the samples; it is NOT one of the
`n` samples (success_rate and the quantiles are over the perturbed samples only). It is the
reference for the orbit-insertion errors and is returned by `run_dispersion_detailed`
(agent/tools.py echoes its metrics as `nominal` in the tool result).

The per-tier perturbations (`perturb_bottle`, `perturb_amateur`, `perturb_multistage`) take
their sigmas from `DISPERSION_SPEC`. Every sigma is PROVISIONAL (no source yet, see README
"要確認"). Quantities that are not design/env fields (motor thrust, engine Isp/thrust) are passed
to the simulate callable as keyword scales (`thrust_scale`, `isp_scale`).

Samples run in a `concurrent.futures.ProcessPoolExecutor` when n >= `POOL_THRESHOLD`
(environment variable ROCKETWRIGHT_DISPERSION_WORKERS overrides the worker count; 0 = inline).
The workers come from a forkserver, never from a fork of the caller: the API has other threads,
and a child forked while one of them holds the stdout lock hangs forever when it exits.
"""

from __future__ import annotations

import math
import multiprocessing
import os
import re
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from typing import Any

import numpy as np

from rocketwright.schema import (
    AmateurDesign,
    BottleDesign,
    Design,
    DispersionResult,
    Ellipse95,
    Env,
    LandingPoint,
    LandingScatter,
    MultistageDesign,
    OrbitInsertionStats,
    OrbitSample,
    Quantiles,
    SimResult,
    Tier,
)

__all__ = [
    "CHI2_2DOF_95",
    "DISPERSION_SPEC",
    "MAX_SAMPLES",
    "POOL_THRESHOLD",
    "DispersionRun",
    "Perturbation",
    "components_for",
    "ellipse_95",
    "metric_quantiles",
    "normalize_reason",
    "perturb_amateur",
    "perturb_bottle",
    "perturb_multistage",
    "run_dispersion",
    "run_dispersion_detailed",
    "summarize_landing",
    "summarize_orbit",
]

# --------------------------------------------------------------------------- spec

# One-sigma perturbations per tier (CLAUDE.md section 7 "多数回試行"). Every entry is
# PROVISIONAL: round numbers chosen for a plausible demo, awaiting a source (motor certification
# scatter, launch-site wind statistics, engine acceptance-test tolerances). `_frac` keys are
# relative (multiplicative) sigmas, the others are absolute in the unit of their suffix.
DISPERSION_SPEC: dict[Tier, dict[str, float]] = {
    Tier.BOTTLE: {
        "pressure_frac": 0.05,  # provisional: hand-pump gauge reading scatter
        "wind_speed_mps": 1.0,  # provisional
        "wind_direction_deg": 20.0,  # provisional
    },
    Tier.AMATEUR: {
        "thrust_frac": 0.05,  # provisional: motor total-impulse lot-to-lot scatter
        "dry_mass_frac": 0.03,  # provisional: build-mass uncertainty
        "wind_speed_mps": 1.5,  # provisional
        "wind_direction_deg": 30.0,  # provisional
        "deploy_delay_s": 0.5,  # provisional: ejection-charge timing (clipped at 0)
    },
    Tier.COMMERCIAL: {
        "isp_frac": 0.01,  # provisional: engine acceptance-test Isp tolerance
        "thrust_frac": 0.02,  # provisional: engine thrust tolerance
        "structural_fraction_frac": 0.05,  # provisional: dry-mass growth, relative
    },
    Tier.HEAVY: {
        "isp_frac": 0.01,  # provisional
        "thrust_frac": 0.02,  # provisional
        "structural_fraction_frac": 0.05,  # provisional
    },
}
DISPERSION_SPEC_PROVISIONAL = True

# Relative scales are clipped to this band so a 4-sigma draw can never produce a non-physical
# (zero/negative) thrust, Isp or mass.
_SCALE_CLIP = (0.5, 1.5)
_STRUCTURAL_FRACTION_CLIP = (1e-3, 0.999)

# chi-square quantile with 2 degrees of freedom at 95 %: the ellipse containing 95 % of a
# bivariate normal has semi-axes sqrt(CHI2 * eigenvalue).
CHI2_2DOF_95 = 5.991
MAX_SAMPLES = 5000  # schema cap on LandingScatter.points / OrbitInsertionStats.samples
POOL_THRESHOLD = 32  # below this the process-pool start-up costs more than it saves
POOL_PRELOAD = ["rocketwright.agent.tools"]

Perturbation = tuple[Design, Env, dict[str, float]]
PerturbFn = Callable[[Design, Env, np.random.Generator], Perturbation]
SimulateFn = Callable[..., SimResult]  # (design, env, seed, **scales) -> SimResult
SummarizeFn = Callable[
    [list[SimResult], SimResult], tuple[LandingScatter | None, OrbitInsertionStats | None]
]


# --------------------------------------------------------------------------- perturbations


def _clip(value: float, lo: float, hi: float) -> float:
    return min(max(value, lo), hi)


def _rel(rng: np.random.Generator, sigma_frac: float) -> float:
    """A multiplicative factor 1 + N(0, sigma), clipped to `_SCALE_CLIP`."""
    return _clip(1.0 + sigma_frac * float(rng.normal()), *_SCALE_CLIP)


def _perturb_wind(
    env: Env, rng: np.random.Generator, sigma_speed_mps: float, sigma_direction_deg: float
) -> Env:
    speed = max(env.wind_speed_mps + sigma_speed_mps * float(rng.normal()), 0.0)
    direction = (env.wind_direction_deg + sigma_direction_deg * float(rng.normal())) % 360.0
    return env.model_copy(update={"wind_speed_mps": speed, "wind_direction_deg": direction})


def perturb_bottle(design: Design, env: Env, rng: np.random.Generator) -> Perturbation:
    """Bottle: initial gauge pressure (relative) and wind speed / direction."""
    if not isinstance(design, BottleDesign):
        raise ValueError(f"perturb_bottle needs a bottle design, got {design.tier!r}")
    s = DISPERSION_SPEC[Tier.BOTTLE]
    new_design = design.model_copy(
        update={
            "initial_gauge_pressure_pa": design.initial_gauge_pressure_pa
            * _rel(rng, s["pressure_frac"])
        }
    )
    return new_design, _perturb_wind(env, rng, s["wind_speed_mps"], s["wind_direction_deg"]), {}


def perturb_amateur(design: Design, env: Env, rng: np.random.Generator) -> Perturbation:
    """Amateur: motor total impulse (`thrust_scale` keyword), dry mass, wind, deploy delay."""
    if not isinstance(design, AmateurDesign):
        raise ValueError(f"perturb_amateur needs an amateur design, got {design.tier!r}")
    s = DISPERSION_SPEC[Tier.AMATEUR]
    thrust_scale = _rel(rng, s["thrust_frac"])
    new_design = design.model_copy(
        update={
            "dry_mass_kg": design.dry_mass_kg * _rel(rng, s["dry_mass_frac"]),
            "deploy_delay_s": max(
                design.deploy_delay_s + s["deploy_delay_s"] * float(rng.normal()), 0.0
            ),
        }
    )
    new_env = _perturb_wind(env, rng, s["wind_speed_mps"], s["wind_direction_deg"])
    return new_design, new_env, {"thrust_scale": thrust_scale}


def perturb_multistage(design: Design, env: Env, rng: np.random.Generator) -> Perturbation:
    """Commercial/heavy: Isp and thrust (`isp_scale` / `thrust_scale` keywords, one draw each
    for the whole vehicle) and every stage's structural fraction (independent draws)."""
    if not isinstance(design, MultistageDesign):
        raise ValueError(f"perturb_multistage needs a commercial/heavy design, got {design.tier!r}")
    s = DISPERSION_SPEC[Tier(design.tier)]
    isp_scale = _rel(rng, s["isp_frac"])
    thrust_scale = _rel(rng, s["thrust_frac"])
    stages = [
        stage.model_copy(
            update={
                "structural_fraction": _clip(
                    stage.structural_fraction * _rel(rng, s["structural_fraction_frac"]),
                    *_STRUCTURAL_FRACTION_CLIP,
                )
            }
        )
        for stage in design.stages
    ]
    new_design = design.model_copy(update={"stages": stages})
    return new_design, env, {"isp_scale": isp_scale, "thrust_scale": thrust_scale}


def components_for(tier: Tier | str) -> tuple[PerturbFn, SummarizeFn]:
    """(perturb, summarize) for a tier, for callers that bring their own simulate callable."""
    t = Tier(tier)
    if t is Tier.BOTTLE:
        return perturb_bottle, summarize_landing
    if t is Tier.AMATEUR:
        return perturb_amateur, summarize_landing
    return perturb_multistage, summarize_orbit


# --------------------------------------------------------------------------- reductions

# A number not glued to a letter/underscore (so catalog ids such as "dummy_G80" survive).
_NUMBER_RE = re.compile(r"(?<![A-Za-z_\d])[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?")


def normalize_reason(text: str) -> str:
    """Bucket key for a failure reason: numbers replaced by `N`, whitespace collapsed, so
    "perigee 289.9 km below target 400 km" and "perigee 301.2 km below target 400 km" count as
    one reason."""
    return re.sub(r"\s+", " ", _NUMBER_RE.sub("N", text)).strip()


def metric_quantiles(samples: list[SimResult]) -> dict[str, Quantiles]:
    """p05/p50/p95 of every metric key (keys in first-seen order); NaN / inf values are dropped
    and keys with no finite value are skipped."""
    keys: list[str] = []
    seen: set[str] = set()
    for s in samples:
        for k in s.metrics:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    out: dict[str, Quantiles] = {}
    for k in keys:
        values = np.array([s.metrics[k] for s in samples if k in s.metrics], dtype=float)
        values = values[np.isfinite(values)]
        if values.size == 0:
            continue
        p05, p50, p95 = (float(v) for v in np.percentile(values, [5.0, 50.0, 95.0]))
        out[k] = Quantiles(p05=p05, p50=p50, p95=p95)
    return out


def ellipse_95(points: list[LandingPoint]) -> Ellipse95:
    """95 % containment ellipse of a 2-D normal fitted to the points: centre = mean,
    semi-axes = sqrt(CHI2_2DOF_95 * eigenvalues of the covariance), angle of the major axis from
    east (counter-clockwise, normalised to [-90, 90)). Fewer than 2 points -> degenerate."""
    if not points:
        return Ellipse95(
            center_east_m=0.0, center_north_m=0.0, semi_major_m=0.0, semi_minor_m=0.0, angle_deg=0.0
        )
    xy = np.array([[p.east_m, p.north_m] for p in points], dtype=float)
    center = xy.mean(axis=0)
    if len(points) < 2:
        return Ellipse95(
            center_east_m=float(center[0]),
            center_north_m=float(center[1]),
            semi_major_m=0.0,
            semi_minor_m=0.0,
            angle_deg=0.0,
        )
    cov = np.cov(xy, rowvar=False)
    eigenvalues, eigenvectors = np.linalg.eigh(cov)  # ascending
    major = eigenvectors[:, 1]
    angle = math.degrees(math.atan2(float(major[1]), float(major[0])))
    angle = ((angle + 90.0) % 180.0) - 90.0
    return Ellipse95(
        center_east_m=float(center[0]),
        center_north_m=float(center[1]),
        semi_major_m=math.sqrt(CHI2_2DOF_95 * max(float(eigenvalues[1]), 0.0)),
        semi_minor_m=math.sqrt(CHI2_2DOF_95 * max(float(eigenvalues[0]), 0.0)),
        angle_deg=angle,
    )


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def summarize_landing(
    samples: list[SimResult], nominal: SimResult
) -> tuple[LandingScatter | None, OrbitInsertionStats | None]:
    """Landing points of every sample with a finite landing_east_m / landing_north_m."""
    del nominal
    points = [
        LandingPoint(east_m=s.metrics["landing_east_m"], north_m=s.metrics["landing_north_m"])
        for s in samples
        if _finite(s.metrics.get("landing_east_m")) and _finite(s.metrics.get("landing_north_m"))
    ]
    return LandingScatter(points=points[:MAX_SAMPLES], ellipse_95=ellipse_95(points)), None


def _quantiles_of(values: list[float]) -> Quantiles:
    if not values:
        return Quantiles(p05=0.0, p50=0.0, p95=0.0)
    p05, p50, p95 = (float(v) for v in np.percentile(np.array(values), [5.0, 50.0, 95.0]))
    return Quantiles(p05=p05, p50=p50, p95=p95)


def summarize_orbit(
    samples: list[SimResult], nominal: SimResult
) -> tuple[LandingScatter | None, OrbitInsertionStats | None]:
    """Perigee / apogee errors relative to the nominal run, payload-margin distribution and the
    per-sample (perigee, apogee, margin) list."""
    keys = ("perigee_m", "apogee_m", "payload_margin_kg")
    valid = [s for s in samples if all(_finite(s.metrics.get(k)) for k in keys)]
    ref_perigee = nominal.metrics.get("perigee_m", 0.0)
    ref_apogee = nominal.metrics.get("apogee_m", 0.0)
    stats = OrbitInsertionStats(
        perigee_error_m=_quantiles_of([s.metrics["perigee_m"] - ref_perigee for s in valid]),
        apogee_error_m=_quantiles_of([s.metrics["apogee_m"] - ref_apogee for s in valid]),
        payload_margin_kg=_quantiles_of([s.metrics["payload_margin_kg"] for s in valid]),
        samples=[
            OrbitSample(
                perigee_m=s.metrics["perigee_m"],
                apogee_m=s.metrics["apogee_m"],
                payload_margin_kg=s.metrics["payload_margin_kg"],
            )
            for s in valid[:MAX_SAMPLES]
        ],
    )
    return None, stats


# --------------------------------------------------------------------------- runner


@dataclass(frozen=True)
class DispersionRun:
    """`run_dispersion_detailed` output: the result plus the nominal run and every sample."""

    result: DispersionResult
    nominal: SimResult
    samples: tuple[SimResult, ...]


def _run_sample(args: tuple[Any, ...]) -> SimResult:
    """Module-level worker (picklable): perturb with rng([seed, i]) and simulate. A model
    exception (integration failure, invalid perturbed design) becomes a failed SimResult so
    one bad draw does not abort the whole run."""
    design, env, seed, index, tier, perturb, simulate = args
    rng = np.random.default_rng([seed, index])
    try:
        d, e, scales = perturb(design, env, rng)
        return simulate(d, e, seed, **scales)
    except (RuntimeError, ValueError, KeyError) as exc:
        return SimResult(
            tier=tier,
            success=False,
            failure_reasons=[f"simulation error: {type(exc).__name__}: {exc}"],
            cost_jpy=0.0,
        )


def _worker_count(n: int) -> int:
    """Processes to use for n samples: 0 means inline."""
    raw = os.environ.get("ROCKETWRIGHT_DISPERSION_WORKERS")
    if raw is not None:
        try:
            return max(int(raw), 0)
        except ValueError:
            pass
    if n < POOL_THRESHOLD:
        return 0
    return max(1, min(os.cpu_count() or 1, 8, n // 8))


def pool_context() -> multiprocessing.context.BaseContext:
    context = multiprocessing.get_context("forkserver")
    context.set_forkserver_preload(POOL_PRELOAD)  # workers start warm, not with a fresh import
    return context


def _simulate_all(
    args: list[tuple[Any, ...]], workers: int, warnings: list[str]
) -> list[SimResult]:
    if workers <= 1:
        return [_run_sample(a) for a in args]
    chunksize = max(1, len(args) // (workers * 4))
    try:
        with ProcessPoolExecutor(max_workers=workers, mp_context=pool_context()) as pool:
            return list(pool.map(_run_sample, args, chunksize=chunksize))
    except (BrokenProcessPool, OSError) as exc:
        warnings.append(f"process pool unavailable ({type(exc).__name__}); samples ran inline")
        return [_run_sample(a) for a in args]


def run_dispersion_detailed(
    design: Design,
    env: Env,
    n: int,
    seed: int,
    *,
    perturb: PerturbFn,
    simulate: SimulateFn,
    tier: Tier,
    summarize: SummarizeFn,
) -> DispersionRun:
    """Nominal run + n perturbed samples -> DispersionResult (see module docstring).

    `perturb(design, env, rng) -> (design, env, scales)`; `simulate(design, env, seed, **scales)`
    must be picklable (module-level function or functools.partial of one) because samples may
    run in worker processes."""
    if n < 1:
        raise ValueError("n must be >= 1")
    nominal = simulate(design, env, seed)
    args = [(design, env, seed, i, tier, perturb, simulate) for i in range(n)]
    warnings: list[str] = []
    samples = _simulate_all(args, _worker_count(n), warnings)

    success_rate = sum(1 for s in samples if s.success) / n
    failure_counts = Counter(
        normalize_reason(r) for s in samples if not s.success for r in s.failure_reasons
    )
    seen: set[str] = set()
    for s in (nominal, *samples):
        for w in s.warnings:
            if w not in seen:
                seen.add(w)
                warnings.append(w)
    landing, orbit = summarize(samples, nominal)
    result = DispersionResult(
        tier=tier,
        n=n,
        seed=seed,
        success_rate=success_rate,
        quantiles=metric_quantiles(samples),
        failure_counts=dict(failure_counts.most_common()),
        landing=landing,
        orbit_insertion=orbit,
        warnings=warnings,
    )
    return DispersionRun(result=result, nominal=nominal, samples=tuple(samples))


def run_dispersion(
    design: Design,
    env: Env,
    n: int,
    seed: int,
    *,
    perturb: PerturbFn,
    simulate: SimulateFn,
    tier: Tier,
    summarize: SummarizeFn,
) -> DispersionResult:
    """`run_dispersion_detailed(...).result` (the common `dispersion()` interface)."""
    return run_dispersion_detailed(
        design, env, n, seed, perturb=perturb, simulate=simulate, tier=tier, summarize=summarize
    ).result
