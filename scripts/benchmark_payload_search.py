"""GPU-trained payload policies and matched measured GA/DE/NN comparison."""

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import numpy as np

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.schema import Precision
from rocketwright.analysis.seed_survey import _case
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read
from scripts import adaptive_evolution
from scripts.expanded_screening import measure
from scripts.expanded_surrogate import contract
from scripts.gpu_payload_surrogate import Monitor, Predictor, cuda_setup
from scripts.payload_search import (
    CATEGORIES,
    candidate,
    initial,
    loss,
    metrics_vector,
    move,
    observation,
    payload,
    violations,
)

METHODS = ("ga", "de", "ga-nn", "de-nn", "sac", "ppo")
SEEDS = (118213, 119233, 120247)


def train(bundles, method, seed, root, steps):
    from stable_baselines3 import PPO, SAC
    from stable_baselines3.common.callbacks import BaseCallback

    from scripts.payload_rl import PayloadEnvironment

    torch = cuda_setup()
    started = time.monotonic()
    env = PayloadEnvironment(bundles, count=64, horizon=15, seed=seed, record=True)

    class Progress(BaseCallback):
        def _on_step(self):
            if self.num_timesteps % 16384 == 0:
                print(
                    json.dumps(
                        dict(
                            training=method,
                            seed=seed,
                            steps=self.num_timesteps,
                            elapsed_s=time.monotonic() - started,
                        )
                    ),
                    flush=True,
                )
            return True

    common = dict(
        policy="MlpPolicy",
        env=env,
        seed=seed,
        gamma=1,
        learning_rate=0.0003,
        device="cuda",
        verbose=0,
        policy_kwargs=dict(net_arch=[256, 256]),
    )
    if method == "ppo":
        policy = PPO(**common, n_steps=128, batch_size=512, n_epochs=10)
    else:
        policy = SAC(
            **common,
            learning_starts=4096,
            buffer_size=max(131072, steps),
            batch_size=512,
            train_freq=1,
            gradient_steps=1,
            ent_coef="auto_0.02",
        )
    policy.learn(total_timesteps=steps, callback=Progress())
    path = root / f"policy-{method}-{seed}.zip"
    policy.save(path)
    trace = root / f"transitions-{method}-{seed}.npz"
    env.save(trace)
    row = dict(
        method=method,
        training_seed=seed,
        steps=policy.num_timesteps,
        transitions=sum(len(r[2]) for r in env.transitions),
        invalid_transitions=sum(int(r[5].sum()) for r in env.transitions),
        accepted_transitions=sum(int(r[6].sum()) for r in env.transitions),
        elapsed_s=time.monotonic() - started,
        policy_file=path.name,
        policy_sha256=sha(path),
        transitions_file=trace.name,
        transitions_sha256=sha(trace),
        device=str(policy.device),
        surrogate_candidates=env.predictor.candidates,
        gpu_peak_allocated_bytes=torch.cuda.max_memory_allocated(),
    )
    env.close()
    return row


def pareto(rows):
    valid = [
        r
        for r in rows
        if r["status"] == "completed"
        and r["metrics"]["static_margin_cal"] >= 1.12
        and r["metrics"]["conservative_beam_ratio"] <= 0.05
    ]
    front, maximum_payload = [], -1
    for row in sorted(
        valid, key=lambda r: (-r["metrics"]["scenario_height_m"][0], -r["payload_g"])
    ):
        if row["payload_g"] > maximum_payload:
            front.append(row)
            maximum_payload = row["payload_g"]
    return front


