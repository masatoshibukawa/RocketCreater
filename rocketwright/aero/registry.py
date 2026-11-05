"""Backend registry, automatic choice and the per-shape disk cache.

`evaluate(query, backend="auto")` picks the best available CFD backend that supports the design
(registration order = preference) and falls back to the L0 Barrowman backend. Results of
cacheable (CFD) backends are stored as JSON under `$ROCKETWRIGHT_AERO_CACHE` (default
`~/.cache/rocketwright/aero/`), keyed by sha256 of (backend name, airframe STL bytes, speed,
angles), so the same shape at the same condition is never solved twice. The CG is not part of
the key: a hit recomputes the static margin for the query's CG.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from rocketwright.aero.base import AeroBackend, AeroQuery, AeroResult
from rocketwright.geometry import airframe

__all__ = [
    "BACKEND_NAMES",
    "L0_BACKEND",
    "backends",
    "cache_dir",
    "cache_key",
    "evaluate",
    "get_backend",
    "register",
    "status",
]

L0_BACKEND = "barrowman"
_REGISTRY: dict[str, AeroBackend] = {}


def register(backend: AeroBackend, *, replace: bool = False) -> None:
    if backend.name in _REGISTRY and not replace:
        raise ValueError(f"aero backend {backend.name!r} is already registered")
    _REGISTRY[backend.name] = backend


def unregister(name: str) -> None:
    _REGISTRY.pop(name, None)


def backends() -> dict[str, AeroBackend]:
    return dict(_REGISTRY)


def get_backend(name: str) -> AeroBackend:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise ValueError(f"unknown aero backend {name!r}; known: {sorted(_REGISTRY)}") from None


def status() -> dict[str, dict[str, object]]:
    out = {}
    for name, b in _REGISTRY.items():
        ok, reason = b.available()
        out[name] = {"available": ok, "reason": reason, "fidelity": b.fidelity}
    return out


def cache_dir() -> Path:
    env = os.environ.get("ROCKETWRIGHT_AERO_CACHE")
    return Path(env).expanduser() if env else Path.home() / ".cache" / "rocketwright" / "aero"


def cache_key(backend: str, query: AeroQuery) -> str:
    h = hashlib.sha256()
    h.update(backend.encode())
    h.update(b"\0")
    h.update(airframe(query.design).stl_bytes())
    h.update(
        json.dumps([round(query.speed_mps, 6), [round(a, 6) for a in query.alphas_deg]]).encode()
    )
    h.update(json.dumps(query.extra, sort_keys=True, default=str).encode())
    return h.hexdigest()


def _cached_call(backend: AeroBackend, query: AeroQuery) -> AeroResult:
    if not backend.cacheable:
        return backend.evaluate(query)
    key = cache_key(backend.name, query)
    path = cache_dir() / f"{key}.json"
    if path.exists():
        try:
            hit = AeroResult.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            hit = None  # corrupt entry: solve again and overwrite
        if hit is not None:
            cg = query.cg_from_nose_m if query.cg_from_nose_m is not None else hit.cg_from_nose_m
            return hit.with_cg(cg).model_copy(update={"cached": True})
    result = backend.evaluate(query)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)
    return result


def _auto_order(query: AeroQuery) -> tuple[list[AeroBackend], list[str]]:
    chosen, skipped = [], []
    for name, b in _REGISTRY.items():
        if b.fidelity == "L0":
            continue
        ok, reason = b.available()
        if ok:
            ok, reason = b.supports(query.design)
        if ok:
            chosen.append(b)
        else:
            skipped.append(f"{name}: {reason}")
    return chosen, skipped


def evaluate(query: AeroQuery, backend: str = "auto") -> AeroResult:
    """Run one backend (by name) or the best available one ("auto")."""
    if backend != "auto":
        b = get_backend(backend)
        ok, reason = b.available()
        if not ok:
            raise RuntimeError(f"aero backend {backend!r} unavailable: {reason}")
        ok, reason = b.supports(query.design)
        if not ok:
            raise ValueError(f"aero backend {backend!r} cannot evaluate this design: {reason}")
        return _cached_call(b, query)
    candidates, notes = _auto_order(query)
    for b in candidates:
        try:
            result = _cached_call(b, query)
        except (RuntimeError, ValueError, OSError) as exc:
            notes.append(f"{b.name} failed: {str(exc)[:300]}")
            continue
        return result.model_copy(update={"notes": [*result.notes, *notes]})
    result = _cached_call(get_backend(L0_BACKEND), query)
    return result.model_copy(
        update={"notes": [*result.notes, "auto: no CFD backend usable, L0 used", *notes]}
    )


BACKEND_NAMES = ("auto", "barrowman", "openfoam_pipeline", "lbm_gpu")
