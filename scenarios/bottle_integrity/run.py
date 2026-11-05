"""Run the integrity pool against a generated assembly packet; no hardware qualification."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rocketwright.physics.bottle_integrity.harness import IntegrityHarness  # noqa: E402
from rocketwright.physics.bottle_integrity.schema import AnalysisConfig  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "packet", type=Path, help="Directory containing design.json and assembly.json"
    )
    parser.add_argument("output", type=Path, help="New, empty output directory")
    parser.add_argument(
        "--solver", type=Path, required=True, help="Installed CalculiX ccx executable"
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument(
        "--evidence", type=Path, help="JSON list with source files relative to its parent"
    )
    parser.add_argument("--cfd-assessment", type=Path)
    args = parser.parse_args()

    def read(p):
        return json.loads(p.read_text(encoding="utf-8"))

    harness = IntegrityHarness(
        read(args.packet / "design.json"),
        read(args.packet / "assembly.json"),
        args.output,
        solver=args.solver.resolve(),
        config=AnalysisConfig(**read(args.config)) if args.config else None,
        evidence_records=read(args.evidence) if args.evidence else [],
        evidence_root=args.evidence.parent if args.evidence else None,
        cfd_assessment=read(args.cfd_assessment) if args.cfd_assessment else None,
    )
    result = harness.run_all(lambda method, status: print(method, status, flush=True))
    print(json.dumps(result["verdict"], ensure_ascii=True, indent=2))
    return bool(result["verdict"]["failed_methods"])


if __name__ == "__main__":
    raise SystemExit(main())
