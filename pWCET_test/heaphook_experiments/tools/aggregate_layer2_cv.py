#!/usr/bin/env python3
"""Aggregate per-rep chain_jitter TSVs into a cross-arm CV table.

Usage:
    tools/aggregate_layer2_cv.py \\
        --rep <arm>:<run_id>:<jitter.tsv> \\
        [--rep ...] \\
        --output reports/figures/cross_arm_cv.tsv \\
        [--lang en|zh-TW]

Each --rep is a colon-triple. The script reads each TSV, joins on chain_name,
groups by arm, and emits per-arm mean ± SD per metric (best_avg_ms / cv_best /
worst_avg_ms / cv_worst). Empty / NaN cells are excluded from aggregation.

Output format (schema=1 TSV):
    chain_name  arm  n_reps  mean_avg_ms  std_avg_ms  mean_cv  std_cv  ...
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SCHEMA = 1
TOOL_NAME = "aggregate_layer2_cv.py"

I18N: Dict[str, Dict[str, str]] = {
    "header": {
        "en":    "Cross-arm chain CV aggregate from layer-2 reps",
        "zh-TW": "跨 arm chain CV 跨 reps 整合（Layer-2 e2e jitter）",
    },
    "tool_label":      {"en": "tool",         "zh-TW": "工具"},
    "generated_label": {"en": "generated_at", "zh-TW": "產生時間"},
    "input_label":     {"en": "inputs",       "zh-TW": "輸入"},
}

NUMERIC_COLS = [
    "best_avg_ms", "best_std_ms", "best_p50_ms", "best_p95_ms", "best_p99_ms",
    "cv_best", "worst_avg_ms", "worst_std_ms", "cv_worst",
]


def parse_rep(spec: str) -> Tuple[str, str, Path]:
    parts = spec.split(":", 2)
    if len(parts) != 3:
        raise SystemExit(f"[ERR] --rep expects arm:run_id:tsv, got: {spec}")
    arm, run_id, tsv = parts
    return arm, run_id, Path(tsv)


def safe_float(v: str) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except ValueError:
        return None


def read_tsv(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open() as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            header = line.rstrip("\n").split("\t")
            break
        else:
            return rows
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            cells = line.rstrip("\n").split("\t")
            cells.extend([""] * (len(header) - len(cells)))
            rows.append(dict(zip(header, cells)))
    return rows


def aggregate(rep_specs: List[Tuple[str, str, Path]]) -> List[Dict[str, str]]:
    # bucket: (chain_name, arm) -> list of {col: float} from each rep
    bucket: Dict[Tuple[str, str], List[Dict[str, Optional[float]]]] = defaultdict(list)
    sources: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    for arm, run_id, tsv in rep_specs:
        if not tsv.is_file():
            print(f"[WARN] missing TSV: {tsv}", file=sys.stderr)
            continue
        for row in read_tsv(tsv):
            chain = row.get("chain_name", "?")
            vals = {c: safe_float(row.get(c, "")) for c in NUMERIC_COLS}
            bucket[(chain, arm)].append(vals)
            sources[(chain, arm)].append(run_id)

    out_rows: List[Dict[str, str]] = []
    for (chain, arm), reps in sorted(bucket.items()):
        n_reps = len(reps)
        row: Dict[str, str] = {"chain_name": chain, "arm": arm,
                               "n_reps": str(n_reps),
                               "run_ids": ",".join(sources[(chain, arm)])}
        for col in NUMERIC_COLS:
            valid = [r[col] for r in reps if r[col] is not None]
            if not valid:
                row[f"mean_{col}"] = ""
                row[f"std_{col}"] = ""
                row[f"n_valid_{col}"] = "0"
                continue
            row[f"mean_{col}"] = f"{statistics.mean(valid):.6g}"
            row[f"std_{col}"] = (
                f"{statistics.stdev(valid):.6g}" if len(valid) >= 2 else ""
            )
            row[f"n_valid_{col}"] = str(len(valid))
        out_rows.append(row)
    return out_rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--rep", action="append", required=True, metavar="arm:run_id:tsv",
                   help="repeatable; each entry colon-separated arm:run_id:tsv-path")
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--lang", choices=("en", "zh-TW"), default="en")
    args = p.parse_args()

    rep_specs = [parse_rep(s) for s in args.rep]
    rows = aggregate(rep_specs)
    if not rows:
        print("[ERR] zero rows aggregated", file=sys.stderr)
        return 2

    L = lambda k: I18N[k][args.lang]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    cols = ["chain_name", "arm", "n_reps", "run_ids"]
    for c in NUMERIC_COLS:
        cols += [f"mean_{c}", f"std_{c}", f"n_valid_{c}"]
    with args.output.open("w") as f:
        f.write(f"# schema={SCHEMA}\n")
        f.write(f"# {L('header')}\n")
        f.write(f"# {L('tool_label')}={TOOL_NAME}\n")
        f.write(f"# {L('generated_label')}={dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}\n")
        f.write(f"# {L('input_label')}=" + "; ".join(s[2].name for s in rep_specs) + "\n")
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(r.get(c, "") for c in cols) + "\n")
    print(f"[OK] wrote {args.output} ({len(rows)} (chain,arm) groups)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
