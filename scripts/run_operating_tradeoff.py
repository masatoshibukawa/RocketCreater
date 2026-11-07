"""Run the temperature, carried mass and initial pressure study on registered airframes."""

import argparse
import json
from pathlib import Path

from rocketwright.agent.design_projects import DesignSpec
from rocketwright.analysis.tradeoff import Study, run

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("spec", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--study", type=Path)
    args = p.parse_args()
    study = (
        Study.model_validate_json(args.study.read_text(encoding="utf-8")) if args.study else Study()
    )
    run(
        DesignSpec.model_validate_json(args.spec.read_text(encoding="utf-8")),
        args.output,
        study=study,
        emit=lambda row: print(json.dumps(row, ensure_ascii=False), flush=True),
    )
