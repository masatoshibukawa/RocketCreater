"""Audit a source-compatible replay without counting repeated conditions as new evidence."""

import argparse
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis import predictor
from rocketwright.analysis.worker import read
from scripts.report_design_search import verified_files


def export(original, replay, destination):
    old, new = read(original), read(replay)
    if old["protocol_hash"] != new["protocol_hash"]:
        raise ValueError("Replay protocol differs")
    comparisons = []
    for a, b in zip(old["trials"], new["trials"], strict=True):
        if a["split"] != b["split"] or a["spec"] != b["spec"]:
            raise ValueError("Replay conditions differ")
        if not predictor.sealed(a["row"]) or not predictor.sealed(b["row"]):
            raise ValueError("Changed observation evidence")
        if b["row"]["code"] != new["source_hash"]:
            raise ValueError("Replay observation came from another source")
        differences = {
            key: abs(a["row"][key] - b["row"][key]) for key in ("prediction_residual_m",)
        }
        differences["before_apogee_m"] = abs(
            a["row"]["before"]["apogee_m"] - b["row"]["before"]["apogee_m"]
        )
        differences["after_apogee_m"] = abs(
            a["row"]["after"]["apogee_m"] - b["row"]["after"]["apogee_m"]
        )
        comparisons.append(dict(split=b["split"], differences=differences))
    result = dict(
        original_source=old["source_hash"],
        replay_source=new["source_hash"],
        original_report_sha256=sha(original),
        replay_report_sha256=sha(replay),
        replay_protocol_hash=new["protocol_hash"],
        independent_additional_conditions=0,
        repeated_conditions=len(comparisons),
        comparisons=comparisons,
        maximum_altitude_difference_m=max(max(r["differences"].values()) for r in comparisons),
        metrics={
            k: new[k]
            for k in (
                "raw_mae_m",
                "corrected_mae_m",
                "legacy_ridge_mae_m",
                "cost_mae_s",
                "elapsed_s",
            )
        },
        evidence=verified_files(replay.parent),
        training_rows=len(new["training_rows"]),
        evaluation_rows=len(new["audits"]),
        scope="Repeated native protocol on current source; not additional independent validation",
    )
    write_json(destination, result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("original", type=Path)
    p.add_argument("replay", type=Path)
    p.add_argument("destination", type=Path)
    a = p.parse_args()
    print(export(a.original, a.replay, a.destination)["maximum_altitude_difference_m"])
