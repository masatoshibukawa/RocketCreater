"""Reproduce every reference vehicle with our physics and print the error table.

uv run python scripts/check_references.py [--no-tune] [--tier bottle|amateur|commercial|heavy]
"""

from __future__ import annotations

import argparse
import sys
import time

from rocketwright.references import load_references, reproduce
from rocketwright.schema import Tier


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-tune", action="store_true", help="skip pitch tuning (orbital)")
    parser.add_argument("--tier", choices=[t.value for t in Tier])
    args = parser.parse_args()

    entries = [e for e in load_references() if args.tier is None or e.tier.value == args.tier]
    if not entries:
        print("no reference entries found")
        return 1

    bad = 0
    print(
        f"{'id':<28}{'tier':<12}{'key':<22}{'published':>14}{'simulated':>14}{'error':>9}"
        f"{'tol':>6}  ok"
    )
    for entry in entries:
        t0 = time.perf_counter()
        rep = reproduce(entry, tune=not args.no_tune)
        dt = time.perf_counter() - t0
        for key, err in rep.errors_frac.items():
            tol = rep.tolerance_for(key)
            ok = abs(err) <= tol
            bad += not ok
            # masses are printed in grams (kit weights are tens of grams)
            scale, unit = (1e3, " g") if key.endswith("_kg") and rep.published[key] < 1 else (1, "")
            print(
                f"{entry.id:<28}{entry.tier.value:<12}{key:<22}"
                f"{rep.published[key] * scale:>12,.1f}{unit:<2}"
                f"{rep.simulated[key] * scale:>12,.1f}{unit:<2}{err:>+8.1%}{tol:>6.0%}  "
                f"{'OK' if ok else 'NG'}"
            )
        flag = "provisional" if entry.provisional else "confirmed"
        basis = "parts build" if rep.from_build else "geometric design"
        status = "pass" if rep.success else f"FAIL: {'; '.join(rep.failure_reasons)}"
        print(f"{'':<28}{flag}, {basis}, {dt:.1f}s, sim {status}")
    print(f"\n{len(entries)} entries, {bad} metric(s) outside tolerance")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
