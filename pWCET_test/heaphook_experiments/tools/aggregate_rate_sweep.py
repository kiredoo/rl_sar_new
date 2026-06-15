#!/usr/bin/env python3
"""Aggregate rate sweep results across 4 rates × 3 arms × N=3 reps = 36 reps.

Reads each rep's result.json (verdict, alignment metrics, trace.cv, trace.chain
mean/p99/max). Outputs:
- reports/figures/rate_sweep_summary.tsv (rate × arm × verdict + metrics)
- reports/figures/mckinsey/f9_rate_sweep_overview.png (4-panel: chain CV, mean,
  p99, deadline miss × rate × arm)
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

RATE_TAGS = {"025": 0.25, "050": 0.5, "075": 0.75, "100": 1.0}


def collect():
    rows = []
    for d in sorted((REPO / "runs").glob("20260506-*_layer2-*-rate*-rep*")):
        nm = d.name.lower()
        # parse tokens: layer2-{a|b|d}-rate{025|050|075|100}-rep{1|2|3}
        parts = nm.split("_")[-1]
        try:
            arm_part = parts.split("-")[1]  # a / b / d
            rate_part = parts.split("-")[2]  # rateXXX
            rep_part = parts.split("-")[3]  # repN
        except IndexError:
            continue
        arm = arm_part.upper()
        rtag = rate_part.replace("rate", "")
        rate = RATE_TAGS.get(rtag)
        if rate is None:
            continue
        rj_paths = list((d / "raw").rglob("result.json"))
        if not rj_paths:
            continue
        data = json.loads(rj_paths[0].read_text())
        align = data.get("alignment") or {}
        trace = data.get("trace") or {}
        chain = trace.get("chain") or {}
        rows.append({
            "rep": d.name,
            "arm": arm,
            "rate": rate,
            "verdict": data.get("verdict", "?"),
            "tp_mean": (align.get("tp") or {}).get("mean"),
            "exe_time_ms_mean": (align.get("exe_time_ms") or {}).get("mean"),
            "kin_state_hz": (align.get("kin_state_hz") or {}).get("mean"),
            "chain_cv": trace.get("cv"),
            "chain_n": chain.get("raw_row_with_end"),
            "chain_mean_ms": chain.get("best_avg"),
            "chain_p95_ms": chain.get("best_p95"),
            "chain_p99_ms": chain.get("best_p99"),
            "chain_max_ms": chain.get("best_max"),
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(REPO / "reports" / "figures" / "rate_sweep_summary.tsv"))
    ap.add_argument("--png", default=str(REPO / "reports" / "figures" / "mckinsey" / "f9_rate_sweep_overview.png"))
    args = ap.parse_args()

    rows = collect()
    print(f"Collected {len(rows)} rate-sweep reps", file=sys.stderr)

    # group by (arm, rate)
    grouped = {}
    for r in rows:
        grouped.setdefault((r["arm"], r["rate"]), []).append(r)

    # Write summary TSV
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["arm", "rate", "n_reps",
            "valid_n", "fail_n",
            "tp_mean_avg", "exe_ms_avg",
            "chain_cv_mean", "chain_cv_std",
            "chain_mean_ms_avg", "chain_p99_ms_avg", "chain_max_ms_avg"]
    with open(out, "w") as f:
        f.write("# schema=1  source=tools/aggregate_rate_sweep.py\n")
        f.write("\t".join(cols) + "\n")
        for (arm, rate), reps in sorted(grouped.items()):
            n = len(reps)
            valid = [r for r in reps if r["verdict"] in ("RELAXED_PASS", "STRICT_PASS")]
            cvs = [r["chain_cv"] for r in valid if r["chain_cv"] is not None]
            tps = [r["tp_mean"] for r in valid if r["tp_mean"] is not None]
            exes = [r["exe_time_ms_mean"] for r in valid if r["exe_time_ms_mean"] is not None]
            means = [r["chain_mean_ms"] for r in valid if r["chain_mean_ms"]]
            p99s = [r["chain_p99_ms"] for r in valid if r["chain_p99_ms"]]
            maxes = [r["chain_max_ms"] for r in valid if r["chain_max_ms"]]
            row = {
                "arm": arm, "rate": rate, "n_reps": n,
                "valid_n": len(valid), "fail_n": n - len(valid),
                "tp_mean_avg": round(statistics.mean(tps), 3) if tps else None,
                "exe_ms_avg": round(statistics.mean(exes), 1) if exes else None,
                "chain_cv_mean": round(statistics.mean(cvs), 4) if cvs else None,
                "chain_cv_std": round(statistics.stdev(cvs), 4) if len(cvs) > 1 else 0,
                "chain_mean_ms_avg": round(statistics.mean(means), 1) if means else None,
                "chain_p99_ms_avg": round(statistics.mean(p99s), 1) if p99s else None,
                "chain_max_ms_avg": round(statistics.mean(maxes), 1) if maxes else None,
            }
            f.write("\t".join(str(row[c]) for c in cols) + "\n")
    print(f"Wrote {out}", file=sys.stderr)

    # PNG with 4 panels (only if matplotlib available)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        from matplotlib.font_manager import FontProperties
        FP = FontProperties(fname="/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")

        fig, axs = plt.subplots(2, 2, figsize=(12, 8))
        axs = axs.flat
        arm_colors = {"A": "#888", "B": "#c25450", "D": "#4a9b82"}
        arms = sorted({k[0] for k in grouped.keys()})
        rates = sorted({k[1] for k in grouped.keys()})

        for ax, key, ylabel, title in [
            (axs[0], "chain_cv", "chain CV", "Chain CV vs bag rate × arm"),
            (axs[1], "chain_mean_ms", "mean latency (ms)", "Mean chain latency vs rate"),
            (axs[2], "chain_p99_ms", "p99 latency (ms)", "p99 chain latency vs rate"),
            (axs[3], "tp_mean", "TP (NDT match)", "NDT TP (alignment validity proxy)"),
        ]:
            for a in arms:
                xs, ys = [], []
                for r in rates:
                    reps = [x for x in (grouped.get((a, r)) or [])
                            if x["verdict"] in ("RELAXED_PASS", "STRICT_PASS")]
                    vals = [rep[key] for rep in reps if rep.get(key) is not None]
                    if vals:
                        xs.append(r)
                        ys.append(statistics.mean(vals))
                if xs:
                    ax.plot(xs, ys, "o-", label=f"arm {a}", color=arm_colors.get(a, "#888"))
            ax.set_xlabel("bag rate (×)")
            ax.set_ylabel(ylabel)
            ax.set_title(title, fontproperties=FP, fontsize=11)
            ax.legend()
            ax.grid(True, alpha=0.3)

        plt.suptitle("Rate sweep: per-arm degradation across 0.25/0.5/0.75/1.0× bag rate",
                     fontproperties=FP, fontsize=13)
        plt.tight_layout()
        png_out = Path(args.png)
        png_out.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(png_out, dpi=140)
        print(f"Wrote chart {png_out}", file=sys.stderr)
    except ImportError:
        print("matplotlib not available", file=sys.stderr)


if __name__ == "__main__":
    main()
