"""Frozen v1/v2 policies and DE+NN on fresh, matched simulator test seeds."""

import argparse
import json
import shutil
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
from scripts.benchmark_design_rl import evaluate_policy
from scripts.benchmark_evolution import experiment
from scripts.mixed_genetic import canonical
from scripts.search_joint_designs import proposal

SEEDS = (14291, 22639, 37117)
METHODS = ("ppo-v1", "sac-v1", "ppo-v2", "sac-v2", "de-nn-v2")


def evaluate_refined(job):
    import torch
    from stable_baselines3 import PPO, SAC

    from scripts.design_rl import move, observation
    from scripts.refined_design_rl import step_size

    model, method, seed, anchor_id, policy_file, destination, source = job
    torch.set_num_threads(1)
    if method == "de-nn-v2":
        row = experiment((model, "de-nn", seed, anchor_id, 32, 10, destination, source))
        row["method"] = method
        return row
    if method.endswith("v1"):
        row = evaluate_policy(
            (model, method[:3], seed, anchor_id, policy_file, destination, source)
        )
        row["method"] = method
        return row
    begin = time.monotonic()
    policy = (PPO if method.startswith("ppo") else SAC).load(policy_file, device="cpu")
    anchor = DesignSpec.model_validate(model["anchor"])
    category = {int(k): v for k, v in model["categories"].items()}
    initial = canonical(samples(32, seed + anchor_id), category)
    rng, rows = np.random.default_rng(seed + 100000), []
    with destination.open("w", encoding="utf-8") as stream:
        for episode, start in enumerate(initial):
            unit, current, incumbent_loss = start.copy(), None, float("inf")
            for step in range(11):
                proposed = unit.copy()
                if step:
                    remaining = (11 - step) / 10
                    action = (
                        rng.uniform(-1, 1, 11)
                        if current is None
                        else policy.predict(
                            observation(unit, anchor_id, current, remaining), deterministic=True
                        )[0]
                    )
                    proposed = move(unit, action, step_size(remaining))
                row, value = proposal(proposed, anchor, model["cad"], "initial")
                accepted = row["status"] == "completed" and value < incumbent_loss
                if accepted:
                    unit, current, incumbent_loss = proposed, row["metrics"], value
                row.update(
                    loss=value,
                    episode=episode,
                    step=step,
                    incumbent_improved=accepted,
                    incumbent_loss=incumbent_loss if current is not None else None,
                )
                rows.append(row)
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    if code_hash() != source:
        raise ValueError("Physics changed during refined policy evaluation")
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
        policy_sha256=sha(policy_file),
    )


