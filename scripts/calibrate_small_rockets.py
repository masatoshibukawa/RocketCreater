#!/usr/bin/env python
"""Calibrate the small-rocket drag / air-impulse constants against the reference flights.

    uv run python scripts/calibrate_small_rockets.py [--tier amateur|bottle]

For every amateur reference entry (rocketwright/catalog/references/amateur.yaml) the solid model
is flown with Cd in CD_GRID (everything else unchanged) and the apogee error per entry per Cd is
printed, plus the Cd that minimises the RMS error over the tier. For the bottle tier the scan is
Cd x AIR_IMPULSE_EFFICIENCY (AIR_GRID). The chosen values become `solid.DEFAULT_CD`,
`water.DEFAULT_CD` and `water.AIR_IMPULSE_EFFICIENCY` only by a human editing the module
constants (CLAUDE.md section 2: every constant keeps its provenance in the README).
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Sequence

from rocketwright.physics import solid, water
from rocketwright.references import ReferenceEntry, load_references
from rocketwright.schema import Tier

CD_GRID: tuple[float, ...] = (0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.0)
AIR_GRID: tuple[float, ...] = (0.0, 0.25, 0.5)


def apogee_error(entry: ReferenceEntry, *, cd: float, air_eff: float | None = None) -> float:
    """(simulated - published) / published apogee for one entry under the given constants."""
    published = entry.published["apogee_m"]
    if entry.tier is Tier.AMATEUR:
        result = solid.simulate(entry.design, entry.env, None, cd=cd)
    else:
        result = water.simulate(
            entry.design, entry.env, None, cd=cd, air_impulse_efficiency=air_eff
        )
    return (result.metrics["apogee_m"] - published) / published


def rms(errors: Sequence[float]) -> float:
    return math.sqrt(sum(e * e for e in errors) / len(errors)) if errors else math.nan


def _print_table(
    entries: list[ReferenceEntry], columns: list[tuple[str, float, float | None]]
) -> None:
    """columns: (label, cd, air_eff). Prints one row per entry and an RMS row."""
    width = max(len(e.id) for e in entries) + 2
    print(f"{'id':<{width}}" + "".join(f"{label:>10}" for label, _, _ in columns))
    table: dict[str, list[float]] = {label: [] for label, _, _ in columns}
    for entry in entries:
        row = []
        for label, cd, air_eff in columns:
            err = apogee_error(entry, cd=cd, air_eff=air_eff)
            table[label].append(err)
            row.append(f"{err:>+9.1%}")
        print(f"{entry.id:<{width}}" + " ".join(row))
    print(f"{'RMS':<{width}}" + " ".join(f"{rms(v):>9.1%}" for v in table.values()))
    best = min(table.items(), key=lambda kv: rms(kv[1]))
    print(f"best (min RMS over {len(entries)} entries): {best[0]} -> RMS {rms(best[1]):.1%}")


def scan_amateur(entries: list[ReferenceEntry]) -> None:
    print(f"== amateur: solid.DEFAULT_CD scan (current {solid.DEFAULT_CD})")
    _print_table(entries, [(f"Cd {cd:g}", cd, None) for cd in CD_GRID])


def scan_bottle(entries: list[ReferenceEntry]) -> None:
    print(
        f"== bottle: water.DEFAULT_CD x AIR_IMPULSE_EFFICIENCY scan "
        f"(current {water.DEFAULT_CD} / {water.AIR_IMPULSE_EFFICIENCY})"
    )
    for air_eff in AIR_GRID:
        print(f"-- AIR_IMPULSE_EFFICIENCY = {air_eff:.2f}")
        _print_table(entries, [(f"Cd {cd:g}", cd, air_eff) for cd in CD_GRID])
    # overall best over the whole grid
    best: tuple[float, float, float] | None = None
    for air_eff in AIR_GRID:
        for cd in CD_GRID:
            r = rms([apogee_error(e, cd=cd, air_eff=air_eff) for e in entries])
            if best is None or r < best[0]:
                best = (r, cd, air_eff)
    assert best is not None
    print(
        f"best over the grid: Cd {best[1]:.1f}, air efficiency {best[2]:.2f} -> RMS {best[0]:.1%}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=("amateur", "bottle"))
    args = parser.parse_args(argv)
    entries = list(load_references())
    amateur = [e for e in entries if e.tier is Tier.AMATEUR]
    bottle = [e for e in entries if e.tier is Tier.BOTTLE]
    if args.tier in (None, "amateur"):
        if not amateur:
            print("no amateur reference entries")
            return 1
        scan_amateur(amateur)
    if args.tier in (None, "bottle"):
        if not bottle:
            print("no bottle reference entries")
            return 1
        if args.tier is None:
            print()
        scan_bottle(bottle)
    return 0


if __name__ == "__main__":
    sys.exit(main())
