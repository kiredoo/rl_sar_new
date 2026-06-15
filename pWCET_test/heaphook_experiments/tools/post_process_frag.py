#!/usr/bin/env python3
"""Summarize per-PID fragmentation TSVs into one derived/frag_summary.tsv.

Usage:  post_process_frag.py <run_dir>

Walks <run_dir>/raw/*/frag/heaphook_frag_*.tsv. Each file matches
heaphook::sampler schema=1 (see heaphook/include/heaphook/frag_stats.hpp):

    # schema=1
    # pid=<pid>  allocator=<A|B|D>  started_at=<ISO8601>
    timestamp_ns  allocator  pool_id  capacity  allocated  largest_free
    free_block_count  peak_allocated  oom_count

Writes <run_dir>/derived/frag_summary.tsv with one row per PID plus a
per-arm aggregate footer. Derived fragmentation_ratio follows plan §4:

    frag_ratio = 1 - (largest_free / (capacity - allocated))

Rows where capacity == 0 or free_bytes <= 0 contribute only to
"n_rows_excluded_from_frag"; allocated/capacity stats still include
them so we do not lose bringup data.

Caveat: this summarises the full sampler lifetime (ctor → dtor), which
covers bringup + bag + shutdown. Joining to snapshot_rss.sh's pre/post
window to isolate the bag-replay phase is a step-4 concern and requires
snapshot_rss.sh to start emitting CLOCK_MONOTONIC_RAW ns timestamps.
"""

from __future__ import annotations

import math
import pathlib
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

SCHEMA = 1

REQUIRED_COLS = [
    "timestamp_ns", "allocator", "pool_id", "capacity", "allocated",
    "largest_free", "free_block_count", "peak_allocated", "oom_count",
]


@dataclass
class PidStats:
    pid: int
    allocator: str
    n_rows: int = 0
    n_rows_excluded_from_frag: int = 0
    first_ts_ns: int | None = None
    last_ts_ns: int | None = None
    allocated: list[int] = field(default_factory=list)
    peak_allocated_max: int = 0
    frag_ratios: list[float] = field(default_factory=list)
    final_oom_count: int = 0


def _parse_tsv(path: pathlib.Path) -> PidStats | None:
    pid: int | None = None
    allocator: str | None = None
    header_cols: list[str] | None = None

    with path.open() as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line:
                continue
            if line.startswith("# schema="):
                schema = int(line.split("=", 1)[1])
                if schema != SCHEMA:
                    raise ValueError(f"{path}: schema={schema}, expected {SCHEMA}")
                continue
            if line.startswith("#"):
                for tok in line[1:].split("\t"):
                    tok = tok.strip()
                    if tok.startswith("pid="):
                        pid = int(tok.split("=", 1)[1])
                    elif tok.startswith("allocator="):
                        allocator = tok.split("=", 1)[1]
                continue
            if header_cols is None:
                header_cols = line.split("\t")
                missing = [c for c in REQUIRED_COLS if c not in header_cols]
                if missing:
                    raise ValueError(f"{path}: missing columns {missing}")
                stats = PidStats(pid=pid or -1, allocator=allocator or "?")
                continue
            parts = line.split("\t")
            if len(parts) != len(header_cols):
                # tolerate truncated trailing line from abrupt process exit
                continue
            row = dict(zip(header_cols, parts))
            # Header `# pid=...  allocator=A` is hardcoded by the sampler's
            # write_header() and does NOT distinguish hybrid vs glibc mode;
            # data-row "allocator" column is the truth (Phase 2.5b: D-rows
            # come from O1heap/TLSF providers, A-rows from glibc provider).
            # Use the first encountered data-row allocator for stats.allocator.
            data_alloc = row.get("allocator", "")
            if data_alloc and data_alloc != "?" and data_alloc != stats.allocator:
                stats.allocator = data_alloc
            try:
                ts = int(row["timestamp_ns"])
                capacity = int(row["capacity"])
                allocated = int(row["allocated"])
                largest_free = int(row["largest_free"])
                oom_count = int(row["oom_count"])
                peak = int(row["peak_allocated"])
            except ValueError:
                continue

            stats.n_rows += 1
            stats.first_ts_ns = ts if stats.first_ts_ns is None else stats.first_ts_ns
            stats.last_ts_ns = ts
            stats.allocated.append(allocated)
            if peak > stats.peak_allocated_max:
                stats.peak_allocated_max = peak
            stats.final_oom_count = oom_count

            free_bytes = capacity - allocated
            if capacity > 0 and free_bytes > 0 and largest_free >= 0:
                stats.frag_ratios.append(1.0 - (largest_free / free_bytes))
            else:
                stats.n_rows_excluded_from_frag += 1

    if header_cols is None or pid is None:
        return None
    return stats


def _mean(xs: list[float]) -> float:
    return statistics.fmean(xs) if xs else math.nan


def _stdev(xs: list[float]) -> float:
    return statistics.pstdev(xs) if len(xs) > 1 else 0.0


def summarise(run_dir: pathlib.Path) -> tuple[list[PidStats], pathlib.Path]:
    per_pid: list[PidStats] = []
    for tsv in sorted(run_dir.glob("raw/*/frag/heaphook_frag_*.tsv")):
        stats = _parse_tsv(tsv)
        if stats is not None:
            per_pid.append(stats)

    derived = run_dir / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    out = derived / "frag_summary.tsv"

    with out.open("w") as f:
        f.write(f"# schema={SCHEMA}\n")
        f.write(f"# run_dir={run_dir}\n")
        f.write(f"# generated={datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
        f.write("\t".join([
            "pid", "allocator", "n_rows", "n_excluded_frag",
            "first_ts_ns", "last_ts_ns", "span_s",
            "mean_allocated", "peak_allocated",
            "mean_frag_ratio", "stddev_frag_ratio", "final_oom_count",
        ]) + "\n")
        for s in per_pid:
            span_s = 0.0
            if s.first_ts_ns is not None and s.last_ts_ns is not None:
                span_s = (s.last_ts_ns - s.first_ts_ns) / 1e9
            f.write("\t".join([
                str(s.pid), s.allocator, str(s.n_rows), str(s.n_rows_excluded_from_frag),
                str(s.first_ts_ns or 0), str(s.last_ts_ns or 0), f"{span_s:.3f}",
                f"{_mean([float(x) for x in s.allocated]):.0f}", str(s.peak_allocated_max),
                f"{_mean(s.frag_ratios):.6f}", f"{_stdev(s.frag_ratios):.6f}",
                str(s.final_oom_count),
            ]) + "\n")

        # Per-arm aggregate footer (comment rows).
        per_arm: dict[str, list[PidStats]] = {}
        for s in per_pid:
            per_arm.setdefault(s.allocator, []).append(s)
        for arm, group in sorted(per_arm.items()):
            all_ratios = [r for s in group for r in s.frag_ratios]
            total_peak = sum(s.peak_allocated_max for s in group)
            f.write(
                f"# arm={arm}\tn_pids={len(group)}\t"
                f"total_peak_allocated={total_peak}\t"
                f"mean_frag_ratio={_mean(all_ratios):.6f}\t"
                f"stddev_frag_ratio={_stdev(all_ratios):.6f}\n"
            )

    return per_pid, out


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <run_dir>", file=sys.stderr)
        return 2
    run_dir = pathlib.Path(argv[1]).resolve()
    if not run_dir.is_dir():
        print(f"post_process_frag: run_dir does not exist: {run_dir}", file=sys.stderr)
        return 1
    per_pid, out = summarise(run_dir)
    print(f"wrote {out} ({len(per_pid)} pid rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
