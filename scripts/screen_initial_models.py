"""Compare all registered initial airframes with independent, bounded native workers."""

import argparse
import json
from pathlib import Path

from rocketwright.agent.design_projects import DesignSpec
from rocketwright.analysis.seed_survey import run


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("spec", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--workers", type=int, default=2, choices=range(1, 5))
    p.add_argument("--budget-s", type=float, default=1800)
    args = p.parse_args()
    run(
        DesignSpec.model_validate_json(args.spec.read_text(encoding="utf-8")),
        args.output,
        workers=args.workers,
        budget_s=args.budget_s,
        emit=lambda row: print(json.dumps(row, ensure_ascii=False), flush=True),
    )


if __name__ == "__main__":
    main()
