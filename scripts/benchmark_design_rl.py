"""Frozen-surrogate PPO/SAC training followed by matched real-simulator evaluation."""

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import numpy as np

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.design_space import samples
from rocketwright.analysis.schema import Precision
from rocketwright.analysis.seed_survey import _case
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read
from scripts.benchmark_evolution import SEEDS
from scripts.mixed_genetic import canonical
from scripts.search_joint_designs import proposal

METHODS = ("ppo", "sac", "random-local")


def evaluate_policy(job):
    import torch
    from stable_baselines3 import PPO, SAC

    from scripts.design_rl import move, observation

    model, method, seed, anchor_id, policy_file, destination, source = job
    torch.set_num_threads(1)
    begin = time.monotonic()
    policy = None
    if method != "random-local":
        policy = (PPO if method == "ppo" else SAC).load(policy_file, device="cpu")
    anchor = DesignSpec.model_validate(model["anchor"])
    categories = {int(k): v for k, v in model["categories"].items()}
    initial = canonical(samples(32, seed + anchor_id), categories)
    rng, rows = np.random.default_rng(seed + 100000), []
    with destination.open("w", encoding="utf-8") as stream:
        for episode, start in enumerate(initial):
            unit, current = start.copy(), None
            for step in range(11):
                if step:
                    if current is None:
                        action = rng.uniform(-1, 1, 11)
                    else:
                        obs = observation(unit, anchor_id, current, (11 - step) / 10)
                        action = (
                            rng.uniform(-1, 1, 11)
                            if policy is None
                            else policy.predict(obs, deterministic=True)[0]
                        )
                    unit = move(unit, action)
                row, value = proposal(unit, anchor, model["cad"], "initial")
                row.update(loss=value, episode=episode, step=step)
                rows.append(row)
                current = row.get("metrics")
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    if code_hash() != source:
        raise ValueError("Physics changed during policy evaluation")
    valid = [r for r in rows if r["status"] == "completed"]
    best = min(valid, key=lambda r: r["loss"])
    stable = [r for r in valid if r["metrics"]["static_margin_cal"] >= 1]
    high = max(stable, key=lambda r: r["metrics"]["scenario_height_m"][0], default=None)
    return dict(
        method=method,
        seed=seed,
        anchor=anchor_id,
        evaluations=len(rows),
        expected_evaluations=352,
        initial_sha256=digest(initial.tolist()),
        best_loss=best["loss"],
        best=best,
        best_stable_screen_height_m=high["metrics"]["scenario_height_m"][0] if high else None,
        rejected=len(rows) - len(valid),
        unique_specs=len({r["spec_hash"] for r in valid}),
        predicted_candidates=0,
        elapsed_s=time.monotonic() - begin,
        data_file=destination.name,
        data_sha256=sha(destination),
        policy_sha256=sha(policy_file) if policy_file else None,
    )


