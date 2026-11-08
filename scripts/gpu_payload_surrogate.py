"""CUDA FP32 refinement of verified ensembles; selection never sees test labels."""

import argparse
import copy
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read
from scripts.expanded_design_data import CATEGORIES, FAMILIES, from_original
from scripts.expanded_surrogate import contract, predict, transform
from scripts.search_surrogate import features, targets
from scripts.train_expanded_surrogate import arrays, scores


def cuda_setup():
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA execution required; no silent CPU fallback")
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision("highest")
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    return torch


class Monitor:
    def __init__(self, folder):
        self.path = folder / "gpu.csv"
        self.stream = self.path.open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            [
                "nvidia-smi",
                "--query-gpu=timestamp,utilization.gpu,memory.used,power.draw,temperature.gpu",
                "--format=csv,noheader,nounits",
                "-lms",
                "1000",
            ],
            stdout=self.stream,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def stop(self):
        self.process.terminate()
        self.process.wait(timeout=10)
        self.stream.close()
        values = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                values.append([float(v.strip()) for v in line.split(",")[1:]])
            except ValueError:
                continue
        return dict(
            samples=len(values),
            maximum=np.max(values, axis=0).tolist() if values else None,
            mean=np.mean(values, axis=0).tolist() if values else None,
            columns=["gpu_percent", "memory_mib", "power_w", "temperature_c"],
            scope="Whole-device samples, possibly including other processes",
            log_sha256=sha(self.path),
        )


def network(bundle, device="cuda"):
    import torch
    from torch import nn

    class Ensemble(nn.Module):
        def __init__(self):
            super().__init__()
            members = bundle["members"]
            for field in ("x_mean", "x_scale", "y_mean", "y_scale"):
                self.register_buffer(
                    field, torch.tensor([m[field] for m in members], dtype=torch.float32)
                )
            self.weights = nn.ParameterList(
                [
                    nn.Parameter(
                        torch.tensor([m["weights"][j] for m in members], dtype=torch.float32)
                    )
                    for j in range(len(members[0]["weights"]))
                ]
            )
            self.biases = nn.ParameterList(
                [
                    nn.Parameter(
                        torch.tensor([m["biases"][j] for m in members], dtype=torch.float32)
                    )
                    for j in range(len(members[0]["biases"]))
                ]
            )

        def forward(self, x):
            x = (x[None] - self.x_mean[:, None]) / self.x_scale[:, None]
            for j, (w, b) in enumerate(zip(self.weights, self.biases, strict=True)):
                x = torch.bmm(x, w) + b[:, None]
                if j + 1 < len(self.weights):
                    x = torch.relu(x)
            return x * self.y_scale[:, None] + self.y_mean[:, None]

        def physical(self, x):
            y = self(x)
            return torch.stack(
                (
                    torch.expm1(y[..., 0]).clamp_min(0),
                    torch.sinh(y[..., 1]),
                    torch.expm1(y[..., 2]).clamp_min(0),
                ),
                -1,
            ).mean(0)

    return Ensemble().to(device)


class Predictor:
    def __init__(self, bundles, device="cuda"):
        import torch

        self.torch, self.device = torch, device
        self.models = [network(b, device).eval() for b in bundles]
        self.anchors = [DesignSpec.model_validate(b["anchor"]) for b in bundles]
        self.calls, self.candidates = 0, 0

    def predict(self, points, anchor_ids):
        from scripts.payload_search import expanded

        points, ids = np.atleast_2d(points), np.atleast_1d(anchor_ids)
        result = np.empty((len(points), 3))
        with self.torch.no_grad():
            for i in range(3):
                mask = ids == i
                if not mask.any():
                    continue
                x = features(expanded(points[mask], self.anchors[i]), CATEGORIES)
                result[mask] = (
                    self.models[i]
                    .physical(self.torch.as_tensor(x, dtype=self.torch.float32, device=self.device))
                    .cpu()
                    .numpy()
                )
        if not np.isfinite(result).all():
            raise ValueError("Nonfinite GPU surrogate outcome")
        self.calls += 1
        self.candidates += len(points)
        return result


