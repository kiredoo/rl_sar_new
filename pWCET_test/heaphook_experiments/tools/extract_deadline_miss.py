#!/usr/bin/env python3
"""Extract deadline-miss rate per arm from existing CARET stats_path.yaml.

Phase 1 (post-hoc, no new reps): use percentile data already in stats_path.yaml
to estimate miss rate at multiple deadline thresholds. Where p95/p99/max sit
relative to a deadline gives us the interpolated miss rate.

Output: schema=1 TSV with one row per (rep, deadline_ms).
Columns: rep_dir, arm, deadline_ms, n_instances, mean_ms, p50_ms, p95_ms, p99_ms, max_ms,
         miss_rate_estimate, miss_rate_method.

Method "exact" — when p95 >= deadline we know exactly miss_rate >= 0.05.
Method "interp" — when deadline between two known percentiles, linearly interpolate.
Method "below_p99" — deadline > p99 but ≤ max → miss_rate in (0, 0.01].
Method "above_max" — deadline > max → miss_rate = 0 (no miss).
"""
import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Try: python3 -m pip install --user pyyaml", file=sys.stderr)
    sys.exit(1)


REPO = Path(__file__).resolve().parent.parent
DEFAULT_REPS_GLOB = "runs/20260505-1*_layer2-cv-*-canonical-*/raw/*/result.json"
DEFAULT_REPS_GLOB_2 = "runs/20260506-0*_layer2-cv-*-canonical-*-rss/raw/*/result.json"

# 自駕 LiDAR sensing chain deadlines, ms
# 10 Hz cycle = 100 ms per frame; common operational deadlines:
DEFAULT_DEADLINES_MS = [100, 150, 200, 250, 300, 500]


def find_stats_yaml_for_rep(rep_dir: Path) -> Path | None:
    """observe_rep.py stores stats yaml path under result.json -> trace.stats_yaml."""
    arm_dirs = list((rep_dir / "raw").iterdir()) if (rep_dir / "raw").exists() else []
    for arm_dir in arm_dirs:
        rj = arm_dir / "result.json"
        if not rj.exists():
            continue
        with open(rj) as f:
            data = json.load(f)
        stats_path = (data.get("trace") or {}).get("stats_yaml")
        if stats_path and Path(stats_path).exists():
            return Path(stats_path)
    return None


def estimate_miss_rate(deadline_ms: float, p50: float, p95: float, p99: float, mx: float):
    """Estimate fraction of instances exceeding deadline_ms using percentile interpolation."""
    if deadline_ms >= mx:
        return 0.0, "above_max"
    if deadline_ms >= p99:
        # Between p99 and max — miss_rate in (0, 0.01]
        if mx == p99:
            return 0.005, "interp_p99_max"
        frac_above_p99 = (mx - deadline_ms) / (mx - p99)
        return 0.01 * frac_above_p99, "interp_p99_max"
    if deadline_ms >= p95:
        # Between p95 and p99 — miss_rate in (0.01, 0.05]
        frac = (p99 - deadline_ms) / (p99 - p95) if p99 != p95 else 0.5
        return 0.01 + 0.04 * frac, "interp_p95_p99"
    if deadline_ms >= p50:
        # Between p50 and p95 — miss_rate in (0.05, 0.50]
        frac = (p95 - deadline_ms) / (p95 - p50) if p95 != p50 else 0.5
        return 0.05 + 0.45 * frac, "interp_p50_p95"
    # Below p50 — miss_rate > 0.50
    if deadline_ms <= 0:
        return 1.0, "below_zero"
    return 0.5 + 0.5 * (1.0 - deadline_ms / p50), "below_p50"


