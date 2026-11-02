"""Water-rocket model for the bottle tier (CLAUDE.md section 7). Implemented in phase 3."""

from rocketwright.schema import Design, DispersionResult, Env, SimResult


def simulate(design: Design, env: Env, seed: int | None = None) -> SimResult:
    raise NotImplementedError("water.simulate: implemented in phase 3")


def dispersion(design: Design, env: Env, n: int, seed: int) -> DispersionResult:
    raise NotImplementedError("water.dispersion: implemented in phase 3")
