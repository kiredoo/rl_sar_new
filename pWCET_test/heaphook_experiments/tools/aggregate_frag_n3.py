#!/usr/bin/env python3
"""Aggregate Phase 2 N=3 D PROBE=1 fragmentation results into cross-rep summary.

Reads per-rep frag_summary.tsv (from post_process_frag.py) → produces:
- reports/figures/frag_n3_d_probe.tsv (per-rep × per-arm)
- text summary printed
- stamp into deck appendix C
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
    ap.add_argument("--reps-glob", default="20260506-*_layer2-d-probe-rep*")
    ap.add_argument("--output", default=str(REPO / "reports" / "figures" / "frag_n3_d_probe.tsv"))
    args = ap.parse_args()

    rep_dirs = sorted((REPO / "runs").glob(args.reps_glob))
    print(f"Found {len(rep_dirs)} d-probe rep dirs", file=sys.stderr)

    summary_rows = []
    for rep_dir in rep_dirs:
        frag_summary = rep_dir / "derived" / "frag_summary.tsv"
        if not frag_summary.exists():
            print(f"  skip {rep_dir.name}: no frag_summary.tsv", file=sys.stderr)
            continue
        rows = read_tsv(frag_summary)
        # Aggregate: total allocated, peak, fallback (pool 32768) usage
        total_o1heap_alloc = 0
        total_tlsf_alloc = 0
        peak_o1heap = 0
        peak_tlsf = 0
        n_rows_o1heap = 0
        n_rows_tlsf = 0
        for r in rows:
            try:
                cap = int(r.get("capacity", 0) or 0)
            except Exception:
                cap = 0
            try:
                alloc = int(float(r.get("mean_allocated", 0) or 0))
                peak = int(float(r.get("peak_allocated", 0) or 0))
            except Exception:
                continue
            # TLSF fallback pools have cap > 16 MiB; thread-local O1heap = 4 MiB
            if cap >= 16 * 1024 * 1024:
                total_tlsf_alloc += alloc
                peak_tlsf = max(peak_tlsf, peak)
                n_rows_tlsf += 1
            else:
                total_o1heap_alloc += alloc
                peak_o1heap = max(peak_o1heap, peak)
                n_rows_o1heap += 1
        # peak_o1heap as % of pool capacity (4 MiB = 4194304)
        peak_pct = (peak_o1heap / 4194304.0) * 100 if peak_o1heap else 0
        summary_rows.append({
            "rep": rep_dir.name,
            "n_o1heap_pool_rows": n_rows_o1heap,
            "n_tlsf_fallback_rows": n_rows_tlsf,
            "total_o1heap_alloc_bytes": total_o1heap_alloc,
            "total_tlsf_alloc_bytes": total_tlsf_alloc,
            "peak_o1heap_alloc_bytes": peak_o1heap,
            "peak_tlsf_alloc_bytes": peak_tlsf,
            "peak_o1heap_pct_of_pool": round(peak_pct, 2),
        })

    if not summary_rows:
        print("No frag data found in d-probe reps yet", file=sys.stderr)
        sys.exit(2)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = list(summary_rows[0].keys())
    with open(out, "w") as f:
        f.write("# schema=1  source=tools/aggregate_frag_n3.py\n")
        f.write("\t".join(cols) + "\n")
        for r in summary_rows:
            f.write("\t".join(str(r[c]) for c in cols) + "\n")

    # Print summary
    tlsf_total = sum(r["total_tlsf_alloc_bytes"] for r in summary_rows)
    print(f"\nN={len(summary_rows)} D PROBE=1 reps (post-fix heaphook):")
    print(f"  TLSF fallback total allocated bytes (across all reps): {tlsf_total}")
    print(f"  TLSF fallback peak allocated bytes (max across reps):  "
          f"{max(r['peak_tlsf_alloc_bytes'] for r in summary_rows)}")
    print(f"  O1heap pool peak utilisation (max % of pool capacity):"
          f" {max(r['peak_o1heap_pct_of_pool'] for r in summary_rows)}%")
    print(f"  → {'fallback NEVER triggered' if tlsf_total == 0 else 'fallback DID trigger'}")
    print(f"\nWrote per-rep details to {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
