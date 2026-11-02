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
    print(f"{'id':<28}{'tier':<12}{'key':<22}{'published':>14}{'simulated':>14}{'error':>9}  ok")
    for entry in entries:
        t0 = time.perf_counter()
        rep = reproduce(entry, tune=not args.no_tune)
        dt = time.perf_counter() - t0
        for key, err in rep.errors_frac.items():
            ok = abs(err) <= rep.tolerance_frac
            bad += not ok
            print(
                f"{entry.id:<28}{entry.tier.value:<12}{key:<22}"
                f"{rep.published[key]:>14,.1f}{rep.simulated[key]:>14,.1f}{err:>+8.1%}  "
                f"{'OK' if ok else 'NG'}"
            )
        flag = "provisional" if entry.provisional else "confirmed"
        status = "pass" if rep.success else f"FAIL: {'; '.join(rep.failure_reasons)}"
        print(f"{'':<28}{flag}, {dt:.1f}s, sim {status}")
    print(f"\n{len(entries)} entries, {bad} metric(s) outside tolerance")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
