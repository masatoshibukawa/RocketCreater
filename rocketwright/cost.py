"""Cost estimation: BOM roll-up for bottle/amateur, mass-based estimate for commercial/heavy.

Implemented in phase 1 (prompt 1B) and refined in phase 3.
"""

from rocketwright.schema import Design


def estimate_cost_jpy(design: Design) -> float:
    raise NotImplementedError("cost.estimate_cost_jpy: implemented in phase 1 (prompt 1B)")
