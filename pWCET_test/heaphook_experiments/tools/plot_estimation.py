#!/usr/bin/env python3
"""Gardner-Altman / Cumming-style estimation plot for cross-arm Δ (M3 P0).

Renders, per metric, two stacked panels:

  Top:    per-arm scatter of N reps + dashed group-mean line
  Bottom: bootstrap distribution of (compare_arm − baseline_arm) with
          95 % CI shading, mean Δ marked with a triangle, zero line

This is the SOTA paper-grade alternative to a 4-bar bar-chart with no
uncertainty (per `docs/SOTA_VIZ_PATTERNS.md` P0). One figure per metric;
all comparator arms share the bottom panel.

Reuses `tools/cross_arm_bootstrap.py` resampling logic (paired
bootstrap on per-rep means; --seed reproducible). Pure numpy +
matplotlib — no `dabest` dep. Schema=1 + legacy=0 bypass per
`feedback_schema_legacy_bypass.md`.

Usage (mirrors cross_arm_bootstrap.py CLI):

    tools/plot_estimation.py \\
        --baseline-arm A --baseline-runs runs/A-rep1 runs/A-rep2 runs/A-rep3 \\
        --arm B --runs runs/B-rep1 runs/B-rep2 runs/B-rep3 \\
        --arm D-v4 --runs runs/D-rep1 runs/D-rep2 runs/D-rep3 \\
        --metric minflt_delta \\
        --output reports/figures/estimation_minflt_a_vs_others.png \\
        --bootstrap-iters 10000 --seed 42 --preset paper

Tip: pair with `tools/plot_ecdf_ccdf.py` per metric for a complete
"summary + tail" page in `cross_abcd_v4.md`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import figstyle
import cross_arm_bootstrap as bs


def collect_metric(arm_label: str, run_dirs: List[Path], metric: str) -> np.ndarray:
    """Return an array of one metric value per rep dir."""
    vals: List[float] = []
    for d in run_dirs:
        summary = bs.read_summary_tsv(d)
        if metric not in summary:
            raise KeyError(f"arm {arm_label}: rep {d} missing metric {metric!r}")
        vals.append(float(summary[metric]))
    return np.array(vals, dtype=np.float64)


def bootstrap_distribution(
    baseline: np.ndarray, compare: np.ndarray, n_iters: int, rng: np.random.RandomState
) -> np.ndarray:
    """Return the n_iters-long array of (compare − baseline) bootstrap deltas."""
    nb, nc = baseline.shape[0], compare.shape[0]
    deltas = np.empty(n_iters, dtype=np.float64)
    for i in range(n_iters):
        sb = baseline[rng.randint(0, nb, size=nb)]
        sc = compare[rng.randint(0, nc, size=nc)]
        deltas[i] = sc.mean() - sb.mean()
    return deltas


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--baseline-arm", required=True)
    p.add_argument("--baseline-runs", nargs="+", required=True)
    p.add_argument("--arm", action="append", required=True)
    p.add_argument("--runs", action="append", nargs="+", required=True)
    p.add_argument("--metric", required=True, help="Single metric column name")
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--bootstrap-iters", type=int, default=10000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--preset", choices=list(figstyle.DPI_PRESETS), default="report")
    p.add_argument("--ylabel-top", default=None, help="Top-panel y-axis label (default: metric)")
    p.add_argument("--ylabel-bottom", default=None, help="Bottom-panel y-axis label (default: 'Δ vs baseline')")
    args = p.parse_args()

    if len(args.arm) != len(args.runs):
        p.error("--arm and --runs must be paired")

    figstyle.apply(preset=args.preset)
    rng = np.random.RandomState(args.seed)

    baseline_vals = collect_metric(args.baseline_arm, [Path(r) for r in args.baseline_runs], args.metric)

    arms_data: Dict[str, np.ndarray] = {args.baseline_arm: baseline_vals}
    arms_deltas: Dict[str, Tuple[np.ndarray, float, float, float]] = {}
    for arm_label, run_list in zip(args.arm, args.runs):
        compare_vals = collect_metric(arm_label, [Path(r) for r in run_list], args.metric)
        arms_data[arm_label] = compare_vals
        deltas = bootstrap_distribution(baseline_vals, compare_vals, args.bootstrap_iters, rng)
        arms_deltas[arm_label] = (
            deltas,
            float(deltas.mean()),
            float(np.percentile(deltas, 100 * args.alpha / 2)),
            float(np.percentile(deltas, 100 * (1 - args.alpha / 2))),
        )

    fig, axes = plt.subplots(2, 1, figsize=(8, 6), gridspec_kw={"height_ratios": [1, 1]})
    ax_top, ax_bot = axes

    arm_order = [args.baseline_arm] + list(args.arm)
    x_positions = np.arange(len(arm_order))
    for x, arm in zip(x_positions, arm_order):
        vals = arms_data[arm]
        color = figstyle.arm_color(arm)
        ax_top.scatter(np.full(vals.shape, x), vals, color=color, s=40, zorder=3, label=arm)
        ax_top.hlines(vals.mean(), x - 0.2, x + 0.2, color=color, linestyles="dashed", zorder=2)
    ax_top.set_xticks(x_positions)
    ax_top.set_xticklabels(arm_order)
    ax_top.set_ylabel(args.ylabel_top or args.metric)
    ax_top.set_title(f"Per-rep {args.metric} (N reps = {[arms_data[a].size for a in arm_order]})")

    bottom_arms = list(args.arm)
    bottom_x = np.arange(len(bottom_arms))
    for x, arm in zip(bottom_x, bottom_arms):
        deltas, mean_d, ci_low, ci_high = arms_deltas[arm]
        color = figstyle.arm_color(arm)
        density, edges = np.histogram(deltas, bins=60, density=True)
        widths = np.diff(edges)
        density_norm = density / density.max() * 0.35 if density.max() > 0 else density
        for d, e, w in zip(density_norm, edges[:-1], widths):
            ax_bot.fill_between(
                [x - d, x + d], e, e + w,
                color=color, alpha=0.4, edgecolor="none",
            )
        ax_bot.plot([x - 0.4, x + 0.4], [ci_low, ci_low], color=color, lw=1)
        ax_bot.plot([x - 0.4, x + 0.4], [ci_high, ci_high], color=color, lw=1)
        ax_bot.plot([x], [mean_d], marker="v", color=color, markersize=10, zorder=4)
    ax_bot.axhline(0, color="black", lw=0.8, linestyle=":")
    ax_bot.set_xticks(bottom_x)
    ax_bot.set_xticklabels([f"{a} − {args.baseline_arm}" for a in bottom_arms])
    ax_bot.set_ylabel(args.ylabel_bottom or f"Δ {args.metric} vs {args.baseline_arm}")
    ax_bot.set_title(
        f"Bootstrap (n={args.bootstrap_iters}, seed={args.seed}, α={args.alpha}): "
        f"95 % CI bars; ▼ = mean Δ; violin = bootstrap density"
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output)
    plt.close(fig)
    sys.stderr.write(f"wrote {args.output}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
