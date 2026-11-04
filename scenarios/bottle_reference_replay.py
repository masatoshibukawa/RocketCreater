"""Reproduce the R14 altitude cross-check: python -m scenarios.bottle_reference_replay."""

from rocketwright.physics.water import run_flight
from rocketwright.schema import BottleDesign, Env

# Fischer et al. (2020), sections 8–10, https://arxiv.org/pdf/2001.08828
# Measured Table 2 rows 1–4. Not the authors' model outputs in Table 3.
OBSERVATIONS = [
    (0.350, 350_000, 17.5),
    (0.325, 350_000, 17.1),
    (0.255, 300_000, 14.1),
    (0.255, 350_000, 17.4),
]


def main():
    errors = []
    for run, (fill, absolute_pa, observed) in enumerate(OBSERVATIONS, 1):
        design = BottleDesign(
            bottle_volume_m3=0.001,
            water_fill_frac=fill,
            initial_gauge_pressure_pa=absolute_pa - 100_000,
            nozzle_diameter_m=0.009,
            dry_mass_kg=0.143,
            has_fins=True,
        )
        # Still air and the model's default rail, diameter law and drag coefficient.
        height = run_flight(design, Env()).apogee_m
        errors.append(abs(height - observed))
        print(f"run {run}: measured {observed:.1f} m, predicted {height:.2f} m")
    print(f"mean absolute error: {sum(errors) / len(errors):.2f} m")


if __name__ == "__main__":
    main()
