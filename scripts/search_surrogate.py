"""Optional MLP proposal ranking; portable JSON weights, no predicted acceptance."""

import warnings

import numpy as np

from scripts.mixed_genetic import canonical

TARGETS = ("height_m", "static_margin_cal", "beam_ratio")


def features(points, categories):
    x = canonical(points, categories)
    if x.ndim != 2:
        raise ValueError("A matrix of candidates is required")
    blocks = [x[:, [i for i in range(x.shape[1]) if i not in categories]]]
    for axis, count in sorted(categories.items()):
        blocks.append(np.eye(count)[np.minimum((x[:, axis] * count).astype(int), count - 1)])
    return np.column_stack(blocks)


def targets(metrics):
    return [
        metrics["scenario_height_m"][0],
        metrics["static_margin_cal"],
        metrics["conservative_beam_ratio"],
    ]


def predict(model, points):
    categories = {int(k): v for k, v in model["categories"].items()}
    x = features(points, categories)
    x = (x - np.asarray(model["x_mean"])) / np.asarray(model["x_scale"])
    for i, (w, b) in enumerate(zip(model["weights"], model["biases"], strict=True)):
        x = x @ np.asarray(w) + np.asarray(b)
        if i < len(model["weights"]) - 1:
            x = np.maximum(x, 0)
    return x * np.asarray(model["y_scale"]) + np.asarray(model["y_mean"])


def advisor(model):
    if not model["validation_enabled"]:
        return None

    def rank(points):
        y = predict(model, points)
        return 2000 * np.maximum(0, 1.12 - y[:, 1]) - y[:, 0]

    return rank


def load_advisor(folder, index, anchor, cad, source):
    """A frozen model applies only to its exact anchor, CAD and physical source."""
    from rocketwright.agent.design_projects import sha
    from rocketwright.analysis.worker import read

    report = read(folder / "report.json")
    entry = report["anchors"][index]
    path = folder / f"model-{index}.json"
    model = read(path)
    if (
        not report["source_unchanged"]
        or report["source_hash"] != source
        or model["source_hash"] != source
        or sha(path) != entry["model_sha256"]
        or model["anchor"] != anchor.model_dump(mode="json")
        or model["cad"] != cad
    ):
        raise ValueError("Surrogate source, anchor or CAD differs; collect matching examples")
    return advisor(model), entry["model_sha256"]


def fit(x, y, validation_x, validation_y, *, categories, seed=9021):
    """Training normalization and internal early stopping never see held-out test labels."""
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.neural_network import MLPRegressor
    from threadpoolctl import threadpool_limits

    fx = features(x, categories)
    y = np.asarray(y, float)
    if len(fx) < 64 or y.shape != (len(fx), 3) or not np.isfinite(y).all():
        raise ValueError("At least 64 finite three-target training examples required")
    xm, xs = fx.mean(0), np.maximum(fx.std(0), 1e-8)
    ym, ys = y.mean(0), np.maximum(y.std(0), 1e-8)
    reg = MLPRegressor(
        hidden_layer_sizes=(64, 32),
        max_iter=500,
        random_state=seed,
        early_stopping=True,
        validation_fraction=0.15,
        n_iter_no_change=25,
        alpha=0.01,
        learning_rate_init=0.002,
        batch_size=128,
    )
    with threadpool_limits(limits=1), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        reg.fit((fx - xm) / xs, (y - ym) / ys)
    model = dict(
        schema=1,
        categories=categories,
        targets=TARGETS,
        architecture=[fx.shape[1], 64, 32, 3],
        x_mean=xm.tolist(),
        x_scale=xs.tolist(),
        y_mean=ym.tolist(),
        y_scale=ys.tolist(),
        weights=[w.tolist() for w in reg.coefs_],
        biases=[b.tolist() for b in reg.intercepts_],
        epochs=int(reg.n_iter_),
        seed=seed,
        training_count=len(fx),
        convergence_warning=any(issubclass(w.category, ConvergenceWarning) for w in caught),
        validation_enabled=False,
        predicted_acceptance=False,
    )
    predicted = predict(model, validation_x)
    truth = np.asarray(validation_y)
    mae, baseline = np.abs(predicted - truth).mean(0), np.abs(ym - truth).mean(0)
    model.update(
        validation_count=len(truth),
        validation_mae=mae.tolist(),
        validation_mean_baseline_mae=baseline.tolist(),
        validation_enabled=bool(np.isfinite(predicted).all() and np.all(mae[:2] < baseline[:2])),
    )
    return model
