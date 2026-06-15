#!/usr/bin/env python3
"""Render cross-arm fragmentation comparison figures from per-rep
frag_summary.tsv files (Phase 2.5b).

Usage:
    tools/plot_frag_cross_arm.py \\
        --arm A --runs runs/A1 runs/A2 \\
        --arm B --runs runs/B1 runs/B2 \\
        --arm D-v4 --runs runs/D1 runs/D2 \\
        --output reports/figures/frag_cross_arm_n2.png \\
        --preset paper
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import figstyle


_ARM_FOOTER = re.compile(
    r"^#\s*arm=(?P<arm>\S+)\s+n_pids=(?P<n_pids>\d+)\s+"
    r"total_peak_allocated=(?P<peak>\d+)\s+"
    r"mean_frag_ratio=(?P<mean>[-\d.]+)\s+"
    r"stddev_frag_ratio=(?P<sd>[-\d.]+)\s*$"
)


def read_arm_aggregate(run_dir: Path, expect_arm: str) -> Dict[str, float]:
    p = run_dir / "derived" / "frag_summary.tsv"
    if not p.exists():
        return {}
    with p.open() as f:
        for line in f:
            m = _ARM_FOOTER.match(line.strip())
            if m and m.group("arm") == expect_arm:
                return {
                    "n_pids": float(m.group("n_pids")),
                    "peak": float(m.group("peak")),
                    "mean": float(m.group("mean")),
                    "sd": float(m.group("sd")),
                }
    return {}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arm", action="append", required=True)
    p.add_argument("--runs", action="append", nargs="+", required=True)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--preset", choices=list(figstyle.DPI_PRESETS), default="paper")
    args = p.parse_args()

    if len(args.arm) != len(args.runs):
        p.error("--arm and --runs must be paired")

    figstyle.apply(preset=args.preset)

    label_to_key = {"A": "A", "B": "A", "D-v4": "D"}

    arm_data: Dict[str, List[Dict[str, float]]] = {}
    for label, run_list in zip(args.arm, args.runs):
        rows: List[Dict[str, float]] = []
        for r in run_list:
            d = read_arm_aggregate(Path(r), label_to_key.get(label, label[:1]))
            if not d and label_to_key.get(label, label[:1]) != "A":
                # fallback to A row (e.g. arm B uses glibc provider → A row)
                d = read_arm_aggregate(Path(r), "A")
            if d:
                rows.append(d)
        arm_data[label] = rows

    # 2-panel figure: mean frag_ratio bar + peak_allocated bar
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    arms = list(arm_data.keys())
    means = [np.mean([r["mean"] for r in arm_data[a]]) if arm_data[a] else np.nan for a in arms]
    sds = [np.std([r["mean"] for r in arm_data[a]], ddof=1) if len(arm_data[a]) > 1 else 0
           for a in arms]
    peaks_mib = [np.mean([r["peak"] for r in arm_data[a]]) / (1024 * 1024) if arm_data[a] else 0
                 for a in arms]
    n_pids_avg = [np.mean([r["n_pids"] for r in arm_data[a]]) if arm_data[a] else 0 for a in arms]

    colors = [figstyle.arm_color(a) for a in arms]

    ax1 = axes[0]
    bars = ax1.bar(arms, means, yerr=sds, color=colors, capsize=5, edgecolor="black", linewidth=0.5)
    ax1.set_ylabel("mean frag_ratio (across reps × PIDs)")
    ax1.set_ylim(0, 1.0)
    ax1.set_title("Cross-arm mean fragmentation ratio (N=2 reps)")
    for b, m, sd in zip(bars, means, sds):
        ax1.text(b.get_x() + b.get_width() / 2, m + 0.02,
                 f"{m:.3f}", ha="center", fontsize=10)

    ax2 = axes[1]
    bars2 = ax2.bar(arms, peaks_mib, color=colors, edgecolor="black", linewidth=0.5)
    ax2.set_ylabel("total peak allocated (MiB)")
    ax2.set_title("Total peak allocated (sum across PIDs × pools)")
    for b, p, n in zip(bars2, peaks_mib, n_pids_avg):
        ax2.text(b.get_x() + b.get_width() / 2, p + max(peaks_mib) * 0.02 if peaks_mib else 0.01,
                 f"{p:.0f} MiB\n({int(n)} PIDs)", ha="center", fontsize=9)

    fig.suptitle("Phase 2.5b — fragmentation cross-arm comparison · sampler-ON · 6 reps × 3 arms",
                 fontsize=12)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output)
    plt.close(fig)
    sys.stderr.write(f"wrote {args.output}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
