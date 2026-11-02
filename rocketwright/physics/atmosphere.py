"""US Standard Atmosphere 1976 up to 86 km, exponential extrapolation above.

Implemented in phase 1 (prompt 1A).
"""


def temperature_k(altitude_m: float) -> float:
    raise NotImplementedError("atmosphere.temperature_k: implemented in phase 1 (prompt 1A)")


def pressure_pa(altitude_m: float) -> float:
    raise NotImplementedError("atmosphere.pressure_pa: implemented in phase 1 (prompt 1A)")


def density_kgpm3(altitude_m: float) -> float:
    raise NotImplementedError("atmosphere.density_kgpm3: implemented in phase 1 (prompt 1A)")


def speed_of_sound_mps(altitude_m: float) -> float:
    raise NotImplementedError("atmosphere.speed_of_sound_mps: implemented in phase 1 (prompt 1A)")
