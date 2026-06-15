#!/usr/bin/env python3
"""Extract per-chain CARET e2e latency + CV from caret_report stats_path.yaml.

Usage:
    tools/extract_chain_jitter.py \\
        --caret-report-output ~/repo/caret_report/sample_autoware/output_storage/<tag> \\
        --output reports/figures/chain_jitter_<run>.tsv \\
        [--lang en|zh-TW]

Output is a schema=1 TSV with one row per target_path_name found in the YAML:

    chain_name  n_samples  best_avg_ms  best_std_ms  best_p50_ms  best_p95_ms
    best_p99_ms  cv_best  worst_avg_ms  worst_std_ms  cv_worst

CV = std / mean (Coefficient of Variation, dimensionless). The product KPI
for Autoware Universe determinism is e2e CV < 0.15 over the longest chain
(see reports/caret_jitter_gate.md).

YAML field reference (per-chain dict, all latency in milliseconds):
    target_path_name        chain identifier
    e2e_best_row_count      sample count for the "best" (full-coverage) bucket
    best_avg / best_std     mean / std-dev for "best" bucket
    best_p50/p95/p99        percentiles for "best" bucket
    worst_avg / worst_std   mean / std-dev for "worst" bucket (often missing
                            on short traces — emitted as empty cells)
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import sys
from pathlib import Path
from typing import Dict, List

try:
    import yaml  # PyYAML, ships with the caret_report venv requirements.
except ImportError as e:  # pragma: no cover
    print(
        "[ERR] PyYAML not importable. Activate caret_report venv first:\n"
        "      source ~/repo/caret_report/venv/bin/activate",
        file=sys.stderr,
    )
    raise SystemExit(2) from e


SCHEMA = 1
TOOL_NAME = "extract_chain_jitter.py"

I18N: Dict[str, Dict[str, str]] = {
    "header_comment": {
        "en":    "Per-chain e2e latency + CV from caret_report stats_path.yaml",
        "zh-TW": "從 caret_report stats_path.yaml 萃取每條 chain 的 e2e 延遲 + CV",
    },
    "source_label": {
        "en":    "source",
        "zh-TW": "來源",
    },
    "tool_label": {
        "en":    "tool",
        "zh-TW": "工具",
    },
    "generated_label": {
        "en":    "generated_at",
        "zh-TW": "產生時間",
    },
}

COLS = [
    "chain_name",
    "n_samples_best",
    "best_avg_ms",
    "best_std_ms",
    "best_p50_ms",
    "best_p95_ms",
    "best_p99_ms",
    "cv_best",
    "worst_avg_ms",
    "worst_std_ms",
    "cv_worst",
]


def _safe_float(v):
    """Return float(v) or NaN for missing / non-numeric cells."""
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return math.nan
        return f
    except (TypeError, ValueError):
        return math.nan


def _div(num, den):
    if den is None or _safe_float(den) == 0 or math.isnan(_safe_float(den)):
        return math.nan
    if num is None or math.isnan(_safe_float(num)):
        return math.nan
    return _safe_float(num) / _safe_float(den)


def _fmt(v) -> str:
    """Empty cell for NaN, else 6-sig-fig number."""
    f = _safe_float(v)
    if math.isnan(f):
        return ""
    return f"{f:.6g}"


def find_stats_yaml(out_dir: Path) -> Path:
    # Two layouts observed:
    #   (a) report_session-*/analyze_path/stats_path.yaml  (legacy AAA dummy)
    #   (b) analyze_path/stats_path.yaml                   (current batch_run.sh output)
    # Match both via recursive glob.
    candidates = sorted(out_dir.rglob("analyze_path/stats_path.yaml"))
    if not candidates:
        raise FileNotFoundError(
            f"no */analyze_path/stats_path.yaml under {out_dir}"
        )
    if len(candidates) > 1:
        print(
            f"[WARN] {len(candidates)} stats_path.yaml under {out_dir}; "
            f"using first: {candidates[0].relative_to(out_dir)}",
            file=sys.stderr,
        )
    return candidates[0]


def parse_yaml(path: Path) -> List[dict]:
    with path.open() as f:
        data = yaml.safe_load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected top-level list, got {type(data).__name__}")
    return data


def row_for(chain: dict) -> List[str]:
    name = chain.get("target_path_name", "")
    n = chain.get("e2e_best_row_count")
    best_avg = chain.get("best_avg")
    best_std = chain.get("best_std")
    worst_avg = chain.get("worst_avg")
    worst_std = chain.get("worst_std")

    return [
        str(name),
        _fmt(n),
        _fmt(best_avg),
        _fmt(best_std),
        _fmt(chain.get("best_p50")),
        _fmt(chain.get("best_p95")),
        _fmt(chain.get("best_p99")),
        _fmt(_div(best_std, best_avg)),
        _fmt(worst_avg),
        _fmt(worst_std),
        _fmt(_div(worst_std, worst_avg)),
    ]


def emit_tsv(rows: List[List[str]], out_path: Path, source: Path, lang: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    L = lambda key: I18N[key][lang]
    with out_path.open("w") as f:
        f.write(f"# schema={SCHEMA}\n")
        f.write(f"# {L('header_comment')}\n")
        f.write(f"# {L('source_label')}={source}\n")
        f.write(f"# {L('tool_label')}={TOOL_NAME}\n")
        f.write(f"# {L('generated_label')}={now}\n")
        f.write("\t".join(COLS) + "\n")
        for r in rows:
            f.write("\t".join(r) + "\n")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--caret-report-output", required=True, type=Path,
                   help="output_storage/<tag>/ directory produced by batch_run.sh")
    p.add_argument("--output", required=True, type=Path,
                   help="schema=1 TSV path to write (parent dirs auto-created)")
    p.add_argument("--lang", choices=("en", "zh-TW"), default="en",
                   help="header-comment language (data is language-neutral)")
    args = p.parse_args()

    out_dir: Path = args.caret_report_output.expanduser().resolve()
    if not out_dir.is_dir():
        print(f"[ERR] not a directory: {out_dir}", file=sys.stderr)
        return 2

    yaml_path = find_stats_yaml(out_dir)
    chains = parse_yaml(yaml_path)
    if not chains:
        print(f"[ERR] {yaml_path}: zero chains parsed", file=sys.stderr)
        return 3

    rows = [row_for(c) for c in chains]
    emit_tsv(rows, args.output.expanduser().resolve(), yaml_path, args.lang)
    print(f"[OK] wrote {args.output} ({len(rows)} chain rows from {yaml_path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