def parse_stats_path_yaml(yaml_path: Path):
    """Return list of (target_path_name, stats_dict)."""
    with open(yaml_path) as f:
        data = yaml.safe_load(f) or []
    result = []
    for entry in data:
        name = entry.get("target_path_name", "")
        stats = {
            "n_instances": entry.get("e2e_best_row_count", 0),
            "mean_ms": entry.get("best_avg", 0),
            "std_ms": entry.get("best_std", 0),
            "p50_ms": entry.get("best_p50", 0),
            "p95_ms": entry.get("best_p95", 0),
            "p99_ms": entry.get("best_p99", 0),
            "max_ms": entry.get("best_max", 0),
        }
        result.append((name, stats))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps-root", default=str(REPO / "runs"),
                    help="Root containing run dirs (default: runs/)")
    ap.add_argument("--rep-pattern", action="append",
                    default=None,
                    help="glob under reps-root; can repeat. Default: 18 canonical reps from 20260505/06.")
    ap.add_argument("--deadlines-ms", type=float, nargs="+",
                    default=DEFAULT_DEADLINES_MS,
                    help="Deadline thresholds in ms.")
    ap.add_argument("--output", default=str(REPO / "reports" / "figures" / "deadline_miss_n18.tsv"),
                    help="Output TSV path.")
    args = ap.parse_args()

    if args.rep_pattern is None:
        patterns = [
            "20260505-17*_layer2-cv-*-canonical-*",
            "20260506-0*_layer2-cv-*-canonical-*-rss",
            "20260506-1*_layer2-*-canonical-rep*-baseline",
        ]
    else:
        patterns = args.rep_pattern

    reps_root = Path(args.reps_root)
    rep_dirs = []
    for pat in patterns:
        rep_dirs.extend(sorted(reps_root.glob(pat)))
    rep_dirs = [d for d in rep_dirs if d.is_dir()]
    print(f"Found {len(rep_dirs)} rep dirs", file=sys.stderr)

    rows = []
    for rep_dir in rep_dirs:
        # Identify arm from dir name: layer2-cv-{a|b|d}-canonical or layer2-{a|b|d}-canonical
        nm = rep_dir.name.lower()
        if "-cv-a-" in nm or "layer2-a-canonical" in nm:
            arm = "A"
        elif "-cv-b-" in nm or "layer2-b-canonical" in nm:
            arm = "B"
        elif "-cv-d-" in nm or "layer2-d-canonical" in nm:
            arm = "D"
        else:
            arm = "?"

        stats_yaml = find_stats_yaml_for_rep(rep_dir)
        if stats_yaml is None:
            print(f"  skip {rep_dir.name}: no stats_path.yaml", file=sys.stderr)
            continue

        try:
            paths = parse_stats_path_yaml(stats_yaml)
        except Exception as e:
            print(f"  skip {rep_dir.name}: parse error {e}", file=sys.stderr)
            continue

        for path_name, stats in paths:
            n = stats["n_instances"]
            if n < 5:
                continue
            for dl in args.deadlines_ms:
                miss_rate, method = estimate_miss_rate(
                    dl, stats["p50_ms"], stats["p95_ms"], stats["p99_ms"], stats["max_ms"]
                )
                rows.append({
                    "rep_dir": rep_dir.name,
                    "arm": arm,
                    "chain": path_name,
                    "deadline_ms": dl,
                    "n_instances": n,
                    "mean_ms": round(stats["mean_ms"], 3),
                    "p50_ms": round(stats["p50_ms"], 3),
                    "p95_ms": round(stats["p95_ms"], 3),
                    "p99_ms": round(stats["p99_ms"], 3),
                    "max_ms": round(stats["max_ms"], 3),
                    "miss_rate_est": round(miss_rate, 4),
                    "method": method,
                })

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        print("No rows produced; check rep dirs / stats_path.yaml", file=sys.stderr)
        sys.exit(2)
    cols = list(rows[0].keys())
    with open(out_path, "w") as f:
        f.write("# schema=1  source=tools/extract_deadline_miss.py  date=2026-05-06\n")
        f.write("# Method: percentile interpolation from CARET stats_path.yaml\n")
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r[c]) for c in cols) + "\n")
    print(f"Wrote {len(rows)} rows × {len(cols)} cols to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
