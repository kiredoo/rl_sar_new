#!/usr/bin/env python3
"""Evaluate Phase 2.5a gate (rep4-rep7 against pre-registered criteria).

Reads `runs/<id>/derived/summary.tsv` for every config in `configs.tsv`
whose name matches `baseline-frag-rep<N>` (N in 4..7), applies criteria
C1-C6 from `reports/frag_2_5a_gate.md` §3, and prints PASS / PARTIAL
PASS / FAIL.

The thresholds and historical baselines are HARD-CODED here to mirror
the pre-registered gate document. **Do not edit them after the gate
document has been committed**; that would be post-hoc gerrymandering
and defeats the purpose of pre-registration. If the gate needs
revision, write a new gate doc (e.g. 2.5a_v2) and a new evaluator,
and supersede this one explicitly.

Usage:
    tools/eval_2_5a_gate.py                  # default project root
    tools/eval_2_5a_gate.py --root <dir>     # alt root
    tools/eval_2_5a_gate.py --json           # machine-readable output

Exit code: 0 PASS, 1 FAIL, 2 PARTIAL PASS, 3 missing data, 4 misuse.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

# --- pre-registered baselines and thresholds (frag_2_5a_gate.md §3) ---

BASELINE = {
    "minflt_delta_mean": 1_268_312,
    "rss_kb_delta_mean": 1_347_492,
    "rss_kb_pre_mean":   12_830_393,
}
THRESHOLDS_PCT = {
    "C1_minflt":      0.10,  # ±10 %
    "C2_rss_delta":   0.10,
    "C3_rss_pre":     0.05,  # ±5 %  (steady-state is tighter)
}
ABORT_CEILING = 4
PID_COVERAGE_FLOOR = 0.90

REP_NAME_RE = re.compile(r"^baseline-frag-rep(?P<n>[4567])$")


# --- summary.tsv reader (mirrors aggregate_configs.read_summary) ------

SUMMARY_TSV_SCHEMA = 1


def _read_summary(run_dir: Path, arm: str) -> dict | None:
    tsv = run_dir / "derived" / "summary.tsv"
    if not tsv.exists():
        return None
    schema = None
    lines: list[str] = []
    with tsv.open() as f:
        for raw in f:
            s = raw.rstrip("\n")
            if s.startswith("#"):
                m = s.lstrip("#").strip()
                if m.startswith("schema="):
                    try:
                        schema = int(m.split("=", 1)[1])
                    except ValueError:
                        pass
                continue
            lines.append(s)
    if schema is not None and schema != SUMMARY_TSV_SCHEMA:
        raise SystemExit(f"{tsv}: schema={schema}, expected {SUMMARY_TSV_SCHEMA}")
    if not lines:
        return None
    header = lines[0].split("\t")
    for ln in lines[1:]:
        parts = ln.split("\t")
        if parts and parts[0] == arm:
            return dict(zip(header, parts))
    return None


def _read_frag_summary(run_dir: Path) -> list[str]:
    """Return list of distinct PIDs in derived/frag_summary.tsv."""
    p = run_dir / "derived" / "frag_summary.tsv"
    if not p.exists():
        return []
    pids: set[str] = set()
    with p.open() as f:
        rows = [ln.rstrip("\n") for ln in f if ln.strip() and not ln.startswith("#")]
    if not rows:
        return []
    header = rows[0].split("\t")
    if "pid" not in header:
        return []
    pid_idx = header.index("pid")
    for ln in rows[1:]:
        parts = ln.split("\t")
        if len(parts) > pid_idx:
            pids.add(parts[pid_idx])
    return sorted(pids)


# --- per-rep evaluation ----------------------------------------------

def _within(value: float, mean: float, pct: float) -> tuple[bool, float]:
    lo = mean * (1 - pct)
    hi = mean * (1 + pct)
    return (lo <= value <= hi), abs(value - mean) / mean if mean else 0.0


def evaluate_rep(name: str, run_id: str, root: Path) -> dict:
    rec: dict = {"name": name, "run_id": run_id, "criteria": {}, "missing": False}
    run_dir = root / "runs" / run_id
    summary = _read_summary(run_dir, "A")
    if summary is None:
        rec["missing"] = True
        return rec

    minflt = int(summary.get("minflt_delta", 0))
    rss_d = int(summary.get("rss_kb_delta", 0))
    rss_pre = int(summary.get("rss_kb_pre", 0))
    aborts = int(summary.get("aborts", 0))
    nprocs = int(summary.get("nprocs", 0))

    c1, c1_dev = _within(minflt, BASELINE["minflt_delta_mean"], THRESHOLDS_PCT["C1_minflt"])
    c2, c2_dev = _within(rss_d,  BASELINE["rss_kb_delta_mean"], THRESHOLDS_PCT["C2_rss_delta"])
    c3, c3_dev = _within(rss_pre, BASELINE["rss_kb_pre_mean"],  THRESHOLDS_PCT["C3_rss_pre"])
    c4 = aborts <= ABORT_CEILING

    frag_pids = _read_frag_summary(run_dir)
    coverage = (len(frag_pids) / nprocs) if nprocs else 0.0
    c5 = coverage >= PID_COVERAGE_FLOOR
    c6 = bool(frag_pids)  # any non-zero coverage means the join key exists

    rec["values"] = {
        "minflt_delta": minflt, "rss_kb_delta": rss_d, "rss_kb_pre": rss_pre,
        "aborts": aborts, "nprocs": nprocs, "frag_pids": len(frag_pids),
        "coverage_pct": round(coverage * 100, 1),
    }
    rec["criteria"] = {
        "C1_minflt": {"pass": c1, "dev_pct": round(c1_dev * 100, 2)},
        "C2_rss_delta": {"pass": c2, "dev_pct": round(c2_dev * 100, 2)},
        "C3_rss_pre": {"pass": c3, "dev_pct": round(c3_dev * 100, 2)},
        "C4_aborts": {"pass": c4, "value": aborts},
        "C5_coverage": {"pass": c5, "value": round(coverage * 100, 1)},
        "C6_frag_join": {"pass": c6},
    }
    rec["pass"] = all(v["pass"] for v in rec["criteria"].values())
    return rec


# --- top-level decision ----------------------------------------------

def decide(reps: list[dict]) -> tuple[str, str]:
    """Return (decision, rationale). decision in PASS / PARTIAL_PASS / FAIL / NO_DATA."""
    present = [r for r in reps if not r["missing"]]
    if not present:
        return "NO_DATA", "no rep4-rep7 runs found in configs.tsv"

    fails = [r for r in present if not r["pass"]]
    if not fails:
        return "PASS", f"{len(present)}/{len(present)} reps satisfied all criteria"

    # PARTIAL PASS = exactly 1 outlier and its worst deviation < 1.5× threshold.
    # Worst deviation = max dev_pct across C1/C2/C3, normalised to threshold.
    if len(fails) == 1:
        out = fails[0]
        worst = 0.0
        thresh = 1.0
        for k, t_pct in [("C1_minflt", THRESHOLDS_PCT["C1_minflt"]),
                         ("C2_rss_delta", THRESHOLDS_PCT["C2_rss_delta"]),
                         ("C3_rss_pre", THRESHOLDS_PCT["C3_rss_pre"])]:
            c = out["criteria"][k]
            if not c["pass"]:
                ratio = c["dev_pct"] / 100 / t_pct
                if ratio > worst:
                    worst = ratio
                    thresh = t_pct
        if worst <= 1.5:
            return "PARTIAL_PASS", (
                f"1 outlier ({out['name']}), worst deviation {worst:.2f}× threshold "
                f"{thresh*100:.0f}% — within 1.5× rule"
            )

    return "FAIL", (
        f"{len(fails)} of {len(present)} reps failed; "
        f"failing reps: {', '.join(r['name'] for r in fails)}"
    )


# --- I/O glue --------------------------------------------------------

def read_configs(root: Path) -> list[dict]:
    p = root / "configs.tsv"
    if not p.exists():
        raise SystemExit(f"configs.tsv missing at {p}")
    with p.open() as f:
        rows = [ln for ln in f if ln.strip() and not ln.startswith("#")]
    reader = csv.DictReader(rows, delimiter="\t")
    return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in reader]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv[1:])

    configs = read_configs(args.root)
    rep_rows = [c for c in configs if REP_NAME_RE.match(c["name"])]
    rep_rows.sort(key=lambda r: int(REP_NAME_RE.match(r["name"]).group("n")))

    reps: list[dict] = []
    for c in rep_rows:
        if c["run_id"] in ("", "-"):
            reps.append({"name": c["name"], "run_id": "-", "missing": True, "criteria": {}})
            continue
        reps.append(evaluate_rep(c["name"], c["run_id"], args.root))

    decision, rationale = decide(reps)

    if args.json:
        print(json.dumps({"decision": decision, "rationale": rationale, "reps": reps}, indent=2))
    else:
        print(f"=== Phase 2.5a gate evaluation ===")
        print(f"baselines (from gate doc §3):")
        for k, v in BASELINE.items():
            print(f"  {k:<20s} {v:>14,d}")
        print()
        for r in reps:
            if r["missing"]:
                print(f"  {r['name']:<22s}  [no run yet — configs.tsv run_id is '-']")
                continue
            tick = "PASS" if r["pass"] else "FAIL"
            print(f"  {r['name']:<22s}  {tick}   ({r['run_id']})")
            for k, v in r["criteria"].items():
                t = "y" if v["pass"] else "n"
                detail = ""
                if "dev_pct" in v:
                    detail = f"dev {v['dev_pct']:>5.2f}%"
                elif "value" in v:
                    detail = f"value {v['value']}"
                print(f"      {t}  {k:<14s} {detail}")
        print()
        print(f"decision: {decision}")
        print(f"  → {rationale}")

    return {"PASS": 0, "FAIL": 1, "PARTIAL_PASS": 2, "NO_DATA": 3}.get(decision, 4)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
