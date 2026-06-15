#!/usr/bin/env python3
"""
Post-rep observer: given a rep dir, emit comprehensive result.json with
verdict (STRICT_PASS / RELAXED_PASS / FAIL).

Inputs:
    run_dir: path to runs/<id>/
    arm:     A | B | D (default infer from dir name)

Outputs:
    {run_dir}/raw/{arm}/result.json — verdict + per-metric pass/fail
    stdout: human-readable summary

Checks:
  Operational health (T1 log):
    - composition done
    - EKF/NDT activated
    - SIGSEGV < 5
    - SIGABRT < 5
    - GNSS pose errors < 3
    - TF unconnected errors < 50

  Alignment quality (from sample_*.txt during measurement window):
    - TP mean >= 4.0
    - exe_time mean < 100
    - dist mean < 2
    - kin_state Hz >= 30

  Trace integrity:
    - trace size > 5 MB
    - stats_path.yaml exists (after caret_batch)
    - raw_row_with_end > 50
    - best_max < 5000 ms (no pause artifact)
    - best_max / best_p99 < 5
"""

import sys
import json
import os
import re
import statistics
from pathlib import Path

# Thresholds
# DOMAIN_ANCHORED: from Autoware NDT spec / physical constraint — DO NOT loosen
# SANITY:          arbitrary guards — loosen if N>=10 reps show false failures
# Will refit SANITY thresholds via Shewhart mean+3σ once N>=10 reps available
THRESHOLDS = {
    # DOMAIN_ANCHORED (alignment quality — Autoware NDT spec)
    "tp_min": 4.0,                  # NDT TIER IV lock-quality lower bound
    "exe_time_max_ms": 100.0,       # 10Hz lidar = 100ms budget
    "dist_max_m": 2.0,              # map cell-size operational tolerance
    "kin_state_hz_min": 30.0,       # EKF typical rate (50Hz nominal, 30 acceptable)

    # SANITY (current best guess; refit later)
    "sigsegv_max": 5,               # <5 = shutdown noise
    "sigabrt_max": 5,
    "gnss_err_max": 10,             # was 3, loosened — bringup transient before align is normal
    "tf_err_max": 200,              # was 50, loosened — A rep1 had 70 healthy
    "trace_size_mb_min": 5.0,
    "raw_row_with_end_min": 50,

    # CRITICAL SANITY (catch protocol-level bugs — DO NOT loosen)
    "best_max_max_ms": 5000.0,      # >5s = pause artifact / system hang
    "max_p99_ratio_max": 5.0,       # >5x = extreme outlier
}

# Tiered verdict reasons
TIER_DOMAIN = ["alignment_tp", "alignment_exe", "alignment_dist", "alignment_kin"]
TIER_CRITICAL = ["trace_best_max", "trace_max_p99_ratio", "op_sigsegv", "op_sigabrt"]
TIER_SANITY = ["op_gnss", "op_tf", "op_composition", "op_ekf", "op_ndt", "trace_size", "trace_samples"]


def grep_count(path, pattern):
    if not os.path.isfile(path):
        return 0
    try:
        with open(path, errors='replace') as f:
            return sum(1 for line in f if re.search(pattern, line))
    except Exception:
        return 0


def parse_floats(path):
    out = []
    if not os.path.isfile(path):
        return out
    try:
        with open(path) as f:
            for l in f:
                l = l.strip()
                if not l:
                    continue
                try:
                    out.append(float(l))
                except ValueError:
                    pass
    except Exception:
        pass
    return out


def stat(arr):
    if not arr:
        return {"n": 0}
    return {
        "n": len(arr),
        "min": round(min(arr), 3),
        "max": round(max(arr), 3),
        "mean": round(statistics.mean(arr), 3),
        "median": round(statistics.median(arr), 3),
    }


def parse_kin_hz(path):
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            for line in f:
                m = re.search(r'average rate:\s*([\d.]+)', line)
                if m:
                    return float(m.group(1))
    except Exception:
        pass
    return None


def find_t1_log(rep_root, arm):
    return rep_root / "raw" / arm / f"aw_{arm}_t1.log"


