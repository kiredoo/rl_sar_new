#!/usr/bin/env python3
"""Render a 3-panel memory time series from a sample_rss.sh TSV.

Panels:
  1. total RSS (kB) — per-epoch sum across live pids
  2. minflt rate (faults/s) — first difference of cumulative-minflt sum,
     with last-value carry-forward for pids that disappeared, so a dying
     process does not show up as a negative rate
  3. nprocs live — per-epoch count of pids present

Usage:  plot_timeseries.py <input.tsv> <output.png>
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def load(tsv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(
        tsv_path,
        sep="\t",
        comment="#",
        dtype={"epoch": "int64", "pid": "int64", "minflt": "int64",
               "majflt": "int64", "rss_kb": "int64",
               "vol_ctx": "int64", "invol_ctx": "int64", "comm": "string"},
    )
    if df.empty:
        raise SystemExit(f"no data rows in {tsv_path}")
    return df


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    rss_wide = df.pivot_table(index="epoch", columns="pid",
                              values="rss_kb", aggfunc="last")
    minflt_wide = df.pivot_table(index="epoch", columns="pid",
                                 values="minflt", aggfunc="last").ffill()

    out = pd.DataFrame(index=rss_wide.index.sort_values())
    out["rss_kb_total"] = rss_wide.sum(axis=1, skipna=True)
    out["minflt_total"] = minflt_wide.sum(axis=1, skipna=True)
    out["nprocs"] = rss_wide.notna().sum(axis=1)

    dt = out.index.to_series().diff()
    out["minflt_rate"] = out["minflt_total"].diff() / dt
    out["t_rel"] = out.index - out.index.min()
    return out


def plot(agg: pd.DataFrame, out_png: Path, title: str) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)

    t = agg["t_rel"].to_numpy()

    axes[0].plot(t, (agg["rss_kb_total"] / 1024.0).to_numpy(), color="tab:blue")
    axes[0].set_ylabel("total RSS (MiB)")
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(t, agg["minflt_rate"].to_numpy(), color="tab:orange")
    axes[1].set_ylabel("minflt rate (faults/s)")
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(t, agg["nprocs"].to_numpy(), color="tab:green", drawstyle="steps-post")
    axes[2].set_ylabel("nprocs live")
    axes[2].set_xlabel("time since first sample (s)")
    axes[2].grid(True, alpha=0.3)

    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(out_png, dpi=120)
    plt.close(fig)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} <input.tsv> <output.png>", file=sys.stderr)
        return 2
    in_path = Path(argv[1])
    out_path = Path(argv[2])
    if not in_path.is_file():
        print(f"input not found: {in_path}", file=sys.stderr)
        return 1
    df = load(in_path)
    agg = aggregate(df)
    plot(agg, out_path, title=f"memory time series — {in_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
