#!/usr/bin/env python3
"""Aggregate Track 1A (memory direct) metrics across all 12 reps with rss_pre/post:
- 9 from 20260506-08*-rss
- 9 from 20260506-1159_*-baseline
Produces cross-arm summary with mean/std for Δminflt, ΔRSS, Δvol_ctx, Δinvol_ctx.
"""
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

PATTERNS = [
    "20260506-0*_layer2-cv-*-canonical-*-rss",
    "20260506-1*_layer2-*-canonical-rep*-baseline",
]


def main():
    rows = {"A": [], "B": [], "D": []}
    for pat in PATTERNS:
        for d in sorted((REPO / "runs").glob(pat)):
            nm = d.name.lower()
            arm = ("A" if "-cv-a-" in nm or "layer2-a-canonical" in nm else
                   "B" if "-cv-b-" in nm or "layer2-b-canonical" in nm else
                   "D" if "-cv-d-" in nm or "layer2-d-canonical" in nm else None)
            if not arm:
                continue
            rj_paths = list((d / "raw").rglob("result.json"))
            if not rj_paths:
                continue
            data = json.loads(rj_paths[0].read_text())
            mem = data.get("memory") or {}
            delta = (mem.get("delta") or {})
            if not delta:
                continue
            rows[arm].append({
                "rep": d.name,
                "minflt_ps": delta.get("minflt", 0) / 30.0,
                "rss_mb": delta.get("rss_mb", 0),
                "vol_ctx_ps": delta.get("vol_ctx", 0) / 30.0,
                "invol_ctx_ps": delta.get("invol_ctx", 0) / 30.0,
            })

    print("Track 1A cross-arm (per-second rate from 30s window):\n")
    print(f"{'arm':<3} {'N':>3} | {'Δminflt/s':>14} | {'ΔRSS MB':>12} | {'Δvol_ctx/s':>14} | {'Δinvol_ctx/s':>14}")
    print("-" * 80)
    for arm in ["A", "B", "D"]:
        if not rows[arm]:
            print(f"{arm:<3} 0  | (no data)")
            continue
        m = rows[arm]
        n = len(m)
        for k_ps, k in [("minflt_ps", "Δminflt/s"), ("rss_mb", "ΔRSS MB"),
                         ("vol_ctx_ps", "Δvol_ctx/s"), ("invol_ctx_ps", "Δinvol_ctx/s")]:
            vs = [r[k_ps] for r in m]
        # Print combined row
        mn_minflt = statistics.mean([r["minflt_ps"] for r in m])
        sd_minflt = statistics.stdev([r["minflt_ps"] for r in m]) if n > 1 else 0
        mn_rss = statistics.mean([r["rss_mb"] for r in m])
        sd_rss = statistics.stdev([r["rss_mb"] for r in m]) if n > 1 else 0
        mn_vol = statistics.mean([r["vol_ctx_ps"] for r in m])
        sd_vol = statistics.stdev([r["vol_ctx_ps"] for r in m]) if n > 1 else 0
        mn_iv = statistics.mean([r["invol_ctx_ps"] for r in m])
        sd_iv = statistics.stdev([r["invol_ctx_ps"] for r in m]) if n > 1 else 0
        print(f"{arm:<3} {n:>3} | {mn_minflt:>10,.0f}±{sd_minflt:>3.0f} | {mn_rss:>7,.0f}±{sd_rss:>3.0f} | "
              f"{mn_vol:>10,.0f}±{sd_vol:>3.0f} | {mn_iv:>10,.0f}±{sd_iv:>3.0f}")

    # Cross-arm Δ
    if rows["A"] and rows["D"]:
        a_vol = statistics.mean([r["vol_ctx_ps"] for r in rows["A"]])
        d_vol = statistics.mean([r["vol_ctx_ps"] for r in rows["D"]])
        delta = (d_vol - a_vol) / a_vol * 100
        print(f"\nD vs A Δvol_ctx: {delta:+.1f}%")
    if rows["A"] and rows["B"]:
        a_vol = statistics.mean([r["vol_ctx_ps"] for r in rows["A"]])
        b_vol = statistics.mean([r["vol_ctx_ps"] for r in rows["B"]])
        delta = (b_vol - a_vol) / a_vol * 100
        print(f"B vs A Δvol_ctx: {delta:+.1f}%")

    # Output TSV
    out = REPO / "reports" / "figures" / "track1a_summary_n6.tsv"
    cols = ["arm", "N", "minflt_ps_mean", "minflt_ps_std",
            "rss_mb_mean", "rss_mb_std",
            "vol_ctx_ps_mean", "vol_ctx_ps_std",
            "invol_ctx_ps_mean", "invol_ctx_ps_std"]
    with open(out, "w") as f:
        f.write("# schema=1  source=tools/aggregate_track1a_n6.py\n")
        f.write("\t".join(cols) + "\n")
        for arm in ["A","B","D"]:
            m = rows[arm]
            if not m:
                continue
            n = len(m)
            def ms(k):
                xs = [r[k] for r in m]
                return statistics.mean(xs), (statistics.stdev(xs) if n>1 else 0)
            mn_mf, sd_mf = ms("minflt_ps")
            mn_rs, sd_rs = ms("rss_mb")
            mn_vc, sd_vc = ms("vol_ctx_ps")
            mn_iv, sd_iv = ms("invol_ctx_ps")
            f.write(f"{arm}\t{n}\t{mn_mf:.1f}\t{sd_mf:.1f}\t{mn_rs:.1f}\t{sd_rs:.1f}\t"
                    f"{mn_vc:.1f}\t{sd_vc:.1f}\t{mn_iv:.1f}\t{sd_iv:.1f}\n")
    print(f"\nWrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
