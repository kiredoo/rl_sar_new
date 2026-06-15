#!/usr/bin/env python3
"""Generate the 4 curated headline figures for the cross_abcd_v4 milestone.

Outputs (under reports/figures/):
  v4_d_n2_rss_timeseries.png   — D-v4 N=2 RSS overlay (rep1 retry + rep2 + tier0)
                                  + 4/29 D-v4 (F4+F2 only) for evolution context
  v4_cross_arm_rss_timeseries.png  — A today vs D-v4 today RSS overlay
  v4_pss_vs_rss_bar.png        — PSS / RSS share bar: A 80.0 % vs D-v4 86.7 %
  v4_psi_zero_evidence.png     — PSI memory total_us flatline (saturation absent)

Convention:
  - all RSS axes in MiB (per feedback_units_kb_to_mb.md)
  - per-run-id labels include date stamp + retry/sampler suffix
  - bag-replay window normalised so t=0 is the first sample of that rep
  - all 4 figures are single-panel; meant for embedding into reports
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
OUT = ROOT / "reports" / "figures"
OUT.mkdir(parents=True, exist_ok=True)


def _load_ts(run_id: str, arm: str) -> pd.DataFrame:
    p = RUNS / run_id / "raw" / arm / f"aw_{arm}_timeseries.tsv"
    df = pd.read_csv(p, sep="\t", comment="#")
    return df


def _agg_total_rss(df: pd.DataFrame) -> pd.DataFrame:
    out = (df.groupby("epoch")["rss_kb"].sum().reset_index()
             .rename(columns={"rss_kb": "rss_kb_total"}))
    out["t_rel"] = out["epoch"] - out["epoch"].min()
    out["rss_mib_total"] = out["rss_kb_total"] / 1024
    return out


# -----------------------------------------------------------------
# 1. D-v4 N=2 overlay
# -----------------------------------------------------------------
def fig_d_n2_overlay() -> None:
    runs = [
        ("20260429-1630_hybrid-fixed-v1", "D", "4/29 D-v4 F4+F2 (pre-F1/F3)"),
        ("20260430-1030_hybrid-fixed-v4-rep1", "D", "4/30 D-v4 rep1 retry"),
        ("20260430-1038_hybrid-fixed-v4-rep2", "D", "4/30 D-v4 rep2"),
        ("20260430-1230_hybrid-fixed-v4-tier0", "D", "4/30 D-v4 + Tier 0 (+26 % perturbed)"),
    ]
    fig, ax = plt.subplots(figsize=(11, 5))
    for run_id, arm, label in runs:
        try:
            df = _load_ts(run_id, arm)
            ag = _agg_total_rss(df)
            ax.plot(ag["t_rel"].to_numpy(), ag["rss_mib_total"].to_numpy(), label=label)
        except FileNotFoundError:
            continue
    ax.set_xlabel("seconds since first sample")
    ax.set_ylabel("sum RSS over Autoware procs (MiB)")
    ax.set_title("D-v4 N=2 RSS time-series overlay (with 4/29 F4+F2 baseline + Tier 0 caveat run)")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "v4_d_n2_rss_timeseries.png", dpi=120)
    plt.close(fig)
    print(f"wrote {OUT / 'v4_d_n2_rss_timeseries.png'}")


# -----------------------------------------------------------------
# 2. A today vs D-v4 today cross-arm RSS overlay
# -----------------------------------------------------------------
def fig_cross_arm() -> None:
    runs = [
        ("20260430-1014_baseline-cross-v4-rep1", "A", "tab:blue", "A today rep1 (no Tier 0)"),
        ("20260430-1042_baseline-cross-v4-rep2", "A", "tab:cyan", "A today rep2 (no Tier 0)"),
        ("20260430-1147_baseline-tier0-validate", "A", "tab:green", "A today rep3 + Tier 0"),
        ("20260430-1030_hybrid-fixed-v4-rep1", "D", "tab:red", "D-v4 today rep1 retry (no Tier 0)"),
        ("20260430-1038_hybrid-fixed-v4-rep2", "D", "tab:orange", "D-v4 today rep2 (no Tier 0)"),
        ("20260430-1230_hybrid-fixed-v4-tier0", "D", "tab:brown", "D-v4 today + Tier 0 (+26 % perturbed)"),
    ]
    fig, ax = plt.subplots(figsize=(11, 5))
    for run_id, arm, color, label in runs:
        try:
            df = _load_ts(run_id, arm)
            ag = _agg_total_rss(df)
            ax.plot(ag["t_rel"].to_numpy(), ag["rss_mib_total"].to_numpy(),
                    label=label, color=color, linewidth=1.4)
        except FileNotFoundError:
            continue
    ax.set_xlabel("seconds since first sample")
    ax.set_ylabel("sum RSS over Autoware procs (MiB)")
    ax.set_title("Cross-arm RSS time-series — A (glibc) vs D-v4 (hybrid F1-F4), 2026-04-30")
    ax.legend(loc="center right", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "v4_cross_arm_rss_timeseries.png", dpi=120)
    plt.close(fig)
    print(f"wrote {OUT / 'v4_cross_arm_rss_timeseries.png'}")


# -----------------------------------------------------------------
# 3. PSS / RSS bar (today's findings, qualitative N=1)
# -----------------------------------------------------------------
def fig_pss_bar() -> None:
    arms = [
        ("A glibc (today's tier0-validate, N=1)", 67945, 54364),
        ("D-v4 hybrid (today's tier0 supersession, N=1)", 102585, 88947),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    labels = [a[0] for a in arms]
    rss_vals = [a[1] for a in arms]
    pss_vals = [a[2] for a in arms]
    x = range(len(labels))
    width = 0.35
    axes[0].bar([i - width / 2 for i in x], rss_vals, width=width, label="sum RSS", color="tab:blue")
    axes[0].bar([i + width / 2 for i in x], pss_vals, width=width, label="sum PSS", color="tab:orange")
    axes[0].set_xticks(list(x))
    axes[0].set_xticklabels(labels, rotation=12, ha="right", fontsize=8)
    axes[0].set_ylabel("MiB (sum over 90 Autoware procs)")
    axes[0].set_title("RSS vs PSS — RSS over-counts shared memory")
    axes[0].legend()
    axes[0].grid(True, axis="y", alpha=0.3)

    shares = [pss / rss * 100 for _, rss, pss in arms]
    axes[1].bar(list(x), shares, color=["tab:blue", "tab:red"])
    for i, s in enumerate(shares):
        axes[1].text(i, s + 0.5, f"{s:.1f} %", ha="center", fontsize=10)
    axes[1].set_xticks(list(x))
    axes[1].set_xticklabels([a[0].split()[0] for a in arms], fontsize=10)
    axes[1].axhline(100, color="grey", linestyle=":", linewidth=0.8)
    axes[1].set_ylabel("PSS / RSS (%)  — closer to 100 % = less double-counting")
    axes[1].set_ylim(70, 102)
    axes[1].set_title("Shared-memory bookkeeping — D-v4's per-thread pools = more private")
    axes[1].grid(True, axis="y", alpha=0.3)

    fig.suptitle("PSS-honest cross-arm — qualitative N=1 finding (2026-04-30)", y=1.02)
    fig.tight_layout()
    fig.savefig(OUT / "v4_pss_vs_rss_bar.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT / 'v4_pss_vs_rss_bar.png'}")


# -----------------------------------------------------------------
# 4. PSI = 0 evidence (saturation absent)
# -----------------------------------------------------------------
def fig_psi_zero() -> None:
    runs = [
        ("20260430-1147_baseline-tier0-validate", "A", "tab:blue", "A today (rep3 + Tier 0)"),
        ("20260430-1230_hybrid-fixed-v4-tier0", "D", "tab:red", "D-v4 today (+ Tier 0)"),
    ]
    fig, axes = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    for run_id, arm, color, label in runs:
        p = RUNS / run_id / "raw" / arm / "tier0" / "tier0_psi_memory.tsv"
        if not p.exists():
            continue
        df = pd.read_csv(p, sep="\t", comment="#")
        df["t_rel"] = (df["epoch_ms"] - df["epoch_ms"].min()) / 1000.0
        for kind, ls in (("some", "-"), ("full", "--")):
            sub = df[df["line_kind"] == kind]
            if sub.empty:
                continue
            axes[0].plot(sub["t_rel"].to_numpy(), sub["avg10"].to_numpy(),
                         color=color, linestyle=ls, label=f"{label} {kind} avg10")
            axes[1].plot(sub["t_rel"].to_numpy(),
                         (sub["total_us"] - sub["total_us"].iloc[0]).to_numpy(),
                         color=color, linestyle=ls, label=f"{label} {kind} Δtotal_us")

    axes[0].set_ylabel("PSI memory avg10 (% time)")
    axes[0].set_ylim(-0.05, 1.0)
    axes[0].axhline(0, color="grey", linestyle=":", linewidth=0.5)
    axes[0].legend(loc="upper right", fontsize=8)
    axes[0].set_title("PSI memory pressure — saturation absent on both A and D-v4 (host has 80 GiB RAM)")
    axes[0].grid(True, alpha=0.3)

    axes[1].set_ylabel("Δ cumulative total_us")
    axes[1].set_xlabel("seconds since first sample")
    axes[1].axhline(0, color="grey", linestyle=":", linewidth=0.5)
    axes[1].legend(loc="upper right", fontsize=8)
    axes[1].grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(OUT / "v4_psi_zero_evidence.png", dpi=120)
    plt.close(fig)
    print(f"wrote {OUT / 'v4_psi_zero_evidence.png'}")


def main() -> int:
    fig_d_n2_overlay()
    fig_cross_arm()
    fig_pss_bar()
    fig_psi_zero()
    return 0


if __name__ == "__main__":
    sys.exit(main())
