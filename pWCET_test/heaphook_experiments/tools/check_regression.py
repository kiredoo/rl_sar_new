#!/usr/bin/env python3
"""Regression check for a new rep against prior reps in the same arm.

Reads `derived_cross/aggregate.csv` (refreshed by aggregate_configs.py)
and the target run's `derived/summary.tsv`. Compares every metric against
the rolling mean of historical reps in the same arm, flags anomalies.

Output (stdout, also a markdown block under `--md` flag for embedding into
MANIFEST or reports):

  PASS     all metrics within band
  FLAG     one or more metrics outside band; per-metric reason listed
  ERROR    can't compute (missing data, schema mismatch)

Bands (default; override via env vars):
  MINFLT_BAND_PCT  ±15
  RSS_BAND_PCT     ±15
  RSS_PRE_BAND_PCT ±5
  ABORTS_DELTA     ±2
  NPROCS_DELTA     ±1

Usage:
  tools/check_regression.py <run_dir>
  tools/check_regression.py <run_dir> --md      # markdown block for MANIFEST
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

BANDS = {
    "minflt_delta":   float(os.environ.get("MINFLT_BAND_PCT", "15")),
    "rss_kb_delta":   float(os.environ.get("RSS_BAND_PCT", "15")),
    "rss_kb_pre":     float(os.environ.get("RSS_PRE_BAND_PCT", "5")),
    "aborts":         float(os.environ.get("ABORTS_DELTA", "2")),
    "nprocs":         float(os.environ.get("NPROCS_DELTA", "1")),
}

SAME_ARM_KEY = "arm"


def _load_aggregate() -> pd.DataFrame:
    p = ROOT / "derived_cross" / "aggregate.csv"
    if not p.exists():
        raise SystemExit(f"missing aggregate; run tools/aggregate_configs.py first")
    df = pd.read_csv(p)
    return df[df["run_id"].notna() & (df["run_id"] != "(not yet run)")].copy()


def _load_run(run_dir: Path) -> pd.DataFrame:
    p = run_dir / "derived" / "summary.tsv"
    if not p.exists():
        raise SystemExit(f"missing {p}")
    df = pd.read_csv(p, sep="\t", comment="#")
    return df


def _check_metric(name: str, this_val: float, peers: pd.Series, abs_delta: bool) -> dict:
    """Return dict(status, mean, this, deviation, band, msg)."""
    if peers.empty or peers.dropna().empty:
        return {"status": "skip", "msg": f"{name}: no peers in same arm; skipped"}
    mean = peers.dropna().astype(float).mean()
    band = BANDS[name]
    if abs_delta:
        dev = this_val - mean
        within = abs(dev) <= band
        msg = f"{name}: {this_val:g} vs mean {mean:.1f} (Δ={dev:+.1f}, band ±{band:g})"
    else:
        if mean == 0:
            return {"status": "skip", "msg": f"{name}: peer mean is 0; skipped"}
        dev_pct = (this_val - mean) / mean * 100.0
        within = abs(dev_pct) <= band
        msg = f"{name}: {this_val:g} vs mean {mean:.1f} (Δ={dev_pct:+.1f}%, band ±{band:g}%)"
    return {"status": "pass" if within else "flag",
            "mean": mean, "this": this_val, "msg": msg}


def main() -> int:
    args = sys.argv[1:]
    md = "--md" in args
    args = [a for a in args if not a.startswith("--")]
    if len(args) != 1:
        print("usage: tools/check_regression.py <run_dir> [--md]", file=sys.stderr)
        return 2
    run_dir = Path(args[0]).resolve()
    run_id = run_dir.name

    agg = _load_aggregate()
    this = _load_run(run_dir)
    if this.empty:
        print("ERROR: empty summary.tsv", file=sys.stderr)
        return 2

    # Match this rep to its arm by checking the run_id (scoped to today's
    # commit-time aggregate). Fallback: match by arm letter.
    rows = []
    for _, row in this.iterrows():
        arm = row[SAME_ARM_KEY]
        peers = agg[(agg[SAME_ARM_KEY] == arm) & (agg["run_id"] != run_id)]
        if peers.empty:
            print(f"WARN: no peers for arm {arm}", file=sys.stderr)
        per_metric = []
        per_metric.append(_check_metric("minflt_delta", float(row["minflt_delta"]),
                                         peers["minflt_delta"], abs_delta=False))
        per_metric.append(_check_metric("rss_kb_delta", float(row["rss_kb_delta"]),
                                         peers["rss_kb_delta"], abs_delta=False))
        per_metric.append(_check_metric("rss_kb_pre", float(row["rss_kb_pre"]),
                                         peers["rss_kb_pre"], abs_delta=False))
        per_metric.append(_check_metric("aborts", float(row["aborts"]),
                                         peers["aborts"], abs_delta=True))
        per_metric.append(_check_metric("nprocs", float(row["nprocs"]),
                                         peers["nprocs"], abs_delta=True))
        flagged = [m for m in per_metric if m["status"] == "flag"]
        rows.append({"arm": arm, "metrics": per_metric, "flagged": flagged})

    has_flag = any(r["flagged"] for r in rows)
    verdict = "FLAG" if has_flag else "PASS"

    if md:
        print(f"<!-- regression check {verdict} (vs historical aggregate) -->")
        print(f"\n## Regression check ({verdict})\n")
        for r in rows:
            print(f"### Arm {r['arm']}\n")
            print("| metric | result | this run | peer mean | band |")
            print("|---|---|---|---|---|")
            for m in r["metrics"]:
                if m["status"] == "skip":
                    print(f"| (skipped) | — | — | — | {m['msg']} |")
                else:
                    icon = "✅" if m["status"] == "pass" else "⚠️"
                    print(f"| {m['msg'].split(':')[0]} | {icon} | {m.get('this', '?')} | {m.get('mean', '?'):.1f} | {m['msg']} |")
            print()
    else:
        print(f"REGRESSION CHECK: {verdict}")
        for r in rows:
            print(f"  arm {r['arm']}:")
            for m in r["metrics"]:
                icon = {"pass": "✅", "flag": "⚠️", "skip": "⏭"}.get(m["status"], "?")
                print(f"    {icon} {m['msg']}")

    return 0 if not has_flag else 1


if __name__ == "__main__":
    sys.exit(main())