def load_data(data, history, original, index):
    dr, hr, old_report = [read(p / "report.json") for p in (data, history, original)]
    source = code_hash()
    if any(not r["source_unchanged"] or r["source_hash"] != source for r in (dr, hr, old_report)):
        raise ValueError("Data/model physics identity differs")
    paths = [
        data / f"examples-{index}.jsonl",
        history / f"examples-{index}.jsonl",
        original / old_report["anchors"][index]["model_file"],
    ]
    expected = [
        dr["anchors"][index]["examples_sha256"],
        hr["anchors"][index]["examples_sha256"],
        old_report["anchors"][index]["model_sha256"],
    ]
    if any(sha(p) != h for p, h in zip(paths, expected, strict=True)):
        raise ValueError("Training input changed")
    bundle = read(paths[2])
    if bundle["input_contract"] != contract(source):
        raise ValueError("Input domain contract changed")
    fresh = [
        r
        for r in map(json.loads, paths[0].read_text(encoding="utf-8").splitlines())
        if r["status"] == "completed"
    ]
    historical = [
        r
        for r in map(json.loads, paths[1].read_text(encoding="utf-8").splitlines())
        if r["split"] == "train"
    ]
    groups = {
        split: [r for r in fresh if r["split"] == split]
        for split in ("train", "validation", "test")
    }
    reserved = {r["spec_hash"] for s in ("validation", "test") for r in groups[s]}
    if reserved & {r["spec_hash"] for r in historical + groups["train"]}:
        raise ValueError("Train/evaluation leakage")
    if {r["spec_hash"] for r in groups["validation"]} & {r["spec_hash"] for r in groups["test"]}:
        raise ValueError("Validation/test leakage")
    old_x = from_original(
        np.array([r["unit"] for r in historical]), DesignSpec.model_validate(bundle["anchor"])
    )
    old_y = np.array([targets(r["metrics"]) for r in historical])
    x, y = arrays(groups["train"])
    return (
        bundle,
        np.r_[old_x, x],
        np.r_[old_y, y],
        groups,
        dict(zip((p.name for p in paths), expected, strict=True)),
    )


def refine(bundle, x, y, vx, vy, *, epochs=500, batch=2048):
    torch = cuda_setup()
    torch.manual_seed(512071)
    model = network(bundle)
    tx, ty, val_x, val_y = [
        torch.as_tensor(a, dtype=torch.float32, device="cuda")
        for a in (features(x, CATEGORIES), transform(y), features(vx, CATEGORIES), transform(vy))
    ]
    opt = torch.optim.AdamW(model.parameters(), lr=0.0003, weight_decay=1e-5)
    best = copy.deepcopy(model.state_dict())
    best_epochs = np.zeros(len(bundle["members"]), int)
    with torch.no_grad():
        best_loss = (((model(val_x) - val_y[None]) / model.y_scale[:, None]) ** 2).mean((1, 2))
    baseline = best_loss.cpu().tolist()
    history = []
    for epoch in range(1, epochs + 1):
        model.train()
        order = torch.randperm(len(tx), device="cuda")
        for indices in order.split(batch):
            opt.zero_grad(set_to_none=True)
            error = ((model(tx[indices]) - ty[indices][None]) / model.y_scale[:, None]) ** 2
            error.mean((1, 2)).sum().backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5)
            opt.step()
        if epoch % 5:
            continue
        model.eval()
        with torch.no_grad():
            value = (((model(val_x) - val_y[None]) / model.y_scale[:, None]) ** 2).mean((1, 2))
        improved = value < best_loss - 1e-7
        for key, tensor in model.state_dict().items():
            best[key][improved] = tensor[improved]
        best_loss = torch.minimum(best_loss, value)
        best_epochs[improved.cpu().numpy()] = epoch
        if epoch % 50 == 0:
            row = dict(
                epoch=epoch, validation_mse=value.cpu().tolist(), best_mse=best_loss.cpu().tolist()
            )
            history.append(row)
            print(json.dumps(row), flush=True)
        if epoch - best_epochs.max() >= 75:
            break
    model.load_state_dict(best)
    result = copy.deepcopy(bundle)
    for i, member in enumerate(result["members"]):
        member.update(
            weights=[p[i].detach().cpu().tolist() for p in model.weights],
            biases=[p[i].detach().cpu().tolist() for p in model.biases],
            gpu_refinement_epoch=int(best_epochs[i]),
        )
    return result, dict(
        epochs=epoch,
        selected_epochs=best_epochs.tolist(),
        initial_mse=baseline,
        best_mse=best_loss.cpu().tolist(),
        history=history,
    )


