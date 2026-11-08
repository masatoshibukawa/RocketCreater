"""Matched CPU/CUDA training-kernel timing; not an end-to-end search speedup."""

import argparse
import sys
import time
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import sha, write_json
from scripts.expanded_design_data import CATEGORIES
from scripts.expanded_surrogate import transform
from scripts.gpu_payload_surrogate import cuda_setup, load_data, network
from scripts.search_surrogate import features


def run(data, history, original, output):
    torch = cuda_setup()
    bundle, x, y, _, hashes = load_data(data, history, original, 0)
    x, y = features(x[:2048], CATEGORIES), transform(y[:2048])
    rows, final = [], {}
    for repeat in range(3):
        for device in ("cpu", "cuda") if repeat % 2 == 0 else ("cuda", "cpu"):
            torch.set_num_threads(8 if device == "cpu" else 1)
            model = network(bundle, device)
            tx, ty = [torch.tensor(a, dtype=torch.float32, device=device) for a in (x, y)]
            opt = torch.optim.AdamW(model.parameters(), lr=0.0003, weight_decay=1e-5)

            def step(opt=opt, model=model, tx=tx, ty=ty):
                opt.zero_grad(set_to_none=True)
                (((model(tx) - ty[None]) / model.y_scale[:, None]) ** 2).mean(
                    (1, 2)
                ).sum().backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 5)
                opt.step()

            for _ in range(5):
                step()
            if device == "cuda":
                torch.cuda.synchronize()
            start = time.perf_counter()
            for _ in range(100):
                step()
            if device == "cuda":
                torch.cuda.synchronize()
            elapsed = time.perf_counter() - start
            with torch.no_grad():
                final[device] = model(tx).cpu().numpy()
            rows.append(
                dict(
                    repeat=repeat,
                    device=device,
                    cpu_threads=torch.get_num_threads(),
                    seconds=elapsed,
                )
            )
    difference = np.abs(final["cpu"] - final["cuda"])
    cpu = np.median([r["seconds"] for r in rows if r["device"] == "cpu"])
    gpu = np.median([r["seconds"] for r in rows if r["device"] == "cuda"])
    result = dict(
        input_hashes=hashes,
        steps=100,
        warmup_steps=5,
        batch_size=2048,
        ensemble_members=3,
        device=torch.cuda.get_device_name(0),
        dtype="float32",
        trials=rows,
        cpu_median_s=float(cpu),
        gpu_median_s=float(gpu),
        kernel_speedup=float(cpu / gpu),
        transformed_prediction_max_difference=float(difference.max()),
        transformed_prediction_mean_difference=float(difference.mean()),
        scope=(
            "Same warm-start network/batch/optimizer; forward/backward/update only, "
            "excludes I/O and whole training/search"
        ),
        source_model_sha256=hashes["baseline_model"],
        script_sha256=sha(Path(__file__)),
    )
    write_json(output, result)
    print(result, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("data", "history", "original", "output"):
        p.add_argument(name, type=Path)
    p.add_argument("--cuda-libraries", type=Path, required=True)
    p.add_argument("--rl-libraries", type=Path, required=True)
    a = p.parse_args()
    sys.path.insert(0, str(a.cuda_libraries.resolve()))
    sys.path.append(str(a.rl_libraries.resolve()))
    run(a.data, a.history, a.original, a.output)