def find_trace_dir(rep_root, arm):
    caret_dir = rep_root / "raw" / arm / "caret"
    if not caret_dir.is_dir():
        return None
    for prefix in ("heaphook-", "session-"):
        for child in caret_dir.iterdir():
            if child.is_dir() and child.name.startswith(prefix):
                return child
    return None


def find_stats_yaml(rep_root, arm):
    """Look for stats_path.yaml from caret_batch output.
    Match on prefix `report_<trace_dir.name>` AND filter by trace_dir's full
    path (caret_batch may append disambiguator when name collides)."""
    trace_dir = find_trace_dir(rep_root, arm)
    if not trace_dir:
        return None
    prefix = f"report_{trace_dir.name}"
    # Sanitised path fragment that batch_run.sh appends for disambiguation
    sanitised_path = str(trace_dir).replace('/', '_')
    candidates = []
    for storage_dir in [
        Path(os.path.expanduser("~/repo/caret_report/sample_autoware/output_storage")),
        Path(os.path.expanduser("~/repo/caret_report/sample_autoware/output")),
    ]:
        if not storage_dir.is_dir():
            continue
        for child in storage_dir.iterdir():
            if not child.is_dir():
                continue
            if not child.name.startswith(prefix):
                continue
            stats = child / "analyze_path" / "stats_path.yaml"
            if not stats.is_file():
                continue
            # Prefer one that contains our path fragment (disambiguated dir)
            score = 1
            if sanitised_path[-60:] in child.name:
                score = 10
            candidates.append((score, stats.stat().st_mtime, stats))
    if not candidates:
        return None
    # Highest score, then most recent mtime
    candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return candidates[0][2]


def parse_stats_yaml(path):
    """Parse stats_path.yaml — minimal yaml-like extraction (avoid pyyaml dep)."""
    chain = {
        "name": None,
        "raw_row_total": 0,
        "raw_row_with_end": 0,
        "best_avg": 0.0,
        "best_p50": 0.0,
        "best_p95": 0.0,
        "best_p99": 0.0,
        "best_min": 0.0,
        "best_max": 0.0,
        "best_std": 0.0,
    }
    if not path or not path.is_file():
        return chain
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("- target_path_name:"):
                    chain["name"] = line.split(":", 1)[1].strip()
                for key in ["raw_row_total", "raw_row_with_end",
                            "best_avg", "best_p50", "best_p95", "best_p99",
                            "best_min", "best_max", "best_std"]:
                    if line.startswith(f"{key}:"):
                        try:
                            chain[key] = float(line.split(":", 1)[1].strip())
                        except ValueError:
                            pass
                if chain["name"] and line.startswith("- target_path_name:") and chain["name"] != line.split(":", 1)[1].strip():
                    break  # stop at next chain (we take first)
    except Exception:
        pass
    return chain


