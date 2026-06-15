#!/usr/bin/env python3
import argparse
import csv
import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator


def _stats(vals):
    if not vals:
        return {"n": 0, "mean": float("nan"), "std": float("nan"), "max": float("nan")}
    n = len(vals)
    mean = sum(vals) / n
    var = sum((x - mean) ** 2 for x in vals) / n
    std = math.sqrt(var)
    return {"n": n, "mean": mean, "std": std, "max": max(vals)}


def read_loopfunc_csv(path: Path):
    """Read LoopFunc CSV with columns: t_ns, elapsed_us."""
    t_mono_ns = []
    elapsed_us = []
    with path.open("r", newline="") as f:
        r = csv.DictReader(f)
        if r.fieldnames is None:
            raise ValueError("empty csv (no header)")
        need = {"t_mono_ns", "elapsed_us"}
        if not need.issubset(set(r.fieldnames)):
            raise ValueError(f"missing columns: need {sorted(need)}, got {r.fieldnames}")
        for row in r:
            try:
                t_mono_ns.append(int(row["t_mono_ns"]))
                elapsed_us.append(float(row["elapsed_us"]))
            except Exception:
                continue
    if len(t_mono_ns) < 2:
        raise ValueError("need at least 2 data rows to compute cycle time")
    return t_mono_ns, elapsed_us


def find_rl_csv(in_dir: Path, pattern: str) -> Path:
    candidates = sorted(in_dir.glob(pattern))
    if not candidates:
        raise FileNotFoundError(f"No CSV matched: {in_dir}/{pattern}")

    for p in candidates:
        if p.name == "loopfunc_loop_rl.csv":
            return p
    for p in candidates:
        if "loop_rl" in p.name:
            return p
    return candidates[0]


def main():
    ap = argparse.ArgumentParser(
        description="Compute RL input->output latency and cycle time from LoopFunc CSV (loopfunc_loop_rl.csv)."
    )
    ap.add_argument("--in_dir", default="/tmp", help="Directory containing loopfunc_*.csv (default: /tmp)")
    ap.add_argument("--pattern", default="loopfunc_*.csv", help="Glob pattern to search (default: loopfunc_*.csv)")
    ap.add_argument("--out_csv", default="rl_latency_cycle.csv", help="Output CSV path (default: rl_latency_cycle.csv)")
    ap.add_argument("--out_png", default="rl_latency_cycle.png", help="Output PNG path (default: rl_latency_cycle.png)")
    ap.add_argument("--no_plot", action="store_true", help="Do not generate PNG plot")
    ap.add_argument(
        "--xtick_sec",
        type=float,
        default=10.0,
        help="X-axis major tick interval in seconds (default: 10)",
    )
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    rl_csv = find_rl_csv(in_dir, args.pattern)
    t_ns, latency_us = read_loopfunc_csv(rl_csv)

    # Cycle time: delta of consecutive start timestamps
    cycle_us = [float("nan")]
    for i in range(1, len(t_ns)):
        cycle_us.append((t_ns[i] - t_ns[i - 1]) / 1000.0)

    # Write output CSV
    out_csv = Path(args.out_csv)
    if out_csv.is_dir():
        out_csv = out_csv / "rl_latency_cycle.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    with out_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_ns", "rl_latency_us", "rl_cycle_us"])
        for t, lat, cyc in zip(t_ns, latency_us, cycle_us):
            w.writerow([t, f"{lat:.6f}", "" if math.isnan(cyc) else f"{cyc:.6f}"])

    lat_stats = _stats(latency_us)
    cyc_vals = [x for x in cycle_us[1:] if not math.isnan(x)]
    cyc_stats = _stats(cyc_vals)

    print(f"[INPUT] rl_csv = {rl_csv}")
    print("[RL latency] proxy = loop_rl elapsed_us (RunModel work time)")
    print(f"  n={lat_stats['n']} mean={lat_stats['mean']:.3f}us std={lat_stats['std']:.3f}us max={lat_stats['max']:.3f}us")
    print("[RL cycle time] = delta consecutive t_ns (start-to-start period)")
    print(f"  n={cyc_stats['n']} mean={cyc_stats['mean']:.3f}us std={cyc_stats['std']:.3f}us max={cyc_stats['max']:.3f}us")
    print(f"[OK] wrote {out_csv}")

    if args.no_plot:
        return

    # Plot: 2x1 (latency + cycle time)
    t0 = t_ns[0]
    x_s = [(t - t0) / 1e9 for t in t_ns]

    fig, axes = plt.subplots(2, 1, figsize=(14, 6.5), sharex=True)
    axes[0].plot(x_s, latency_us)
    axes[0].set_title("RL input->output latency")
    axes[0].set_ylabel("latency (us)")

    axes[1].plot(x_s, cycle_us)
    axes[1].set_title("RL cycle time")
    axes[1].set_ylabel("cycle time (us)")
    axes[1].set_xlabel("time (s) from first sample")

    # X ticks every N seconds
    if args.xtick_sec > 0:
        axes[1].xaxis.set_major_locator(MultipleLocator(args.xtick_sec))

    fig.tight_layout()
    out_png = Path(args.out_png)
    if out_png.is_dir():
        out_png = out_png / "rl_latency_cycle.png"
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"[OK] wrote {out_png}")


if __name__ == "__main__":
    main()
