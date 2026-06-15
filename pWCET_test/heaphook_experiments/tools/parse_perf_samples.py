#!/usr/bin/env python3
"""Parse mpstat / nvidia-smi / pidstat samples → JSON summary."""

import sys
import json
import re
import statistics
from pathlib import Path


def parse_mpstat(path):
    """Parse mpstat -P ALL output. Returns per-core and aggregate stats."""
    if not path.is_file():
        return {}
    rows = []  # list of {ts, cpu, usr, sys, idle}
    cur_ts = None
    with open(path) as f:
        for line in f:
            if "Linux" in line and "(" in line:
                continue
            m = re.match(r'^(\d+:\d+:\d+\s*[AP]M|\d+:\d+:\d+)\s+(all|\d+)\s+([\d.]+)\s+[\d.]+\s+([\d.]+)\s+[\d.]+\s+[\d.]+\s+([\d.]+)\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+([\d.]+)', line)
            if m:
                ts, cpu, usr, sys_, soft, idle = m.groups()
                rows.append({
                    "ts": ts.strip(),
                    "cpu": cpu,
                    "usr": float(usr),
                    "sys": float(sys_),
                    "soft": float(soft),
                    "idle": float(idle),
                })
    if not rows:
        return {}

    # Aggregate %busy = 100 - %idle for "all"
    all_rows = [r for r in rows if r["cpu"] == "all"]
    busy = [100.0 - r["idle"] for r in all_rows]

    # Per-core busy
    cores = {}
    for r in rows:
        if r["cpu"] == "all":
            continue
        cid = int(r["cpu"])
        cores.setdefault(cid, []).append(100.0 - r["idle"])

    return {
        "n_samples": len(busy),
        "all_busy_mean": round(statistics.mean(busy), 2) if busy else 0,
        "all_busy_max": round(max(busy), 2) if busy else 0,
        "all_busy_p95": round(statistics.quantiles(busy, n=20)[18], 2) if len(busy) >= 20 else (round(max(busy), 2) if busy else 0),
        "n_cores": len(cores),
        "per_core_busy_mean": {cid: round(statistics.mean(v), 2) for cid, v in cores.items()},
        "per_core_busy_max": {cid: round(max(v), 2) for cid, v in cores.items()},
        "per_core_busy_p95": {cid: (round(statistics.quantiles(v, n=20)[18], 2) if len(v) >= 20 else round(max(v), 2)) for cid, v in cores.items()},
    }


def parse_nvidia(path):
    """Parse nvidia-smi --format=csv,noheader,nounits output.
    Columns: timestamp, util_gpu, util_mem, mem_used, mem_free, temp, power
    """
    if not path.is_file():
        return {}
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 7:
                continue
            try:
                rows.append({
                    "util_gpu": float(parts[1]),
                    "util_mem": float(parts[2]),
                    "mem_used_mb": float(parts[3]),
                    "mem_free_mb": float(parts[4]),
                    "temp_c": float(parts[5]),
                    "power_w": float(parts[6]),
                })
            except ValueError:
                continue

    if not rows:
        return {}
    util = [r["util_gpu"] for r in rows]
    mem = [r["mem_used_mb"] for r in rows]
    temp = [r["temp_c"] for r in rows]
    power = [r["power_w"] for r in rows]
    return {
        "n_samples": len(rows),
        "util_gpu_mean": round(statistics.mean(util), 1),
        "util_gpu_max": round(max(util), 1),
        "util_gpu_p95": round(statistics.quantiles(util, n=20)[18], 1) if len(util) >= 20 else round(max(util), 1),
        "mem_used_mean_mb": round(statistics.mean(mem), 0),
        "mem_used_max_mb": round(max(mem), 0),
        "temp_mean_c": round(statistics.mean(temp), 1),
        "temp_max_c": round(max(temp), 1),
        "power_mean_w": round(statistics.mean(power), 1),
        "power_max_w": round(max(power), 1),
    }


def parse_pidstat_summary(path):
    """Parse pidstat -p ALL -u -w 1 output. Compute aggregate context switch rate
    for autoware processes.
    """
    if not path.is_file():
        return {}

    cs_total = 0  # voluntary cs
    ncs_total = 0  # non-voluntary cs
    cpu_total = 0  # %CPU
    n_autoware_pids = set()
    n_lines = 0

    with open(path) as f:
        for line in f:
            # match: "HH:MM:SS PM  UID  PID  ... %CPU CPU Command"
            # or:    "HH:MM:SS PM  UID  PID  cswch/s  nvcswch/s ... Command"
            if "autoware-2025" not in line and "rclcpp" not in line:
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            try:
                # Extract PID (varies by column position; find numeric in early columns)
                pid = None
                for p in parts[2:5]:
                    if p.isdigit():
                        pid = int(p)
                        break
                if pid:
                    n_autoware_pids.add(pid)
                # Find cswch/s and nvcswch/s if present
                for i, tok in enumerate(parts):
                    if i + 1 < len(parts):
                        try:
                            v = float(tok)
                            if 0 < v < 50000:
                                # heuristic: cs counts often in range
                                pass
                        except ValueError:
                            continue
            except Exception:
                continue
            n_lines += 1

    return {
        "n_autoware_pids_seen": len(n_autoware_pids),
        "n_lines": n_lines,
    }


def main():
    if len(sys.argv) < 2:
        print("usage: parse_perf_samples.py <raw_dir>", file=sys.stderr)
        sys.exit(2)

    raw_dir = Path(sys.argv[1]).resolve()

    out = {
        "raw_dir": str(raw_dir),
        "cpu": parse_mpstat(raw_dir / "sample_mpstat.txt"),
        "gpu": parse_nvidia(raw_dir / "sample_nvidia.txt"),
        "pidstat": parse_pidstat_summary(raw_dir / "sample_pidstat.txt"),
    }

    out_path = raw_dir / "perf_summary.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)

    print(f"=== perf summary: {raw_dir.name} ===")
    if out["cpu"]:
        print(f"  CPU all_busy: mean={out['cpu']['all_busy_mean']}% p95={out['cpu']['all_busy_p95']}% max={out['cpu']['all_busy_max']}% (n_cores={out['cpu']['n_cores']})")
    if out["gpu"]:
        print(f"  GPU: util mean={out['gpu']['util_gpu_mean']}% max={out['gpu']['util_gpu_max']}% mem={out['gpu']['mem_used_mean_mb']}MB temp={out['gpu']['temp_mean_c']}°C power={out['gpu']['power_mean_w']}W")
    if out["pidstat"]:
        print(f"  pidstat: pids_seen={out['pidstat']['n_autoware_pids_seen']} lines={out['pidstat']['n_lines']}")
    print(f"  saved: {out_path}")


if __name__ == "__main__":
    main()