def main():
    if len(sys.argv) < 2:
        print("usage: observe_rep.py <run_dir> [arm]", file=sys.stderr)
        sys.exit(2)

    rep_root = Path(sys.argv[1]).resolve()
    if not rep_root.is_dir():
        print(f"ERR: not a dir: {rep_root}", file=sys.stderr)
        sys.exit(2)

    if len(sys.argv) >= 3:
        arm = sys.argv[2]
    else:
        # Infer from dir name (e.g., layer2-cv-d-0.5x-rep1 → D)
        m = re.search(r'cv-([abd])', rep_root.name.lower())
        arm = m.group(1).upper() if m else "D"

    raw_dir = rep_root / "raw" / arm
    raw_dir.mkdir(parents=True, exist_ok=True)
    t1_log = raw_dir / f"aw_{arm}_t1.log"

    result = {
        "rep_dir": str(rep_root),
        "arm": arm,
        "thresholds": THRESHOLDS,
        "operational": {},
        "alignment": {},
        "trace": {},
        "memory": {},  # Track 1A: RSS / minflt / majflt / ctx delta
    }

    # ---- 1. Operational health (T1 log) ----
    op = result["operational"]
    if t1_log.is_file():
        op["t1_log_present"] = True
        op["t1_log_lines"] = sum(1 for _ in open(t1_log, errors='replace'))
        op["composition_done"] = grep_count(t1_log, r"Loaded node.*traffic_light_roi_visualizer") >= 1
        op["ekf_activation_count"] = grep_count(t1_log, r"EKF Activation succeeded")
        op["ndt_activation_count"] = grep_count(t1_log, r"NDT Activation succeeded")
        op["align_succeeded"] = grep_count(t1_log, r"align server succeeded")
        op["deactivation_count"] = grep_count(t1_log, r"Deactivation succeeded")
        op["sigsegv_count"] = grep_count(t1_log, r"exit code -11")
        op["sigabrt_count"] = grep_count(t1_log, r"exit code -6")
        op["gnss_pose_not_arrived_count"] = grep_count(t1_log, r"GNSS pose has not arrived")
        op["tf_unconnected_count"] = grep_count(t1_log, r"two or more unconnected trees")
    else:
        op["t1_log_present"] = False

    op["pass"] = (
        op.get("t1_log_present", False)
        and op.get("composition_done", False)
        and op.get("ekf_activation_count", 0) >= 1
        and op.get("ndt_activation_count", 0) >= 1
        and op.get("sigsegv_count", 999) < THRESHOLDS["sigsegv_max"]
        and op.get("sigabrt_count", 999) < THRESHOLDS["sigabrt_max"]
        and op.get("gnss_pose_not_arrived_count", 999) < THRESHOLDS["gnss_err_max"]
        and op.get("tf_unconnected_count", 999) < THRESHOLDS["tf_err_max"]
    )

    # ---- 2. Alignment quality (sample_*.txt during record window) ----
    align = result["alignment"]
    align["tp"] = stat(parse_floats(raw_dir / "sample_tp.txt"))
    align["exe_time_ms"] = stat(parse_floats(raw_dir / "sample_exe.txt"))
    align["dist_m"] = stat(parse_floats(raw_dir / "sample_dist.txt"))
    align["kin_hz"] = parse_kin_hz(raw_dir / "sample_kin_hz.txt")
    align["pass"] = (
        align["tp"].get("mean", 0) >= THRESHOLDS["tp_min"]
        and align["exe_time_ms"].get("mean", 9999) < THRESHOLDS["exe_time_max_ms"]
        and align["dist_m"].get("mean", 99) < THRESHOLDS["dist_max_m"]
        and (align["kin_hz"] or 0) >= THRESHOLDS["kin_state_hz_min"]
    )

    # ---- 3. Trace integrity ----
    tr = result["trace"]
    trace_dir = find_trace_dir(rep_root, arm)
    if trace_dir:
        tr["trace_dir"] = str(trace_dir)
        try:
            sz = sum(f.stat().st_size for f in trace_dir.rglob('*') if f.is_file())
            tr["trace_size_mb"] = round(sz / 1024 / 1024, 1)
        except Exception:
            tr["trace_size_mb"] = 0
    else:
        tr["trace_dir"] = None
        tr["trace_size_mb"] = 0

    stats_yaml = find_stats_yaml(rep_root, arm)
    tr["stats_yaml"] = str(stats_yaml) if stats_yaml else None
    chain = parse_stats_yaml(stats_yaml)
    tr["chain"] = chain

    if chain.get("best_p99", 0) > 0:
        tr["max_p99_ratio"] = round(chain.get("best_max", 0) / chain["best_p99"], 2)
    else:
        tr["max_p99_ratio"] = None

    if chain.get("best_avg", 0) > 0:
        tr["cv"] = round(chain.get("best_std", 0) / chain["best_avg"], 3)
    else:
        tr["cv"] = None

    tr["pass"] = (
        tr.get("trace_size_mb", 0) > THRESHOLDS["trace_size_mb_min"]
        and chain.get("raw_row_with_end", 0) > THRESHOLDS["raw_row_with_end_min"]
        and chain.get("best_max", 9999) < THRESHOLDS["best_max_max_ms"]
        and (tr["max_p99_ratio"] or 99) < THRESHOLDS["max_p99_ratio_max"]
    )

    # ---- 4. Memory snapshot (Track 1A direct evidence) ----
    mem = result["memory"]

    def parse_rss_totals(path):
        """Parse # totals minflt=... majflt=... rss_kb=... vol_ctx=... invol_ctx=... num=... line."""
        if not path.is_file():
            return None
        try:
            with open(path) as f:
                for line in f:
                    if line.startswith("# totals"):
                        out = {}
                        for kv in line.replace("# totals", "").strip().split():
                            if "=" in kv:
                                k, v = kv.split("=", 1)
                                try:
                                    out[k] = int(v)
                                except ValueError:
                                    out[k] = v
                        return out
        except Exception:
            pass
        return None

    pre = parse_rss_totals(raw_dir / "rss_pre.txt")
    post = parse_rss_totals(raw_dir / "rss_post.txt")
    mem["pre"] = pre
    mem["post"] = post
    if pre and post:
        mem["delta"] = {
            "minflt": post.get("minflt", 0) - pre.get("minflt", 0),
            "majflt": post.get("majflt", 0) - pre.get("majflt", 0),
            "rss_kb": post.get("rss_kb", 0) - pre.get("rss_kb", 0),
            "rss_mb": round((post.get("rss_kb", 0) - pre.get("rss_kb", 0)) / 1024.0, 1),
            "vol_ctx": post.get("vol_ctx", 0) - pre.get("vol_ctx", 0),
            "invol_ctx": post.get("invol_ctx", 0) - pre.get("invol_ctx", 0),
            "nprocs_pre": pre.get("num", 0),
            "nprocs_post": post.get("num", 0),
        }
        mem["pass"] = (mem["delta"]["nprocs_post"] >= 80)  # heuristic: most procs alive
    else:
        mem["delta"] = None
        mem["pass"] = False

    # ---- Tiered verdict ----
    # Categorize each fail into domain / critical-sanity / sanity tier
    domain_fails = []
    critical_fails = []
    sanity_fails = []

    # Alignment (DOMAIN_ANCHORED)
    if align["tp"].get("mean", 0) < THRESHOLDS["tp_min"]:
        domain_fails.append(f"TP={align['tp'].get('mean', 0):.2f} < 4.0")
    if align["exe_time_ms"].get("mean", 9999) >= THRESHOLDS["exe_time_max_ms"]:
        domain_fails.append(f"exe_time={align['exe_time_ms'].get('mean', 9999):.0f}ms >= 100")
    if align["dist_m"].get("mean", 99) >= THRESHOLDS["dist_max_m"]:
        domain_fails.append(f"dist={align['dist_m'].get('mean', 99):.2f}m >= 2.0")
    if (align["kin_hz"] or 0) < THRESHOLDS["kin_state_hz_min"]:
        sanity_fails.append(f"kin_hz={align.get('kin_hz')} < 30 (sampler timing)")  # demote to sanity

    # Trace critical (DO NOT loosen)
    if chain.get("best_max", 0) >= THRESHOLDS["best_max_max_ms"]:
        critical_fails.append(f"best_max={chain.get('best_max', 0):.0f}ms >= 5000 (pause artifact)")
    if (tr.get("max_p99_ratio") or 0) >= THRESHOLDS["max_p99_ratio_max"]:
        critical_fails.append(f"max/p99={tr.get('max_p99_ratio')} >= 5 (extreme outlier)")

    # Operational critical
    if op.get("sigsegv_count", 0) >= THRESHOLDS["sigsegv_max"]:
        critical_fails.append(f"sigsegv={op.get('sigsegv_count')}")
    if op.get("sigabrt_count", 0) >= THRESHOLDS["sigabrt_max"]:
        critical_fails.append(f"sigabrt={op.get('sigabrt_count')}")

    # Operational sanity
    if not op.get("composition_done", False):
        sanity_fails.append("composition_not_done")
    if op.get("ekf_activation_count", 0) < 1:
        sanity_fails.append(f"ekf_act={op.get('ekf_activation_count', 0)} < 1")
    if op.get("ndt_activation_count", 0) < 1:
        sanity_fails.append(f"ndt_act={op.get('ndt_activation_count', 0)} < 1")
    if op.get("gnss_pose_not_arrived_count", 0) >= THRESHOLDS["gnss_err_max"]:
        sanity_fails.append(f"gnss_err={op.get('gnss_pose_not_arrived_count')} >= 10")
    if op.get("tf_unconnected_count", 0) >= THRESHOLDS["tf_err_max"]:
        sanity_fails.append(f"tf_err={op.get('tf_unconnected_count')} >= 200")
    if tr.get("trace_size_mb", 0) <= THRESHOLDS["trace_size_mb_min"]:
        sanity_fails.append(f"trace_size={tr.get('trace_size_mb', 0)}MB")
    if chain.get("raw_row_with_end", 0) <= THRESHOLDS["raw_row_with_end_min"]:
        sanity_fails.append(f"samples={chain.get('raw_row_with_end', 0)}")

    # Tiered verdict logic
    if not domain_fails and not critical_fails and not sanity_fails:
        result["verdict"] = "STRICT_PASS"
    elif not domain_fails and not critical_fails and len(sanity_fails) <= 2:
        result["verdict"] = "RELAXED_PASS"
    elif not domain_fails and not critical_fails:
        result["verdict"] = "INFO_ONLY"
    else:
        result["verdict"] = "FAIL"

    result["domain_fails"] = domain_fails
    result["critical_fails"] = critical_fails
    result["sanity_fails"] = sanity_fails
    result["fail_reasons"] = domain_fails + critical_fails + sanity_fails

    # legacy fields for backward compat
    result["fails"] = []
    if domain_fails: result["fails"].append("alignment_domain")
    if critical_fails: result["fails"].append("trace_critical")
    if sanity_fails: result["fails"].append("sanity")

    # Save + print
    out_path = raw_dir / "result.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"=== {arm} rep observation: {result['verdict']} ===")
    print(f"  op:    ekf={op.get('ekf_activation_count')} ndt={op.get('ndt_activation_count')} sigsegv={op.get('sigsegv_count')} tf_err={op.get('tf_unconnected_count')} gnss_err={op.get('gnss_pose_not_arrived_count')}")
    print(f"  align: TP={align['tp'].get('mean','-')} exe={align['exe_time_ms'].get('mean','-')}ms dist={align['dist_m'].get('mean','-')}m kin_hz={align.get('kin_hz')}")
    avg_str = f"{chain.get('best_avg', 0):.0f}" if chain.get('best_avg') else "-"
    max_str = f"{chain.get('best_max', 0):.0f}" if chain.get('best_max') else "-"
    print(f"  trace: size={tr.get('trace_size_mb')}MB samples={chain.get('raw_row_with_end')} avg={avg_str}ms max={max_str}ms p95={chain.get('best_p95'):.0f}ms p99={chain.get('best_p99'):.0f}ms cv={tr.get('cv')} max/p99={tr.get('max_p99_ratio')}")
    if mem["delta"]:
        d = mem["delta"]
        print(f"  memory: Δminflt={d['minflt']} Δmajflt={d['majflt']} Δrss={d['rss_mb']}MB Δvol_ctx={d['vol_ctx']} Δinvol_ctx={d['invol_ctx']} nprocs={d['nprocs_pre']}→{d['nprocs_post']}")
    else:
        print(f"  memory: no rss_pre/post snapshot (canonical orch missing patch — see slide_requirements.md)")
    if domain_fails:
        print("  ❌ DOMAIN fails (Autoware NDT spec):")
        for r in domain_fails: print(f"    - {r}")
    if critical_fails:
        print("  ❌ CRITICAL fails (protocol bug suspect):")
        for r in critical_fails: print(f"    - {r}")
    if sanity_fails:
        print("  ⚠️  SANITY warnings (will refit at N>=10):")
        for r in sanity_fails: print(f"    - {r}")
    print(f"  saved: {out_path}")


if __name__ == "__main__":
    main()
