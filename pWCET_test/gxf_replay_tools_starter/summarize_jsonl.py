#!/usr/bin/env python3
"""Summarize JSONL topic files produced by bag_to_jsonl.py."""

import argparse
import json
from pathlib import Path
from statistics import mean, pstdev


def summarize_file(path: Path) -> dict:
    timestamps = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            timestamps.append(int(rec["timestamp_ns"]))

    if not timestamps:
        return {"file": path.name, "count": 0}

    timestamps.sort()
    intervals_ms = [
        (timestamps[i] - timestamps[i - 1]) / 1e6 for i in range(1, len(timestamps))
    ]
    duration_s = (timestamps[-1] - timestamps[0]) / 1e9 if len(timestamps) > 1 else 0.0
    rate_hz = (len(timestamps) - 1) / duration_s if duration_s > 0 else 0.0

    out = {
        "file": path.name,
        "count": len(timestamps),
        "duration_s": duration_s,
        "rate_hz": rate_hz,
    }
    if intervals_ms:
        intervals_ms_sorted = sorted(intervals_ms)
        n = len(intervals_ms_sorted)
        out.update(
            {
                "period_mean_ms": mean(intervals_ms),
                "period_std_ms": pstdev(intervals_ms) if len(intervals_ms) > 1 else 0.0,
                "period_min_ms": intervals_ms_sorted[0],
                "period_p95_ms": intervals_ms_sorted[int(0.95 * (n - 1))],
                "period_p99_ms": intervals_ms_sorted[int(0.99 * (n - 1))],
                "period_max_ms": intervals_ms_sorted[-1],
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True, help="Directory with *.jsonl files")
    parser.add_argument("--out", default="summary.json", help="Output JSON path")
    args = parser.parse_args()

    in_dir = Path(args.dir).expanduser().resolve()
    summaries = [summarize_file(p) for p in sorted(in_dir.glob("*.jsonl"))]

    out_path = Path(args.out).expanduser().resolve()
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(summaries, fh, indent=2)
    print(json.dumps(summaries, indent=2))
    print(f"[DONE] wrote {out_path}")


if __name__ == "__main__":
    main()
