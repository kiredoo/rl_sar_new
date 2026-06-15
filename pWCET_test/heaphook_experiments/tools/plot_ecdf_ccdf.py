#!/usr/bin/env python3
"""ECDF + CCDF (1 - CDF) plot for any 1 Hz time-series TSV (M3 viz P0).

Renders two side-by-side panels for any numeric column from a 1 Hz
sample TSV:

  Panel 1: ECDF (linear y) — what fraction of samples ≤ x
  Panel 2: CCDF on log-y (1 - ECDF) — tail behaviour visible 4 decades

This is the workhorse "tail story" plot per
`docs/SOTA_VIZ_PATTERNS.md` P0. Multiple files can be overlaid on the
same panel pair to compare arms (same colour palette as figstyle.py).

Schema requirement: input TSV has a `# schema=N` first line (N≥1) or
no header (treated as legacy=0 with WARN per
`feedback_schema_legacy_bypass.md`).

Usage:
    tools/plot_ecdf_ccdf.py \\
        --label A    --tsv runs/A-rep1/raw/baseline/sample_rss.tsv \\
        --label D-v4 --tsv runs/D-rep1/raw/hybrid-fixed/sample_rss.tsv \\
        --column rss_kb --aggregate sum_per_epoch \\
        --output reports/figures/ecdf_rss_a_vs_d.png \\
        --preset paper

Aggregation modes:
  - none           (default) — use raw column values directly
  - sum_per_epoch  — group by epoch, sum the column across pids per epoch
  - max_per_epoch  — group by epoch, max
  - per_pid        — keep per-pid values without aggregation (for tail of
                     per-pid distribution rather than per-epoch sum)

The MiB axis formatter applies if --column rss_kb (auto-detected by
column name).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import figstyle


def read_tsv(path: Path) -> pd.DataFrame:
    """Read a 1 Hz sample TSV with schema=1 or legacy=0 headers."""
    schema = 0
    skip = 0
    with path.open() as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.startswith("#"):
                skip += 1
                if "schema=" in line:
                    try:
                        schema = int(line.split("schema=")[1].split()[0].rstrip(";"))
                    except (IndexError, ValueError):
                        pass
                continue
            break
    if schema == 0:
        sys.stderr.write(f"WARN: legacy schema=0 at {path}; assuming pre-N3 fields\n")
    return pd.read_csv(path, sep="\t", comment="#")


def aggregate(df: pd.DataFrame, column: str, mode: str) -> np.ndarray:
    """Reduce DataFrame to a 1D array of values per the aggregation mode."""
    if column not in df.columns:
        raise KeyError(f"column {column!r} not in TSV (have: {list(df.columns)})")
    if mode == "none":
        return df[column].dropna().to_numpy()
    if mode == "sum_per_epoch":
        if "epoch" not in df.columns:
            raise KeyError("aggregate=sum_per_epoch requires an `epoch` column")
        return df.groupby("epoch")[column].sum().to_numpy()
    if mode == "max_per_epoch":
        if "epoch" not in df.columns:
            raise KeyError("aggregate=max_per_epoch requires an `epoch` column")
        return df.groupby("epoch")[column].max().to_numpy()
    if mode == "per_pid":
        return df[column].dropna().to_numpy()
    raise ValueError(f"unknown aggregate mode {mode!r}")


def plot_pair(
    series: List[Tuple[str, np.ndarray]],
    column_label: str,
    is_kb: bool,
    output: Path,
    title: str | None = None,
) -> None:
    """Render the ECDF + CCDF panel pair."""
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    for label, values in series:
        if values.size == 0:
            sys.stderr.write(f"WARN: arm {label!r} has 0 samples; skipping\n")
            continue
        sorted_vals = np.sort(values)
        n = sorted_vals.size
        ecdf = np.arange(1, n + 1) / n
        ccdf = 1 - ecdf + 1.0 / n   # avoid log(0) at the tip
        color = figstyle.arm_color(label)
        axes[0].plot(sorted_vals, ecdf, color=color, label=label)
        axes[1].plot(sorted_vals, ccdf, color=color, label=label)

    axes[0].set_xlabel(column_label)
    axes[0].set_ylabel("ECDF")
    axes[0].legend()

    axes[1].set_xlabel(column_label)
    axes[1].set_ylabel("CCDF (1 − ECDF), log scale")
    axes[1].set_yscale("log")
    axes[1].legend()

    if is_kb:
        figstyle.format_axis_mib(axes[0], axis="x")
        figstyle.format_axis_mib(axes[1], axis="x")

    if title:
        fig.suptitle(title)

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output)
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--label", action="append", required=True, help="Series label (arm or scenario); paired with --tsv")
    p.add_argument("--tsv", action="append", required=True, help="Input TSV path; paired with --label")
    p.add_argument("--column", default="rss_kb", help="Column name to summarise (default rss_kb)")
    p.add_argument("--aggregate", choices=["none", "sum_per_epoch", "max_per_epoch", "per_pid"], default="sum_per_epoch")
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--preset", choices=list(figstyle.DPI_PRESETS), default="report")
    p.add_argument("--title", default=None)
    args = p.parse_args()

    if len(args.label) != len(args.tsv):
        p.error("--label and --tsv must be paired the same number of times")

    figstyle.apply(preset=args.preset)

    series: List[Tuple[str, np.ndarray]] = []
    for label, tsv in zip(args.label, args.tsv):
        df = read_tsv(Path(tsv))
        values = aggregate(df, args.column, args.aggregate)
        series.append((label, values))

    is_kb = args.column.endswith("_kb")
    column_label = args.column + (" (KiB → MiB labelled)" if is_kb else "")
    plot_pair(series, column_label, is_kb, args.output, title=args.title)

    sys.stderr.write(f"wrote {args.output}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
