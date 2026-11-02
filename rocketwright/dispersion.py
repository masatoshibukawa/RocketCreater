"""Monte Carlo dispersion runner shared by all physics models (CLAUDE.md section 7).

Implemented in phase 3.
"""

from rocketwright.schema import Design, DispersionResult, Env


def run_dispersion(design: Design, env: Env, n: int, seed: int) -> DispersionResult:
    raise NotImplementedError("dispersion.run_dispersion: implemented in phase 3")