def experiment(job):
    folder, method, seed, index, count, generations, policy_file, output, source = job
    bundles = [read(folder / f"context-model-{i}.json") for i in range(3)]
    bundle = bundles[index]
    anchor = DesignSpec.model_validate(bundle["anchor"])
    population = initial(count, seed + index, anchor)
    begin, rows = time.monotonic(), []
    predictor = None
    if method.endswith("-nn"):
        cuda_setup()
        predictor = Predictor(bundles)
    policy = None
    if method in ("sac", "ppo"):
        from stable_baselines3 import PPO, SAC

        cuda_setup()
        policy = (PPO if method == "ppo" else SAC).load(policy_file, device="cuda")
    if code_hash() != source:
        raise ValueError("Changed physics source")
    with output.open("w", encoding="utf-8") as stream:

        def objective(unit):
            row = dict(
                unit=unit.tolist(),
                payload_g=float(payload(unit)),
                status="invalid_geometry",
                screening_attempts=0,
                spec_hash=None,
            )
            value = 1e9
            try:
                spec = candidate(anchor, unit)
                row.update(
                    spec=spec.model_dump(mode="json"),
                    spec_hash=digest(spec.model_dump(mode="json")),
                    payload_g=spec.design.payload_mass_kg * 1000,
                    status="analysis_failed",
                    screening_attempts=1,
                )
                metrics = measure(spec, anchor, bundle["cad"])
                y = metrics_vector(metrics)
                value = float(loss(y, row["payload_g"])[0])
                row.update(
                    status="completed",
                    metrics=metrics,
                    constraint_violation=violations(y)[0].tolist(),
                )
            except (ValueError, RuntimeError) as error:
                row["error"] = str(error)
            row["loss"] = value
            rows.append(row)
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            return value

        def advisor(points):
            y = predictor.predict(points, np.full(len(points), index))
            values = loss(y, payload(points))
            for i, point in enumerate(points):
                try:
                    candidate(anchor, point)
                except ValueError:
                    values[i] = np.nan
            return values

        if policy is None:
            fit = adaptive_evolution.minimize(
                objective,
                population,
                generations=generations,
                seed=seed + 100000,
                method=method.split("-")[0],
                categories=CATEGORIES,
                advisor=advisor if predictor else None,
            )
            history, predicted = fit.history, fit.predicted_candidates
        else:
            rng = np.random.default_rng(seed + 100000)
            for start in population:
                unit, current, incumbent = start.copy(), None, float("inf")
                for step in range(generations + 1):
                    proposed = unit.copy()
                    if step:
                        remaining = (generations + 1 - step) / generations
                        action = (
                            rng.uniform(-1, 1, 12)
                            if current is None
                            else policy.predict(
                                observation(unit, index, metrics_vector(current), remaining),
                                deterministic=True,
                            )[0][0]
                        )
                        proposed = move(unit, action, remaining)
                    value = objective(proposed)
                    if rows[-1]["status"] == "completed" and value < incumbent:
                        unit, current, incumbent = proposed, rows[-1]["metrics"], value
            history, predicted = None, 0
    valid = [r for r in rows if r["status"] == "completed"]
    if len(rows) != count * (generations + 1) or code_hash() != source:
        raise ValueError("Budget/source changed")
    return dict(
        method=method,
        seed=seed,
        anchor=index,
        evaluations=len(rows),
        completed=len(valid),
        screening_attempts=sum(r["screening_attempts"] for r in rows),
        rejected=len(rows) - len(valid),
        unique_specs=len({r["spec_hash"] for r in valid}),
        initial_sha256=digest(population.tolist()),
        best=min(valid, key=lambda r: r["loss"], default=None),
        front=pareto(rows),
        feasible_count=sum(r["loss"] <= 0 for r in valid),
        history=history,
        predicted_candidates=predicted,
        elapsed_s=time.monotonic() - begin,
        data_file=output.name,
        data_sha256=sha(output),
        policy_sha256=sha(policy_file) if policy_file else None,
    )


