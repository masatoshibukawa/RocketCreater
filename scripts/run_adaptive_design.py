"""Run/resume the saved-design loop; local LLM by default, baseline only when requested."""

import argparse
import json
from pathlib import Path

from rocketwright.agent.design_projects import DesignProjects, DesignSpec
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.schema import Precision, SearchLimits
from rocketwright.analysis.service import Harness


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path("output/adaptive-projects"))
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--spec", type=Path)
    source.add_argument("--project")
    p.add_argument("--precision", type=Path)
    p.add_argument("--limits", type=Path)
    p.add_argument("--runtime", type=Path, help="Host-only native solver settings")
    p.add_argument("--steps", type=int, default=200)
    args = p.parse_args()
    store = DesignProjects(args.root.resolve())
    runtime = Runtime.model_validate_json(args.runtime.read_text()) if args.runtime else None
    h = Harness(store, runtime=runtime)
    if args.spec:
        s = store.create(DesignSpec.model_validate_json(args.spec.read_text(encoding="utf-8")))
        precision = (
            Precision.model_validate_json(args.precision.read_text()) if args.precision else None
        )
        limits = SearchLimits.model_validate_json(args.limits.read_text()) if args.limits else None
        s = h.start(s["id"], s["revision"], precision, limits)
    else:
        s = store.get(args.project)
    print(json.dumps(dict(project=s["id"], version=s["version"])), flush=True)
    for _ in range(args.steps):
        s = h.step(s["id"], s["revision"])
        a = s["adaptive"]
        last = a["decisions"][-1] if a["decisions"] else {}
        print(
            json.dumps(
                dict(
                    version=s["version"],
                    status=a["status"],
                    action=last.get("action"),
                    planner=last.get("planner"),
                    remaining_s=round(a["remaining_s"], 2),
                ),
                ensure_ascii=False,
            ),
            flush=True,
        )
        if a["status"] != "running":
            break


if __name__ == "__main__":
    main()
