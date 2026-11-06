"""Verify and export the local learned-selector stage 5-7 evidence without host paths."""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis import predictor
from rocketwright.analysis.service import code_hash


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def portable(value):
    if isinstance(value, dict):
        return {k: portable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [portable(v) for v in value]
    if isinstance(value, str) and re.match(r"^[A-Za-z]:[\\/]", value):
        return "local-evidence/" + value.replace("\\", "/").rsplit("/", 1)[-1]
    return value


def verified_tree(root):
    files, cases, manifests = set(), set(), 0
    for path in root.rglob("manifest.json"):
        for name, expected in read(path).items():
            child = (path.parent / name).resolve()
            if (
                not child.is_relative_to(path.parent.resolve())
                or child.is_symlink()
                or not child.is_file()
                or sha(child) != expected
            ):
                raise ValueError(f"Changed native evidence: {path.parent.name}/{name}")
            files.add(child)
            if child.name == "case.json":
                cases.add(child)
        manifests += 1
    if not manifests:
        raise ValueError("No native evidence manifests")
    return dict(manifests=manifests, unique_files=len(files), gpu_cases=len(cases))


def decision_view(state):
    rows = []
    for d in state["adaptive"]["decisions"]:
        choice = d.get("selection_context", {}).get("choices", {}).get(d.get("action"), {})
        if any(not predictor.sealed(r) for r in choice.get("retrieved_outcomes", [])):
            raise ValueError("A selected historical observation changed")
        rows.append(
            dict(
                version=d["version"],
                action=d["action"],
                planner=d["planner"],
                model=d.get("model"),
                reason=d.get("reason"),
                api_requests=d.get("api_requests", []),
                prediction=choice.get("prediction"),
                learned_prediction=choice.get("learned_prediction"),
                retrieved_cases=choice.get("retrieved_cases", []),
                prompt_view=d.get("prompt_view"),
            )
        )
    return rows


def export(root, destination):
    report = read(root / "report.json")
    if report["source_hash"] != code_hash() or report["planner"] != "local_llm":
        raise ValueError("Expected current-source local-model evidence")
    stage7 = read(root / "stage7" / "report.json")
    if len(stage7.get("cases", {})) != 5:
        raise ValueError("All five stage-7 scenarios must finish, including recorded failures")
    stage5 = read(next((root / "stage5" / "projects").glob("*/state.json")))
    stage6 = read(next((root / "stage6" / "projects").glob("*/state.json")))
    output = {
        "source_hash": report["source_hash"],
        "planner": "local_llm",
        "physical_qualification": False,
        "policy_efficiency_improvement_proved": False,
        "evidence": verified_tree(root),
        "report_sha256": sha(root / "report.json"),
        "stage7_report_sha256": sha(root / "stage7" / "report.json"),
        "stage5": {
            **{k: v for k, v in report["stage5"].items() if k not in ("observations", "decisions")},
            "observations": [
                {k: o[k] for k in ("version", "metrics", "spec", "code")}
                for o in report["stage5"]["observations"]
            ],
            "decisions": decision_view(stage5),
            "planner_counts": dict(Counter(d["planner"] for d in stage5["adaptive"]["decisions"])),
        },
        "stage6": read(root / "stage6-summary.json"),
        "stage6_planner_counts": dict(
            Counter(d["planner"] for d in stage6["adaptive"]["decisions"])
        ),
        "stage7": stage7,
        "limits": [
            "Stage 5 demonstrates history use, including an already measured transition; "
            "it is not a held-out policy test",
            "Only the separately reported two geometry evaluations "
            "are held out from predictor training",
            "Model explanations can overstate confidence; only host checks decide acceptance",
            "No Claude API requests, model-weight training, "
            "general policy-efficiency or hardware qualification claim",
        ],
    }
    output = portable(output)
    encoded = json.dumps(output, ensure_ascii=False)
    if re.search(r"[A-Za-z]:\\\\|C:/Users/", encoded):
        raise ValueError("Host path remains in public output")
    write_json(destination, output)
    print(json.dumps({"evidence": output["evidence"], "stage7_passed": stage7["passed"]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    export(args.root, args.destination)


if __name__ == "__main__":
    main()
