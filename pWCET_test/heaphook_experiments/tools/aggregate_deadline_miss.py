#!/usr/bin/env python3
"""Aggregate per-rep deadline miss into cross-arm summary.

Reads tools/extract_deadline_miss.py output (TSV) → produces:
- reports/figures/deadline_miss_summary.tsv (arm × deadline → mean/std miss rate)
- reports/figures/mckinsey/f8_deadline_miss_by_arm.png (bar chart)
"""
import argparse
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def read_tsv(path):
    rows = []
    header = None
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if header is None:
                header = parts
                continue
            rows.append(dict(zip(header, parts)))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(REPO / "reports" / "figures" / "deadline_miss_n18.tsv"))
    ap.add_argument("--output", default=str(REPO / "reports" / "figures" / "deadline_miss_summary.tsv"))
    ap.add_argument("--png", default=str(REPO / "reports" / "figures" / "mckinsey" / "f8_deadline_miss_by_arm.png"))
    args = ap.parse_args()

    rows = read_tsv(args.input)
    print(f"Read {len(rows)} per-rep rows", file=sys.stderr)

    # Group by (arm, deadline) → list of miss_rate
    grouped = {}
    for r in rows:
        arm = r["arm"]
        dl = float(r["deadline_ms"])
        miss = float(r["miss_rate_est"])
        grouped.setdefault((arm, dl), []).append(miss)

    summary = []
    for (arm, dl), miss_list in sorted(grouped.items()):
        summary.append({
            "arm": arm,
            "deadline_ms": dl,
            "n_reps": len(miss_list),
            "mean_miss_rate": round(statistics.mean(miss_list), 4),
            "std_miss_rate": round(statistics.stdev(miss_list) if len(miss_list) > 1 else 0.0, 4),
            "min_miss_rate": round(min(miss_list), 4),
            "max_miss_rate": round(max(miss_list), 4),
        })

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = list(summary[0].keys())
    with open(out, "w") as f:
        f.write("# schema=1  source=tools/aggregate_deadline_miss.py\n")
        f.write("\t".join(cols) + "\n")
        for r in summary:
            f.write("\t".join(str(r[c]) for c in cols) + "\n")
    print(f"Wrote {len(summary)} rows to {out}", file=sys.stderr)

    # Print readable summary
    print("\nCross-arm deadline miss rate (mean across reps):")
    arms = sorted({r["arm"] for r in summary})
    dls = sorted({r["deadline_ms"] for r in summary})
    print(f"  deadline_ms | " + " | ".join(f"{a:>6s}" for a in arms))
    for dl in dls:
        cells = []
        for a in arms:
            match = [r for r in summary if r["arm"] == a and r["deadline_ms"] == dl]
            cells.append(f"{match[0]['mean_miss_rate']*100:>5.1f}%" if match else "    -")
        print(f"  {dl:>11.0f} | " + " | ".join(cells))

    # Optional PNG (only if matplotlib available)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        from matplotlib.font_manager import FontProperties
        FP = FontProperties(fname="/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")

        fig, ax = plt.subplots(figsize=(9, 5))
        arm_colors = {"A": "#888", "B": "#c25450", "D": "#4a9b82"}
        x = np.arange(len(dls))
        width = 0.27
        for i, a in enumerate(arms):
            vals = []
            errs = []
            for dl in dls:
                m = [r for r in summary if r["arm"] == a and r["deadline_ms"] == dl]
                vals.append(m[0]["mean_miss_rate"] * 100 if m else 0)
                errs.append(m[0]["std_miss_rate"] * 100 if m else 0)
            offset = (i - 1) * width
            ax.bar(x + offset, vals, width, yerr=errs, capsize=3,
                   label=f"arm {a}", color=arm_colors.get(a, "#888"))

        ax.set_xticks(x)
        ax.set_xticklabels([f"{int(d)}" for d in dls])
        ax.set_xlabel("Deadline (ms)")
        ax.set_ylabel("Miss rate estimate (%)")
        ax.set_title("Deadline miss rate × arm × deadline (estimated from CARET p50/p95/p99/max)",
                     fontproperties=FP)
        ax.legend()
        ax.grid(True, axis="y", alpha=0.3)
        plt.tight_layout()
        png_out = Path(args.png)
        png_out.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(png_out, dpi=140)
        print(f"Wrote chart to {png_out}", file=sys.stderr)
    except ImportError:
        print("matplotlib not available; skipping PNG", file=sys.stderr)


if __name__ == "__main__":
    main()
