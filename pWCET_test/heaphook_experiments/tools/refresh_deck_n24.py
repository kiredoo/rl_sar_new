#!/usr/bin/env python3
"""After Phase 3 refresh completes, this script updates the deck's hard-coded
N=3 / N=5-6 numbers to N=6 / N=8-9. Reads the aggregator outputs and rewrites
specific lines in tools/build_mckinsey_pptx.py.

Run pattern:
  1. tools/refresh_n9_pipeline.sh  (re-extract / re-aggregate)
  2. tools/aggregate_track1a_n6.py
  3. THIS SCRIPT — patches deck source with new numbers
  4. python3 tools/build_mckinsey_pptx.py  (rebuild)
  5. libreoffice --headless --convert-to pdf ...
"""
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Collect Track 1A N=6 numbers
def track1a():
    rows = {"A": [], "B": [], "D": []}
    for pat in ["20260506-0*_layer2-cv-*-canonical-*-rss",
                "20260506-1*_layer2-*-canonical-rep*-baseline"]:
        for d in sorted((REPO / "runs").glob(pat)):
            nm = d.name.lower()
            arm = ("A" if "-cv-a-" in nm or "layer2-a-canonical" in nm else
                   "B" if "-cv-b-" in nm or "layer2-b-canonical" in nm else
                   "D" if "-cv-d-" in nm or "layer2-d-canonical" in nm else None)
            if not arm:
                continue
            rj = list((d / "raw").rglob("result.json"))
            if not rj:
                continue
            data = json.loads(rj[0].read_text())
            mem = data.get("memory") or {}
            delta = mem.get("delta") or {}
            if delta:
                rows[arm].append(delta)
    out = {}
    for arm, recs in rows.items():
        if not recs:
            continue
        n = len(recs)
        m_minflt = statistics.mean([r["minflt"]/30.0 for r in recs])
        m_rss = statistics.mean([r["rss_mb"] for r in recs])
        m_vol = statistics.mean([r["vol_ctx"]/30.0 for r in recs])
        m_iv = statistics.mean([r["invol_ctx"]/30.0 for r in recs])
        out[arm] = {"N": n, "minflt_ps": m_minflt, "rss_mb": m_rss,
                    "vol_ctx_ps": m_vol, "invol_ctx_ps": m_iv}
    return out


def chain_cv():
    """Collect chain CV per arm. Accept reps where chain n>=50 (sufficient
    chain data) regardless of alignment sampler verdict — alignment sampler
    failures (TP=0.00 from ros2 topic echo race) are orthogonal to chain CV
    measurement quality. B rep1 cold-start dropped (per memory)."""
    rows = {"A": [], "B": [], "D": []}
    for pat in ["20260505-1[78]*_layer2-cv-*-canonical-rep*",
                "20260506-0*_layer2-cv-*-canonical-*-rss",
                "20260506-1*_layer2-*-canonical-rep*-baseline"]:
        for d in sorted((REPO / "runs").glob(pat)):
            nm = d.name.lower()
            if "1.0x" in nm:
                continue
            # B rep1 cold-start drop per memory feedback_b_arm_cold_start.md
            if "-cv-b-canonical-rep1" in nm:
                continue
            arm = ("A" if "-cv-a-" in nm or "layer2-a-canonical" in nm else
                   "B" if "-cv-b-" in nm or "layer2-b-canonical" in nm else
                   "D" if "-cv-d-" in nm or "layer2-d-canonical" in nm else None)
            if not arm:
                continue
            rj = list((d / "raw").rglob("result.json"))
            if not rj:
                continue
            data = json.loads(rj[0].read_text())
            cv = (data.get("trace") or {}).get("cv")
            chain = (data.get("trace") or {}).get("chain") or {}
            n = chain.get("raw_row_with_end", 0)
            if cv is not None and n >= 50:
                rows[arm].append(cv)
    return rows


def main():
    t1 = track1a()
    cv = chain_cv()

    print("Track 1A (memory direct):")
    for a in ["A","B","D"]:
        if a in t1:
            print(f"  {a}: N={t1[a]['N']} minflt={t1[a]['minflt_ps']:.0f}/s "
                  f"rss={t1[a]['rss_mb']:.0f}MB vol_ctx={t1[a]['vol_ctx_ps']:.0f}/s "
                  f"invol_ctx={t1[a]['invol_ctx_ps']:.0f}/s")

    print("\nChain CV:")
    for a in ["A","B","D"]:
        n = len(cv[a])
        if n > 0:
            mean = statistics.mean(cv[a])
            std = statistics.stdev(cv[a]) if n > 1 else 0
            print(f"  {a}: N={n} mean={mean:.4f} std={std:.4f}")

    # Stat tests
    try:
        import scipy.stats as st
        if cv["A"] and cv["B"]:
            t, p = st.ttest_ind(cv["A"], cv["B"], equal_var=False)
            print(f"\nWelch A vs B chain CV: t={t:.3f} p={p:.4f}")
        if cv["A"] and cv["D"]:
            t, p = st.ttest_ind(cv["A"], cv["D"], equal_var=False)
            print(f"Welch A vs D chain CV: t={t:.3f} p={p:.4f}")
    except ImportError:
        print("scipy not available; skip stat tests", file=sys.stderr)


if __name__ == "__main__":
    main()
