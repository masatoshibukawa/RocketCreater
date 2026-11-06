"""Plot an audited prediction comparison without claiming policy or physical accuracy."""

import argparse
import json
from pathlib import Path


def figure(report, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    rows = [r for r in report["rows"] if r["matched_samples"]]
    if not rows:
        raise ValueError("No held-out predictions with comparable history")
    names = ["Physics only", "Mean-gain mixing", "Residual correction"]
    keys = [
        "axial_absolute_error_m",
        "history_adjusted_absolute_error_m",
        "residual_corrected_absolute_error_m",
    ]
    colors = ["#66758a", "#bb7846", "#287e86"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    means = [np.mean([r[key] for r in rows]) for key in keys]
    axes[0].bar(names, means, color=colors, width=0.62)
    for i, value in enumerate(means):
        axes[0].text(i, value + max(means) * 0.025, f"{value:.4f}", ha="center")
    axes[0].set(ylim=(0, max(means) * 1.2), ylabel="Mean absolute error (m)")
    for key, color, name in zip(keys, colors, names, strict=True):
        axes[1].plot(range(1, len(rows) + 1), [r[key] for r in rows], ".-", color=color, label=name)
    axes[1].set(xlabel="Held-out selected transition", ylabel="Absolute error (m)")
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
    families = len(set(report["equivalent_ascent_groups"].values()))
    fig.suptitle(
        f"Exploratory prediction audit: {len(rows)} selected changes / {families} ascent families"
    )
    fig.text(
        0.5,
        -0.035,
        "Predicts changes in analytic-aero screening height; "
        "not flight accuracy or policy efficiency",
        ha="center",
        fontsize=9,
    )
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    figure(json.loads(args.audit.read_text(encoding="utf-8")), args.output)


if __name__ == "__main__":
    main()
