"""Multistage ascent model for the commercial and heavy tiers (CLAUDE.md section 7).

Implemented in phase 1 (prompt 1A).
"""

from rocketwright.schema import Design, DispersionResult, Env, SimResult


def simulate(design: Design, env: Env, seed: int | None = None) -> SimResult:
    raise NotImplementedError("multistage.simulate: implemented in phase 1 (prompt 1A)")


def dispersion(design: Design, env: Env, n: int, seed: int) -> DispersionResult:
    raise NotImplementedError("multistage.dispersion: implemented in phase 3")