def run(training, original, baseline, output, *, steps=32768, workers=3):
    import gymnasium
    import stable_baselines3
    import torch
    from stable_baselines3 import PPO, SAC
    from stable_baselines3.common.env_checker import check_env

    from scripts.refined_design_rl import RefinedDesignEnvironment

    output.mkdir(parents=True, exist_ok=False)
    begin, source = time.monotonic(), code_hash()
    torch.set_num_threads(1)
    tr, old, base = [read(p / "report.json") for p in (training, original, baseline)]
    if any(not r["source_unchanged"] or r["source_hash"] != source for r in (tr, old, base)):
        raise ValueError("Training and baseline sources differ")
    if base["training_report_sha256"] != sha(original / "report.json"):
        raise ValueError("Old policies used a different original surrogate")
    if tuple(tr["reserved_new_test_seeds"]) != SEEDS or set(SEEDS) & set(base["seeds"]):
        raise ValueError("Fresh evaluation seed contract differs")
    models, inputs = [], {}
    for folder in (training, original, baseline):
        inputs[str(folder)] = sha(folder / "report.json")
    for i, entry in enumerate(tr["anchors"]):
        path, old_path = training / f"model-{i}.json", original / f"model-{i}.json"
        if sha(path) != entry["model_sha256"] or sha(old_path) != old["anchors"][i]["model_sha256"]:
            raise ValueError("Changed surrogate")
        if sha(training / f"examples-{i}.jsonl") != entry["examples_sha256"]:
            raise ValueError("Changed training data")
        model, old_model = read(path), read(old_path)
        if not model["validation_enabled"] or any(
            model[k] != old_model[k] for k in ("anchor", "cad", "source_hash")
        ):
            raise ValueError("Unvalidated surrogate or changed physical anchor")
        models.append(model)
    paths = [
        Path(__file__).with_name(name)
        for name in (
            "benchmark_refined_rl.py",
            "benchmark_design_rl.py",
            "benchmark_evolution.py",
            "design_rl.py",
            "refined_design_rl.py",
            "adaptive_evolution.py",
            "mixed_genetic.py",
            "search_joint_designs.py",
            "search_surrogate.py",
            "refine_rl_surrogate.py",
        )
    ]
    hashes = {p.name: sha(p) for p in paths}
    report = dict(
        source_hash=source,
        script_hashes=hashes,
        methods=METHODS,
        seeds=SEEDS,
        input_reports=inputs,
        training_report_sha256=sha(training / "report.json"),
        previous_report_sha256=sha(baseline / "report.json"),
        training_steps_per_policy=steps,
        training=[],
        frozen_baselines=[],
        runs=[],
        results=[],
        population_size=32,
        generations=10,
        workers=workers,
        versions=dict(
            torch=torch.__version__,
            stable_baselines3=stable_baselines3.__version__,
            gymnasium=gymnasium.__version__,
            numpy=np.__version__,
        ),
        material_policy="host initial population; fixed within RL episode; mutable in DE",
        state_fidelity_train="frozen refined surrogate",
        state_fidelity_test="axial simulator",
        physics_evaluation_budget_per_anchor_seed=352,
        hyperparameters=dict(
            training_seed_base=81001,
            gamma=1,
            learning_rate=0.0003,
            net_arch=[64, 64],
            ppo_steps=256,
            ppo_epochs=10,
            batch_size=128,
            sac_learning_starts=512,
            sac_train_freq=4,
            sac_gradient_steps=1,
            sac_entropy="auto_0.02",
            reward_gain=5,
            curriculum_probability=0.5,
        ),
        physical_qualification=False,
        acceptance_performed=False,
    )
    write_json(output / "plan.json", report)
    check_env(RefinedDesignEnvironment(models), warn=True)
    policies = {}
    for method in ("ppo", "sac"):
        for index, seed in enumerate(SEEDS):
            previous = next(
                r
                for r in base["training"]
                if r["method"] == method and r["training_seed"] == 70001 + index
            )
            old_policy = baseline / previous["policy_file"]
            if (
                old_policy.parent.resolve() != baseline.resolve()
                or sha(old_policy) != previous["policy_sha256"]
            ):
                raise ValueError("Changed baseline policy")
            copied = output / f"policy-{method}-v1-{seed}.zip"
            shutil.copyfile(old_policy, copied)
            policies[(method + "-v1", seed)] = copied
            report["frozen_baselines"].append(
                dict(
                    method=method + "-v1",
                    evaluation_seed=seed,
                    policy_file=copied.name,
                    policy_sha256=sha(copied),
                    original_training_seed=previous["training_seed"],
                    original_policy_file=previous["policy_file"],
                )
            )
            started = time.monotonic()
            env = RefinedDesignEnvironment(models, record=True)
            common = dict(
                policy="MlpPolicy",
                env=env,
                seed=81001 + index,
                gamma=1.0,
                learning_rate=0.0003,
                device="cpu",
                verbose=0,
                policy_kwargs=dict(net_arch=[64, 64]),
            )
            policy = (
                PPO(**common, n_steps=256, batch_size=128, n_epochs=10)
                if method == "ppo"
                else SAC(
                    **common,
                    learning_starts=512,
                    buffer_size=max(20000, steps),
                    batch_size=128,
                    train_freq=4,
                    gradient_steps=1,
                    ent_coef="auto_0.02",
                )
            )
            policy.learn(total_timesteps=steps)
            path = output / f"policy-{method}-v2-{seed}.zip"
            policy.save(path)
            trace = output / f"transitions-{method}-v2-{seed}.npz"
            env.save_transitions(trace)
            entry = dict(
                method=method + "-v2",
                evaluation_seed=seed,
                training_seed=81001 + index,
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
            policies[(method + "-v2", seed)] = path
            write_json(output / "training-progress.json", report)
            print(json.dumps(entry), flush=True)
            env.close()
    # No fresh-seed simulator outcome is observed until all six new policies are frozen.
    jobs = [
        (
            model,
            method,
            seed,
            i,
            policies.get((method, seed)),
            output / f"{method}-{seed}-{i}.jsonl",
            source,
        )
        for seed in SEEDS
        for i, model in enumerate(models)
        for method in METHODS
    ]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(evaluate_refined, jobs):
            report["runs"].append(row)
            write_json(output / "progress.json", report)
            print(
                json.dumps({k: row[k] for k in ("method", "seed", "anchor", "best_loss")}),
                flush=True,
            )
    for seed in SEEDS:
        for i in range(3):
            group = [r for r in report["runs"] if r["seed"] == seed and r["anchor"] == i]
            if (
                len(group) != len(METHODS)
                or len({r["initial_sha256"] for r in group}) != 1
                or any(r["evaluations"] != 352 for r in group)
            ):
                raise ValueError("Unmatched initial population or budget")
    jobs = []
    for method in METHODS:
        for i in range(3):
            row = min(
                (r for r in report["runs"] if r["method"] == method and r["anchor"] == i),
                key=lambda r: r["best_loss"],
            )
            label = f"{method}-{i}"
            jobs.append(
                (
                    label,
                    DesignSpec.model_validate(row["best"]["spec"]),
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
        source_unchanged=(
            code_hash() == source
            and hashes == {p.name: sha(p) for p in paths}
            and inputs == {str(p): sha(p / "report.json") for p in (training, original, baseline)}
        ),
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
    for field in ("training", "original", "baseline", "output"):
        p.add_argument(field, type=Path)
    p.add_argument("--steps", type=int, default=32768)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--rl-libraries", type=Path)
    a = p.parse_args()
    if a.rl_libraries:
        sys.path.append(str(a.rl_libraries.resolve()))
    if a.steps < 512 or a.steps % 256 or not 1 <= a.workers <= 4:
        p.error("Use steps >=512 divisible by 256 and 1–4 workers")
    run(a.training, a.original, a.baseline, a.output, steps=a.steps, workers=a.workers)