def run(training, output, *, steps=65536, workers=3):
    import stable_baselines3
    import torch

    cuda_setup()
    output.mkdir(parents=True, exist_ok=False)
    begin, source = time.monotonic(), code_hash()
    training_report = read(training / "report.json")
    if not training_report["source_unchanged"] or training_report["source_hash"] != source:
        raise ValueError("GPU training source differs")
    bundles = []
    for entry in training_report["anchors"]:
        path = training / entry["model_file"]
        b = read(path)
        if (
            sha(path) != entry["model_sha256"]
            or not b["validation_enabled"]
            or b["input_contract"] != contract(source)
        ):
            raise ValueError("Frozen model identity/validation mismatch")
        bundles.append(b)
    paths = [
        Path(__file__).with_name(n)
        for n in (
            "benchmark_payload_search.py",
            "payload_search.py",
            "payload_rl.py",
            "gpu_payload_surrogate.py",
            "adaptive_evolution.py",
            "expanded_screening.py",
        )
    ]
    hashes = {p.name: sha(p) for p in paths}
    report = dict(
        source_hash=source,
        script_hashes=hashes,
        methods=METHODS,
        seeds=SEEDS,
        training_report_sha256=sha(training / "report.json"),
        training=[],
        runs=[],
        results=[],
        population=32,
        generations=15,
        evaluations_per_run=512,
        training_steps=steps,
        payload_range_g=[10, 200],
        altitude_target_m=30,
        static_search_target_cal=1.12,
        beam_search_limit=0.05,
        material_policy="RL material fixed per episode; GA/DE mutable",
        objective="Feasibility first (height, static margin, beam); then maximum payload",
        training_device=torch.cuda.get_device_name(0),
        versions=dict(torch=torch.__version__, sb3=stable_baselines3.__version__),
        hyperparameters=dict(
            envs=64,
            horizon=15,
            net_arch=[256, 256],
            batch_size=512,
            gamma=1,
            learning_rate=0.0003,
            ppo_steps=128,
            ppo_epochs=10,
            sac_train_freq=1,
            sac_gradient_steps=1,
            sac_learning_starts=4096,
            sac_entropy="auto_0.02",
        ),
        physical_qualification=False,
        acceptance_performed=False,
    )
    write_json(output / "plan.json", report)
    monitor = Monitor(output)
    try:
        policies = {}
        for method in ("sac", "ppo"):
            for i, seed in enumerate(SEEDS):
                row = train(bundles, method, 934001 + i, output, steps)
                policies[(method, seed)] = output / row["policy_file"]
                row["evaluation_seed"] = seed
                report["training"].append(row)
                write_json(output / "training-progress.json", report)
                print(json.dumps(row), flush=True)
        write_json(output / "frozen-policies.json", report["training"])
        report["frozen_policies_sha256"] = sha(output / "frozen-policies.json")
        jobs = [
            (
                training,
                method,
                seed,
                i,
                32,
                15,
                policies.get((method, seed)),
                output / f"{method}-{seed}-{i}.jsonl",
                source,
            )
            for seed in SEEDS
            for i in range(3)
            for method in METHODS
        ]
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for row in pool.map(experiment, jobs):
                report["runs"].append(row)
                write_json(output / "progress.json", report)
                print(
                    json.dumps({k: row[k] for k in ("method", "seed", "anchor", "feasible_count")}),
                    flush=True,
                )
        for seed in SEEDS:
            for i in range(3):
                group = [r for r in report["runs"] if r["seed"] == seed and r["anchor"] == i]
                if len(group) != len(METHODS) or len({r["initial_sha256"] for r in group}) != 1:
                    raise ValueError("Unmatched initial populations")
        jobs = []
        for method in METHODS:
            for i in range(3):
                selected = min(
                    (
                        r["best"]
                        for r in report["runs"]
                        if r["method"] == method and r["anchor"] == i and r["best"]
                    ),
                    key=lambda r: r["loss"],
                )
                label = f"{method}-{i}"
                write_json(output / f"selected-{label}.json", selected["spec"])
                jobs.append(
                    (
                        label,
                        DesignSpec.model_validate(selected["spec"]),
                        output / label,
                        source,
                        Precision(),
                        180,
                        time.monotonic() + 2400,
                    )
                )
        with ThreadPoolExecutor(max_workers=2) as pool:
            for row in pool.map(_case, jobs):
                report["results"].append(row)
                write_json(output / "native-progress.json", report)
                print(
                    json.dumps(
                        dict(native=row["label"], status=row["status"], metrics=row.get("metrics"))
                    ),
                    flush=True,
                )
        report.update(
            source_unchanged=source == code_hash()
            and hashes == {p.name: sha(p) for p in paths}
            and report["training_report_sha256"] == sha(training / "report.json"),
            elapsed_s=time.monotonic() - begin,
            matched_evaluations=True,
        )
    finally:
        report["gpu_monitor"] = monitor.stop()
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("training", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--steps", type=int, default=65536)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--cuda-libraries", type=Path, required=True)
    p.add_argument("--rl-libraries", type=Path, required=True)
    a = p.parse_args()
    sys.path.insert(0, str(a.cuda_libraries.resolve()))
    sys.path.append(str(a.rl_libraries.resolve()))
    if a.steps < 8192 or a.steps % 8192 or not 1 <= a.workers <= 4:
        p.error("Use a positive multiple of 8192 transitions and 1–4 workers")
    run(a.training, a.output, steps=a.steps, workers=a.workers)
