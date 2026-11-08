"""Multi-start adaptive search. Keeps the final precision and mission requirements fixed."""

import argparse
import json
from pathlib import Path

from rocketwright.agent.design_projects import DesignSpec
from rocketwright.analysis.portfolio import run
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.schema import Precision, SearchLimits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--limits", type=Path)
    parser.add_argument("--precision", type=Path)
    parser.add_argument("--max-starts", type=int, help="Default: all registered starts")
    args = parser.parse_args()

    def read(cls, path):
        return cls.model_validate_json(path.read_text(encoding="utf-8")) if path else cls()

    run(
        read(DesignSpec, args.spec),
        args.output,
        runtime=read(Runtime, args.runtime),
        limits=read(SearchLimits, args.limits),
        precision=read(Precision, args.precision),
        max_starts=args.max_starts,
        emit=lambda row: print(json.dumps(row, ensure_ascii=False), flush=True),
    )


if __name__ == "__main__":
    main()
