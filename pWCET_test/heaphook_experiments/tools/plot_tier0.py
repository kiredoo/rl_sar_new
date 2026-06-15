#!/usr/bin/env python3
"""Render Tier 0 plumbing 3-panel PNGs from a single run's tier0/ outputs.

Inputs (from a runs/<id>/raw/<arm>/tier0/ directory):
  tier0_psi_memory.tsv          1 Hz  /proc/pressure/memory
  tier0_smaps_rollup.tsv        0.1 Hz  /proc/<pid>/smaps_rollup per pid
  tier0_cgroup_memory_stat.tsv  pre/post snapshot  cgroup memory.stat

Outputs (written next to the input dir, under figures/):
  psi_memory.png            avg10/60/300 + cumulative total_us
  smaps_pss_aggregate.png   sum PSS / sum RSS / PSS share over time
  cgroup_memory_pre_post.png  pre vs post bar chart for top keys

Usage:
  plot_tier0.py <tier0_dir>

Notes:
- PSI = 0 across the window is a normal "saturation absent" signal on
  abundant-RAM hosts (per feedback_psi_metric_semantics.md). The PNG
  visualises the flatline so the absence-of-saturation claim is
  inspectable, not just textual.
- PSS aggregate is sum across whatever PIDs the sampler watched. If
  the PID set drifted mid-rep (process died), the sum line dips at
  that round; smaps_rollup parser does not deduplicate.
- cgroup pre/post: only plotted if both phases captured (the trap fix
  in commit 869efe6 ensures post lands even on SIGTERM; older runs
  may have only pre).
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def _read_tsv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep="\t", comment="#")


def plot_psi(tier0_dir: Path, out_dir: Path) -> Path | None:
    p = tier0_dir / "tier0_psi_memory.tsv"
    if not p.exists():
        return None
    df = _read_tsv(p)
    if df.empty:
        return None
    df["t_rel"] = (df["epoch_ms"] - df["epoch_ms"].min()) / 1000.0
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    for kind in ("some", "full"):
        sub = df[df["line_kind"] == kind]
        axes[0].plot(sub["t_rel"].to_numpy(), sub["avg10"].to_numpy(),
                     label=f"{kind} avg10")
        axes[0].plot(sub["t_rel"].to_numpy(), sub["avg60"].to_numpy(),
                     label=f"{kind} avg60", linestyle="--")
    axes[0].set_ylabel("PSI memory (% time)")
    axes[0].legend(loc="upper right", fontsize=8)
    axes[0].set_title(f"PSI memory pressure — {tier0_dir.parent.parent.name} arm {tier0_dir.parent.name}")
    axes[0].grid(True, alpha=0.3)

    for kind in ("some", "full"):
        sub = df[df["line_kind"] == kind]
        delta = (sub["total_us"] - sub["total_us"].iloc[0]).to_numpy()
        axes[1].plot(sub["t_rel"].to_numpy(), delta,
                     label=f"{kind} Δtotal_us")
    axes[1].set_xlabel("seconds since first sample")
    axes[1].set_ylabel("Δ cumulative pressure (µs)")
    axes[1].legend(loc="upper left", fontsize=8)
    axes[1].grid(True, alpha=0.3)
    fig.tight_layout()
    out = out_dir / "psi_memory.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def plot_smaps_pss(tier0_dir: Path, out_dir: Path) -> Path | None:
    p = tier0_dir / "tier0_smaps_rollup.tsv"
    if not p.exists():
        return None
    df = _read_tsv(p)
    if df.empty:
        return None
    agg = (df.groupby("epoch_ms")
             .agg(rss_kB=("Rss_kB", "sum"),
                  pss_kB=("Pss_kB", "sum"),
                  pss_anon_kB=("Pss_Anon_kB", "sum"),
                  anon_huge_kB=("AnonHugePages_kB", "sum"),
                  n_pids=("pid", "nunique"))
             .reset_index())
    agg["t_rel"] = (agg["epoch_ms"] - agg["epoch_ms"].min()) / 1000.0
    agg["pss_share"] = agg["pss_kB"] / agg["rss_kB"] * 100.0

    t = agg["t_rel"].to_numpy()
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
    axes[0].plot(t, (agg["rss_kB"] / 1024).to_numpy(), label="sum RSS (MiB)")
    axes[0].plot(t, (agg["pss_kB"] / 1024).to_numpy(), label="sum PSS (MiB)")
    axes[0].plot(t, (agg["pss_anon_kB"] / 1024).to_numpy(),
                 label="sum Pss_Anon (MiB)", linestyle="--")
    axes[0].set_ylabel("MiB")
    axes[0].legend(loc="lower right", fontsize=8)
    axes[0].set_title(f"Tier 0 smaps_rollup aggregate — {tier0_dir.parent.parent.name} arm {tier0_dir.parent.name}")
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(t, agg["pss_share"].to_numpy(), color="tab:red")
    axes[1].set_ylabel("PSS / RSS (%)")
    axes[1].axhline(80, color="grey", linestyle=":", linewidth=0.8)
    axes[1].axhline(100, color="grey", linestyle=":", linewidth=0.8)
    axes[1].grid(True, alpha=0.3)
    axes[1].set_ylim(min(70, agg["pss_share"].min() - 2), 102)

    axes[2].plot(t, (agg["anon_huge_kB"] / 1024).to_numpy(), color="tab:green",
                 label="sum AnonHugePages (MiB)")
    axes[2].plot(t, agg["n_pids"].to_numpy(), color="tab:purple",
                 label="distinct pid count", linestyle="--")
    axes[2].set_xlabel("seconds since first sample")
    axes[2].legend(loc="lower right", fontsize=8)
    axes[2].grid(True, alpha=0.3)

    fig.tight_layout()
    out = out_dir / "smaps_pss_aggregate.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def plot_cgroup(tier0_dir: Path, out_dir: Path) -> Path | None:
    p = tier0_dir / "tier0_cgroup_memory_stat.tsv"
    if not p.exists():
        return None
    df = _read_tsv(p)
    if df.empty:
        return None
    phases = sorted(df["phase"].unique())
    if "pre" not in phases:
        return None
    keys_of_interest = ["rss", "cache", "anon", "shmem", "mapped_file",
                        "active_anon", "inactive_anon",
                        "active_file", "inactive_file"]
    have_post = "post" in phases
    pre = df[df["phase"] == "pre"].set_index("key")["value_bytes"]
    if have_post:
        post = df[df["phase"] == "post"].set_index("key")["value_bytes"]
    keys_present = [k for k in keys_of_interest if k in pre.index]
    if not keys_present:
        return None

    fig, ax = plt.subplots(figsize=(10, 5))
    x = range(len(keys_present))
    width = 0.4
    pre_vals = [pre[k] / (1024**2) for k in keys_present]
    ax.bar([i - width / 2 for i in x] if have_post else list(x),
           pre_vals, width=width if have_post else width * 2,
           label="pre", color="tab:blue")
    if have_post:
        post_vals = [post.get(k, 0) / (1024**2) for k in keys_present]
        ax.bar([i + width / 2 for i in x], post_vals, width=width,
               label="post", color="tab:orange")
    ax.set_xticks(list(x))
    ax.set_xticklabels(keys_present, rotation=30, ha="right")
    ax.set_ylabel("MiB")
    ax.set_title(f"cgroup memory.stat — {tier0_dir.parent.parent.name} arm {tier0_dir.parent.name}"
                 + ("" if have_post else " (pre only — post hook missed)"))
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    out = out_dir / "cgroup_memory_pre_post.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: plot_tier0.py <tier0_dir>", file=sys.stderr)
        return 2
    tier0_dir = Path(sys.argv[1]).resolve()
    if not tier0_dir.is_dir():
        print(f"not a directory: {tier0_dir}", file=sys.stderr)
        return 2
    out_dir = tier0_dir / "figures"
    out_dir.mkdir(exist_ok=True)
    outs = [
        plot_psi(tier0_dir, out_dir),
        plot_smaps_pss(tier0_dir, out_dir),
        plot_cgroup(tier0_dir, out_dir),
    ]
    for o in outs:
        if o:
            print(f"wrote {o}")
        else:
            print("(skipped — input missing or empty)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
