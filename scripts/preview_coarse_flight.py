"""Propagate a completed coarse CFD table without treating it as a precision-qualified table."""

import argparse
import time
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis import aero_accuracy
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import Worker, read, serial
from rocketwright.physics.flight_loads import TunnelDatabase


def verify_folder(folder):
    manifest = read(folder / "manifest.json")
    for name, expected in manifest.items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha(path) != expected:
            raise ValueError("Changed diagnostic dependency: " + name)
    return len(manifest)


def run(parent, output):
    protocol = read(parent / "protocol.json")
    source = code_hash()
    if protocol["source_hash"] != source:
        raise ValueError("Coarse preview requires unchanged source")
    dependencies = ("geometry", "thermal", "propulsion", "screen", "cfd_coarse")
    artifacts = {m: str((parent / m / "data.json").resolve()) for m in dependencies}
    hashes = {m: sha(Path(p)) for m, p in artifacts.items()}
    manifests = {m: sha(parent / m / "manifest.json") for m in dependencies}
    verified_files = sum(verify_folder(parent / m) for m in dependencies)
    output.mkdir(parents=True, exist_ok=False)
    context = dict(
        spec=protocol["spec"],
        precision=protocol["precision"],
        runtime=protocol["runtime"],
        artifacts=artifacts,
        timeout_s=300,
    )
    write_json(output / "input.json", context)
    worker = Worker(context, output)
    worker.setup()
    coarse = read(Path(artifacts["cfd_coarse"]))
    table = TunnelDatabase(coarse["table_folder"])
    begin = time.monotonic()
    # The public aero_model hook selects the actual coarse table. No fine-result alias.
    flight = worker.trajectory(aero_model=table)
    envelope = aero_accuracy.fin_envelope(table, flight)
    write_json(output / "flight.json", serial(flight))
    result = dict(
        source_hash=source,
        protocol_sha256=sha(parent / "protocol.json"),
        spec=protocol["spec"],
        input_hashes=hashes,
        dependency_manifests=manifests,
        verified_dependency_files=verified_files,
        source_unchanged=code_hash() == source
        and hashes == {m: sha(Path(p)) for m, p in artifacts.items()}
        and manifests == {m: sha(parent / m / "manifest.json") for m in dependencies},
        fidelity="coarse CFD only; grid/time/holdout precision checks pending",
        cells=coarse["cells"],
        width_d=protocol["runtime"]["cfd_width"],
        apogee_m=flight["apogee_m"],
        incidence_deg=flight["ascent_incidence_deg"],
        maximum_q_pa=flight["max_q_pa"],
        domain_pass=flight["aero_domain_pass"],
        concurrent_fin_envelope=serial(envelope),
        max_abs_fin_normal_force_n=max(abs(c["local_resultant"][2]) for c in envelope),
        analytic_envelope_fin_force_n=worker.fin_force(),
        flight_sha256=sha(output / "flight.json"),
        elapsed_s=time.monotonic() - begin,
        physical_qualification=False,
        precision_checked=False,
        acceptance_performed=False,
    )
    write_json(output / "report.json", result)
    write_json(
        output / "manifest.json",
        {p.relative_to(output).as_posix(): sha(p) for p in output.rglob("*") if p.is_file()},
    )
    print(
        {
            k: result[k]
            for k in (
                "apogee_m",
                "incidence_deg",
                "max_abs_fin_normal_force_n",
                "analytic_envelope_fin_force_n",
            )
        },
        flush=True,
    )
    return result


def export(search, old, new, destination):
    search_report = read(search / "report.json")
    rows = []
    for method, folder in (("wide-old", old), ("wide-new", new)):
        verified = verify_folder(folder)
        result = read(folder / "report.json")
        label = search_report["detailed_candidates"][method]
        selected = next(r for r in search_report["results"] if r["label"] == label)
        if (
            result["spec"] != selected["spec"]
            or result["source_hash"] != search_report["source_hash"]
            or not result["source_unchanged"]
        ):
            raise ValueError("Preview differs from fixed finalist/source")
        rows.append(dict(method=method, verified_files=verified, **result))
    write_json(destination, dict(methods=rows, physical_qualification=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("parent", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    run(a.parent, a.output)