def run(training, baseline, output, *, steps=16384, workers=3):
    import gymnasium
    import stable_baselines3
    import torch
    from stable_baselines3 import PPO, SAC
    from stable_baselines3.common.env_checker import check_env

    from scripts.design_rl import DesignEnvironment

    output.mkdir(parents=True, exist_ok=False)
    begin, source = time.monotonic(), code_hash()
    torch.set_num_threads(1)
    tr, base = read(training / "report.json"), read(baseline / "report.json")
    if (
        not tr["source_unchanged"]
        or tr["source_hash"] != source
        or not base["source_unchanged"]
        or base["source_hash"] != source
        or base["training_report_sha256"] != sha(training / "report.json")
    ):
        raise ValueError("Frozen training and baseline source do not match")
    models = []
    for i, row in enumerate(tr["anchors"]):
        path = training / f"model-{i}.json"
        if sha(path) != row["model_sha256"]:
            raise ValueError("Changed surrogate")
        model = read(path)
        if not model["validation_enabled"]:
            raise ValueError("A surrogate did not pass its independent validation gate")
        models.append(model)
    paths = [
        Path(__file__),
        Path(__file__).with_name("design_rl.py"),
        Path(__file__).with_name("search_joint_designs.py"),
        Path(__file__).with_name("search_surrogate.py"),
    ]
    hashes = {p.name: sha(p) for p in paths}
    report = dict(
        source_hash=source,
        script_hashes=hashes,
        methods=METHODS,
        seeds=SEEDS,
        baseline_report_sha256=sha(baseline / "report.json"),
        training_report_sha256=sha(training / "report.json"),
        training_steps_per_policy=steps,
        training=[],
        runs=[],
        results=[],
        population_size=32,
        generations=10,
        versions=dict(
            torch=torch.__version__,
            stable_baselines3=stable_baselines3.__version__,
            gymnasium=gymnasium.__version__,
            numpy=np.__version__,
        ),
        material_policy="host initial population; fixed within each 10-step episode",
        state_fidelity_train="frozen surrogate",
        state_fidelity_test="axial simulator",
        physics_evaluation_budget_per_anchor_seed=352,
        physical_qualification=False,
        acceptance_performed=False,
    )
    write_json(output / "plan.json", report)
    check_env(DesignEnvironment(models), warn=True)
    policies = {}
    for method in ("ppo", "sac"):
        for index, seed in enumerate(SEEDS):
            started = time.monotonic()
            env = DesignEnvironment(models, record=True)
            common = dict(
                policy="MlpPolicy",
                env=env,
                seed=70001 + index,
                gamma=1.0,
                learning_rate=0.0003,
                device="cpu",
                verbose=0,
                policy_kwargs=dict(net_arch=[64, 64]),
            )
            if method == "ppo":
                policy = PPO(**common, n_steps=256, batch_size=128, n_epochs=10)
            else:
                policy = SAC(
                    **common,
                    learning_starts=512,
                    buffer_size=max(20000, steps),
                    batch_size=128,
                    train_freq=4,
                    gradient_steps=1,
                    ent_coef="auto_0.1",
                )
            policy.learn(total_timesteps=steps)
            path = output / f"policy-{method}-{seed}.zip"
            policy.save(path)
            trace = output / f"transitions-{method}-{seed}.npz"
            env.save_transitions(trace)
            entry = dict(
                method=method,
                evaluation_seed=seed,
                training_seed=70001 + index,
                transitions=len(env.transitions),
                fidelity="surrogate",
                invalid_transitions=sum(r[5] for r in env.transitions),
                elapsed_s=time.monotonic() - started,
                policy_file=path.name,
                policy_sha256=sha(path),
                transitions_file=trace.name,
                transitions_sha256=sha(trace),
            )
            report["training"].append(entry)
            policies[(method, seed)] = path
            write_json(output / "training-progress.json", report)
            print(json.dumps(entry), flush=True)
            env.close()
    jobs = [
        (
            model,
            method,
            seed,
            anchor_id,
            policies.get((method, seed)),
            output / f"{method}-{seed}-{anchor_id}.jsonl",
            source,
        )
        for seed in SEEDS
        for anchor_id, model in enumerate(models)
        for method in METHODS
    ]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(evaluate_policy, jobs):
            counterpart = next(
                r
                for r in base["runs"]
                if r["method"] == "de-nn"
                and r["seed"] == row["seed"]
                and r["anchor"] == row["anchor"]
            )
            if (
                row["evaluations"] != counterpart["evaluations"]
                or row["initial_sha256"] != counterpart["initial_sha256"]
            ):
                raise ValueError("Simulator budget or initial designs differ from baseline")
            report["runs"].append(row)
            write_json(output / "progress.json", report)
            print(
                json.dumps(
                    {
                        k: row[k]
                        for k in (
                            "method",
                            "seed",
                            "anchor",
                            "best_loss",
                            "best_stable_screen_height_m",
                        )
                    }
                ),
                flush=True,
            )
    jobs = []
    for method in METHODS:
        for anchor_id in range(3):
            row = min(
                (r for r in report["runs"] if r["method"] == method and r["anchor"] == anchor_id),
                key=lambda r: r["best_loss"],
            )
            label = f"{method}-{anchor_id}"
            jobs.append(
                (
                    label,
                    DesignSpec.model_validate(row["best"]["spec"]),
                    output / label,
                    source,
                    Precision(),
                    180,
                    time.monotonic() + 1800,
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
        source_unchanged=code_hash() == source and hashes == {p.name: sha(p) for p in paths},
        elapsed_s=time.monotonic() - begin,
        matched_evaluations=True,
        matched_initial_populations=True,
    )
    write_json(output / "report.json", report)
    if not report["source_unchanged"]:
        raise ValueError("Implementation changed during benchmark")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("training", type=Path)
    p.add_argument("baseline", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--steps", type=int, default=16384)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--rl-libraries", type=Path)
    a = p.parse_args()
    if a.rl_libraries:
        sys.path.append(str(a.rl_libraries.resolve()))
    if a.steps < 512 or a.steps % 256 or not 1 <= a.workers <= 4:
        p.error("Use steps >=512 divisible by 256 and 1–4 workers")
    run(a.training, a.baseline, a.output, steps=a.steps, workers=a.workers)
