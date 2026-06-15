#!/usr/bin/env python3
"""Paired bootstrap CI for cross-arm Δ on per-rep summary.tsv metrics.

Produces, for each cross-arm pair (arm_X vs baseline_arm) and each metric
in METRICS, the bootstrap mean of Δ and a percentile 95% CI. Reads each
run's `derived/summary.tsv` (schema=1; legacy=0 bypassed with warn per
`feedback_schema_legacy_bypass.md`).

Output: writes a TSV with one row per (arm, metric) tuple to stdout, or
to --output. Header: schema=1.

This is the M0/R-A enabler — `cross_abcd_v4.md` § Main rows that need
"Δ effect-size + 95% CI" use this tool's output.

Usage:
    tools/cross_arm_bootstrap.py \\
        --baseline-arm A --baseline-runs runs/A-rep1 runs/A-rep2 runs/A-rep3 \\
        --arm B --runs runs/B-rep1 runs/B-rep2 runs/B-rep3 \\
        --arm C --runs runs/C-rep1 runs/C-rep2 runs/C-rep3 \\
        --arm D-v4 --runs runs/D-rep1 runs/D-rep2 runs/D-rep3 \\
        --metrics minflt_delta rss_kb_pre rss_kb_delta \\
        --bootstrap-iters 10000 --seed 42

Bootstrap method: paired sampling-with-replacement at per-rep granularity
(N=3 reps per arm; the bootstrap resamples 3 indices with replacement
from each arm independently and computes the difference of means). The
percentile CI is reported at α=0.05 unless --alpha overrides.

Reproducibility: --seed locks numpy.random.RandomState; output records
the seed in a comment so re-running the report regenerates identical
bounds.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np


SCHEMA_VERSION = 1
DEFAULT_METRICS = ["minflt_delta", "rss_kb_pre", "rss_kb_delta"]


def read_summary_tsv(run_dir: Path) -> Dict[str, float]:
    """Read derived/summary.tsv and return a flat dict of metric → value.

    summary.tsv format (schema=1):
        # schema=1 ...
        config<TAB>field1<TAB>field2 ...
        <name><TAB>v1<TAB>v2 ...
    The summary has one data row per run dir. We return a dict keyed by
    the field names. Missing files raise FileNotFoundError; missing
    fields raise KeyError on access.
    """
    path = run_dir / "derived" / "summary.tsv"
    if not path.exists():
        raise FileNotFoundError(f"summary.tsv not found: {path}")
    rows: List[List[str]] = []
    schema = 0
    with path.open() as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line:
                continue
            if line.startswith("#"):
                if "schema=" in line:
                    try:
                        schema = int(
                            line.split("schema=")[1].split()[0].rstrip(";")
                        )
                    except (IndexError, ValueError):
                        pass
                continue
            rows.append(line.split("\t"))
    if schema != 0 and schema != SCHEMA_VERSION:
        raise ValueError(
            f"summary.tsv at {path} has schema={schema}, expected {SCHEMA_VERSION} "
            f"or legacy=0; refusing to bootstrap on incompatible schema"
        )
    if schema == 0:
        sys.stderr.write(
            f"WARN: legacy schema=0 at {path}; assuming pre-N3 fields\n"
        )
    if len(rows) < 2:
        raise ValueError(f"summary.tsv at {path} has {len(rows)} rows; need ≥ 2")
    header, data = rows[0], rows[1]
    out: Dict[str, float] = {}
    for col, val in zip(header, data):
        try:
            out[col] = float(val)
        except (ValueError, TypeError):
            # Non-numeric (e.g. config name) silently skipped — bootstrap
            # only uses numeric metrics anyway.
            continue
    return out


def collect_arm(arm_label: str, run_dirs: List[Path]) -> Tuple[str, np.ndarray, List[str]]:
    """Read summary.tsv from each rep dir; return (label, matrix, fields).

    matrix shape: (N_reps, N_metrics). fields is the metric column order.
    Only metrics present in ALL reps are kept (intersection); others are
    warned and dropped to keep the matrix rectangular.
    """
    per_rep_dicts: List[Dict[str, float]] = []
    for d in run_dirs:
        per_rep_dicts.append(read_summary_tsv(d))
    common = set(per_rep_dicts[0].keys())
    for d in per_rep_dicts[1:]:
        common &= set(d.keys())
    if not common:
        raise ValueError(f"arm {arm_label}: no common metrics across reps")
    fields = sorted(common)
    matrix = np.array(
        [[d[f] for f in fields] for d in per_rep_dicts], dtype=np.float64
    )
    return arm_label, matrix, fields


def bootstrap_paired_diff(
    a: np.ndarray,
    b: np.ndarray,
    n_iters: int,
    rng: np.random.RandomState,
) -> Tuple[float, float, float]:
    """Bootstrap the mean of (b - a) by independent resampling.

    Returns (delta_mean, ci_low, ci_high) for the (b - a) difference of
    arm means. CI is the 2.5/97.5 percentile of the bootstrap distribution.
    """
    n_a, n_b = a.shape[0], b.shape[0]
    deltas = np.empty(n_iters, dtype=np.float64)
    for i in range(n_iters):
        sa = a[rng.randint(0, n_a, size=n_a)]
        sb = b[rng.randint(0, n_b, size=n_b)]
        deltas[i] = sb.mean() - sa.mean()
    return float(deltas.mean()), float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--baseline-arm", required=True, help="Label for the baseline arm (e.g. A)")
    p.add_argument("--baseline-runs", nargs="+", required=True, help="Per-rep run dirs for the baseline arm")
    p.add_argument(
        "--arm",
        action="append",
        required=True,
        help="Comparator arm label; pair with --runs (repeatable)",
    )
    p.add_argument(
        "--runs",
        action="append",
        nargs="+",
        required=True,
        help="Per-rep run dirs for the most-recent --arm (repeatable)",
    )
    p.add_argument(
        "--metrics",
        nargs="+",
        default=DEFAULT_METRICS,
        help=f"Metric column names (default: {DEFAULT_METRICS})",
    )
    p.add_argument("--bootstrap-iters", type=int, default=10000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--output", type=Path, default=None, help="Output TSV (default: stdout)")
    args = p.parse_args()

    if len(args.arm) != len(args.runs):
        p.error("--arm and --runs must be paired the same number of times")

    rng = np.random.RandomState(args.seed)

    baseline_label, baseline_matrix, baseline_fields = collect_arm(
        args.baseline_arm, [Path(r) for r in args.baseline_runs]
    )

    all_results: List[Dict[str, str]] = []
    for arm_label, run_list in zip(args.arm, args.runs):
        cmp_label, cmp_matrix, cmp_fields = collect_arm(
            arm_label, [Path(r) for r in run_list]
        )
        common_fields = [f for f in baseline_fields if f in cmp_fields]
        if not all(m in common_fields for m in args.metrics):
            missing = set(args.metrics) - set(common_fields)
            sys.stderr.write(f"WARN: arm {arm_label} missing {missing}\n")
        for metric in args.metrics:
            if metric not in common_fields:
                continue
            i_b = baseline_fields.index(metric)
            i_c = cmp_fields.index(metric)
            delta_mean, ci_low, ci_high = bootstrap_paired_diff(
                baseline_matrix[:, i_b],
                cmp_matrix[:, i_c],
                args.bootstrap_iters,
                rng,
            )
            mean_a = float(baseline_matrix[:, i_b].mean())
            std_a = float(baseline_matrix[:, i_b].std(ddof=1)) if baseline_matrix.shape[0] >= 2 else 0.0
            mean_c = float(cmp_matrix[:, i_c].mean())
            std_c = float(cmp_matrix[:, i_c].std(ddof=1)) if cmp_matrix.shape[0] >= 2 else 0.0
            all_results.append({
                "baseline_arm": baseline_label,
                "compare_arm": arm_label,
                "metric": metric,
                "n_baseline": str(baseline_matrix.shape[0]),
                "n_compare": str(cmp_matrix.shape[0]),
                "mean_baseline": f"{mean_a:.4g}",
                "sd_baseline": f"{std_a:.4g}",
                "mean_compare": f"{mean_c:.4g}",
                "sd_compare": f"{std_c:.4g}",
                "delta_mean": f"{delta_mean:.4g}",
                "ci_low": f"{ci_low:.4g}",
                "ci_high": f"{ci_high:.4g}",
            })

    headers = [
        "baseline_arm", "compare_arm", "metric",
        "n_baseline", "n_compare",
        "mean_baseline", "sd_baseline",
        "mean_compare", "sd_compare",
        "delta_mean", "ci_low", "ci_high",
    ]

    out_lines: List[str] = []
    out_lines.append(
        f"# schema={SCHEMA_VERSION}\tbootstrap_iters={args.bootstrap_iters}; "
        f"alpha={args.alpha}; seed={args.seed}; method=paired_resample"
    )
    out_lines.append("\t".join(headers))
    for row in all_results:
        out_lines.append("\t".join(row[h] for h in headers))

    text = "\n".join(out_lines) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
