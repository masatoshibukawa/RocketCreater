"""Solid-motor model for the amateur tier (CLAUDE.md section 7). Implemented in phase 2."""

from rocketwright.schema import Design, DispersionResult, Env, SimResult


def simulate(design: Design, env: Env, seed: int | None = None) -> SimResult:
    raise NotImplementedError("solid.simulate: implemented in phase 2")


def dispersion(design: Design, env: Env, n: int, seed: int) -> DispersionResult:
    raise NotImplementedError("solid.dispersion: implemented in phase 3")
