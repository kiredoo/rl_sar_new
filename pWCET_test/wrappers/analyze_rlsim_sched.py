#!/usr/bin/env python3
import csv
import math
import statistics as st
import sys
from collections import defaultdict, Counter
from pathlib import Path

def parse_sched_csv(path: Path):
    rows = []
    malformed = 0
    with path.open(errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            s = line.strip()
            if not s:
                continue
            # skip bpftrace banners / headers
            if not s[0].isdigit():
                continue
            parts = s.split(",")
            try:
                ts = int(parts[0])
                event = parts[1]
                # New recommended format: ts,event,tid,other
                if len(parts) >= 4 and event in ("wakeup", "switch_in", "switch_out"):
                    tid = int(parts[2])
                    other = int(parts[3])
                    rows.append((ts, event, tid, other, lineno))
                # Old format: ts,wakeup,pid
                elif len(parts) == 3 and event == "wakeup":
                    tid = int(parts[2])
                    rows.append((ts, "wakeup", tid, 0, lineno))
                # Old format: ts,switch,prev_pid,next_pid
                elif len(parts) >= 4 and event == "switch":
                    prev_tid = int(parts[2])
                    next_tid = int(parts[3])
                    rows.append((ts, "switch_out", prev_tid, next_tid, lineno))
                    rows.append((ts, "switch_in", next_tid, prev_tid, lineno))
                else:
                    malformed += 1
            except Exception:
                malformed += 1
    rows.sort(key=lambda x: x[0])
    return rows, malformed

def pct(sorted_values, q):
    if not sorted_values:
        return math.nan
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = (len(sorted_values) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_values[lo])
    return float(sorted_values[lo] * (hi - pos) + sorted_values[hi] * (pos - lo))

def label_and_deadline_us(median_us):
    # External scheduler approximation; use loose bands.
    if 3500 <= median_us <= 7500:
        return "loop_control_candidate", 5000.0
    if 14000 <= median_us <= 28000:
        return "loop_rl_candidate", 20000.0
    if 35000 <= median_us <= 75000:
        return "loop_keyboard_candidate", 50000.0
    return "unclassified", math.nan

def summarize_intervals(rows, event="switch_in"):
    by_tid = defaultdict(list)
    for ts, ev, tid, other, lineno in rows:
        if ev == event and tid > 0:
            by_tid[tid].append(ts)

    summaries = []
    for tid, ts_list in by_tid.items():
        if len(ts_list) < 3:
            continue
        intervals_us = [
            (ts_list[i] - ts_list[i - 1]) / 1000.0
            for i in range(1, len(ts_list))
            if ts_list[i] > ts_list[i - 1]
        ]
        if len(intervals_us) < 2:
            continue
        vals = sorted(intervals_us)
        mean = st.mean(vals)
        median = pct(vals, 0.50)
        label, deadline = label_and_deadline_us(median)
        miss_10pct = ""
        miss_rate = ""
        if math.isfinite(deadline):
            threshold = deadline * 1.10
            misses = sum(1 for x in vals if x > threshold)
            miss_10pct = misses
            miss_rate = misses / len(vals)
        summaries.append({
            "tid": tid,
            "event": event,
            "samples": len(vals),
            "mean_us": mean,
            "p50_us": median,
            "p95_us": pct(vals, 0.95),
            "p99_us": pct(vals, 0.99),
            "max_us": max(vals),
            "label": label,
            "deadline_us": deadline if math.isfinite(deadline) else "",
            "miss_10pct_count": miss_10pct,
            "miss_10pct_rate": miss_rate,
        })
    summaries.sort(key=lambda r: (r["label"] == "unclassified", -r["samples"], r["tid"]))
    return summaries

def main():
    if len(sys.argv) < 2:
        print("usage: analyze_rlsim_sched.py <rlsim_sched.csv> [out_summary.csv]", file=sys.stderr)
        sys.exit(1)

    path = Path(sys.argv[1]).expanduser()
    out = Path(sys.argv[2]).expanduser() if len(sys.argv) >= 3 else path.with_suffix(".summary.csv")

    rows, malformed = parse_sched_csv(path)
    if not rows:
        print(f"No usable scheduling rows parsed from {path}")
        sys.exit(2)

    events = Counter(ev for _, ev, _, _, _ in rows)
    tids = sorted({tid for _, _, tid, _, _ in rows if tid > 0})
    duration_s = (rows[-1][0] - rows[0][0]) / 1e9 if len(rows) >= 2 else 0.0

    print(f"input: {path}")
    print(f"usable rows: {len(rows)}")
    print(f"malformed/skipped data rows: {malformed}")
    print(f"events: {dict(events)}")
    print(f"unique tids seen: {len(tids)}")
    print(f"capture duration: {duration_s:.3f} s")

    if duration_s < 10:
        print("[WARN] Capture duration is short. For deadline/jitter, collect ~60 s during locomotion.")

    if events.get("wakeup", 0) < 10 and events.get("switch_in", 0) < 10:
        print("[WARN] Very few relevant events. This is probably not enough for timing conclusions.")

    summaries = summarize_intervals(rows, event="switch_in")

    fieldnames = [
        "tid", "event", "samples", "mean_us", "p50_us", "p95_us", "p99_us",
        "max_us", "label", "deadline_us", "miss_10pct_count", "miss_10pct_rate"
    ]
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in summaries:
            writer.writerow(r)

    print(f"wrote summary: {out}")
    print()
    print("Top candidate threads from switch_in intervals:")
    for r in summaries[:20]:
        miss = r["miss_10pct_count"]
        rate = r["miss_10pct_rate"]
        if rate != "":
            rate_s = f"{rate*100:.2f}%"
        else:
            rate_s = ""
        print(
            f"tid={r['tid']} label={r['label']} samples={r['samples']} "
            f"p50={r['p50_us']:.1f}us p95={r['p95_us']:.1f}us "
            f"p99={r['p99_us']:.1f}us max={r['max_us']:.1f}us "
            f"miss10%={miss} rate={rate_s}"
        )

if __name__ == "__main__":
    main()
