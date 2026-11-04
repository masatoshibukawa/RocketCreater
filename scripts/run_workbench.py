"""Reproduce the human-checkpoint workflow and optionally render its two videos."""

import argparse
import json
import os
from pathlib import Path

from rocketwright.agent.production import plan_video, render_video, submit_wan
from rocketwright.agent.workbench import ROOT, StepChoice, Workbench


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--wan", action="store_true")
    parser.add_argument("--local-direction", action="store_true")
    parser.add_argument("--media-root", type=Path)
    args = parser.parse_args()
    if args.media_root:
        os.environ["ROCKETWRIGHT_MEDIA_ROOT"] = str(args.media_root.resolve())
    bench = Workbench()
    state = bench.create()
    print("Project:", state["id"], flush=True)
    for row in json.loads((ROOT / "scenarios/bottle_prototype_choices.json").read_text()):
        state = bench.step(state["id"], state["revision"], StepChoice(**row))
        print("Completed:", row["id"], flush=True)
    state = bench.export(state["id"], state["revision"])
    state = plan_video(bench, state["id"], state["revision"], local=args.local_direction)
    if args.render:
        print("Rendering the confirmed design and simulation trace", flush=True)
        state = render_video(bench, state["id"], state["revision"])
    if args.wan:
        state = submit_wan(bench, state["id"], state["revision"])
    (ROOT / "output/latest-workbench.json").write_text(
        json.dumps(
            {
                "project_id": state["id"],
                "revision": state["revision"],
                "files": state["files"],
                "video_plan": state.get("video_plan"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"id": state["id"], "files": len(state["files"]), "video": state.get("video_plan")},
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