def run(data, history, original, output, *, epochs=500):
    torch = cuda_setup()
    output.mkdir(parents=True, exist_ok=False)
    start, source = time.monotonic(), code_hash()
    monitor = Monitor(output)
    paths = [Path(__file__), Path(__file__).with_name("payload_search.py")]
    hashes = {p.name: sha(p) for p in paths}
    report = dict(
        source_hash=source,
        script_hashes=hashes,
        input_contract=contract(source),
        device=torch.cuda.get_device_name(0),
        torch_version=torch.__version__,
        cuda_version=torch.version.cuda,
        dtype="float32",
        tf32=False,
        amp=False,
        epochs_limit=epochs,
        batch_size=2048,
        anchors=[],
        tests=[],
        physical_qualification=False,
    )
    write_json(output / "plan.json", report)
    pending = []
    try:
        for i in range(3):
            bundle, x, y, groups, inputs = load_data(data, history, original, i)
            vx, vy = arrays(groups["validation"])
            begin = time.monotonic()
            trained, training = refine(bundle, x, y, vx, vy, epochs=epochs)
            before, after = predict(bundle, vx, hybrid=False), predict(trained, vx, hybrid=False)
            old_mae, new_mae = np.abs(before - vy).mean(0), np.abs(after - vy).mean(0)
            family = {}
            for f in FAMILIES:
                mask = np.array([r["distribution"] == f for r in groups["validation"]])
                family[f] = dict(
                    before=np.abs(before[mask] - vy[mask]).mean(0).tolist(),
                    after=np.abs(after[mask] - vy[mask]).mean(0).tolist(),
                )
            improved = bool(
                np.all(new_mae <= old_mae)
                and all(
                    np.all(np.array(v["after"]) <= np.array(v["before"]) * 1.1)
                    for v in family.values()
                )
            )
            selected = trained if improved else bundle
            path = output / f"context-model-{i}.json"
            write_json(path, selected)
            entry = dict(
                anchor=i,
                input_hashes=inputs,
                train_count=len(x),
                validation_count=len(vx),
                model_file=path.name,
                model_sha256=sha(path),
                cuda_model_selected=improved,
                selection="All 3 validation MAEs nonworse; no family over 10% worse",
                validation_before=old_mae.tolist(),
                validation_after=new_mae.tolist(),
                by_family=family,
                training=training,
                elapsed_s=time.monotonic() - begin,
            )
            report["anchors"].append(entry)
            pending.append((groups["test"], bundle, selected))
            write_json(output / "progress.json", report)
            print(json.dumps(entry), flush=True)
        write_json(output / "frozen-models.json", report["anchors"])
        report["frozen_models_sha256"] = sha(output / "frozen-models.json")
        for i, (rows, before, selected) in enumerate(pending):
            x, y = arrays(rows)
            prediction = predict(selected, x, hybrid=False)
            model = network(selected).eval()
            with torch.no_grad():
                gpu = (
                    model.physical(
                        torch.tensor(features(x, CATEGORIES), dtype=torch.float32, device="cuda")
                    )
                    .cpu()
                    .numpy()
                )
            np.testing.assert_allclose(gpu, prediction, rtol=1e-4, atol=2e-4)
            report["tests"].append(
                dict(
                    anchor=i,
                    before=scores(y, predict(before, x, hybrid=False)),
                    selected=scores(y, prediction),
                    gpu_cpu_max_absolute_difference=np.max(abs(gpu - prediction), axis=0).tolist(),
                )
            )
        report.update(
            source_unchanged=source == code_hash() and hashes == {p.name: sha(p) for p in paths},
            elapsed_s=time.monotonic() - start,
            gpu_peak_allocated_bytes=torch.cuda.max_memory_allocated(),
        )
    finally:
        report["gpu_monitor"] = monitor.stop()
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for field in ("data", "history", "original", "output"):
        p.add_argument(field, type=Path)
    p.add_argument("--cuda-libraries", type=Path, required=True)
    p.add_argument("--rl-libraries", type=Path, required=True)
    p.add_argument("--epochs", type=int, default=500)
    a = p.parse_args()
    sys.path.insert(0, str(a.cuda_libraries.resolve()))
    sys.path.append(str(a.rl_libraries.resolve()))
    run(a.data, a.history, a.original, a.output, epochs=a.epochs)
