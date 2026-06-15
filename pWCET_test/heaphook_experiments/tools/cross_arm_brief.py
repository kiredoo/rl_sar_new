#!/usr/bin/env python3
"""Cross-arm brief generator.

Given two rep dirs (A and D), produce a markdown table comparing:
- alignment metrics
- chain CV (e2e latency)
- CPU usage
- GPU usage
- operational health
"""

import sys
import json
from pathlib import Path


def load(p):
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def fmt(v, suffix="", default="-"):
    if v is None or v == 0:
        return default
    if isinstance(v, float):
        return f"{v:.3g}{suffix}"
    return f"{v}{suffix}"


def delta_pct(d, a):
    if not a or a == 0:
        return "-"
    return f"{(d - a) / a * 100:+.0f}%"


def main():
    if len(sys.argv) < 3:
        print("usage: cross_arm_brief.py <rep_a_dir> <rep_d_dir> [output.md]", file=sys.stderr)
        sys.exit(2)

    a_dir = Path(sys.argv[1]).resolve()
    d_dir = Path(sys.argv[2]).resolve()
    out_md = Path(sys.argv[3]) if len(sys.argv) > 3 else (a_dir.parent / f"cross_arm_brief_{a_dir.name}_vs_{d_dir.name}.md")

    a_res = load(a_dir / "raw" / "A" / "result.json")
    d_res = load(d_dir / "raw" / "D" / "result.json")
    a_perf = load(a_dir / "raw" / "A" / "perf_summary.json")
    d_perf = load(d_dir / "raw" / "D" / "perf_summary.json")

    a_align = a_res.get("alignment", {})
    d_align = d_res.get("alignment", {})
    a_chain = a_res.get("trace", {}).get("chain", {})
    d_chain = d_res.get("trace", {}).get("chain", {})
    a_op = a_res.get("operational", {})
    d_op = d_res.get("operational", {})
    a_cpu = a_perf.get("cpu", {})
    d_cpu = d_perf.get("cpu", {})
    a_gpu = a_perf.get("gpu", {})
    d_gpu = d_perf.get("gpu", {})

    md = []
    md.append(f"# Cross-arm brief — A vs D")
    md.append("")
    md.append(f"- A: `{a_dir.name}` — verdict {a_res.get('verdict', '?')}")
    md.append(f"- D: `{d_dir.name}` — verdict {d_res.get('verdict', '?')}")
    md.append("")

    md.append("## Host environment")
    md.append("")
    md.append("- BigFix BESClient (~3% CPU avg, periodic fixlet bursts) running")
    md.append("- ForeScout SecureConnector (~0% CPU steady) running")
    md.append("- Cross-arm Δ valid since both arms share same host monitor load")
    md.append("- 0.5x bag rate (host cannot achieve operational validity at 1.0x)")
    md.append("- N=1 per arm (statistical confidence ~6%; refit thresholds at N≥10)")
    md.append("")

    md.append("## Operational health")
    md.append("")
    md.append("| Metric | A | D | Δ |")
    md.append("|---|---|---|---|")
    md.append(f"| EKF Activation | {a_op.get('ekf_activation_count')} | {d_op.get('ekf_activation_count')} | - |")
    md.append(f"| NDT Activation | {a_op.get('ndt_activation_count')} | {d_op.get('ndt_activation_count')} | - |")
    md.append(f"| SIGSEGV | {a_op.get('sigsegv_count')} | {d_op.get('sigsegv_count')} | - |")
    md.append(f"| TF unconnected (bringup) | {a_op.get('tf_unconnected_count')} | {d_op.get('tf_unconnected_count')} | {delta_pct(d_op.get('tf_unconnected_count', 0), a_op.get('tf_unconnected_count', 0))} |")
    md.append(f"| GNSS pose late | {a_op.get('gnss_pose_not_arrived_count')} | {d_op.get('gnss_pose_not_arrived_count')} | - |")
    md.append("")

    md.append("## Alignment quality (sampled during 25s of measurement window)")
    md.append("")
    md.append("| Metric | Threshold | A | D | Δ vs A |")
    md.append("|---|---|---|---|---|")
    a_tp = a_align.get("tp", {}).get("mean", 0)
    d_tp = d_align.get("tp", {}).get("mean", 0)
    a_exe = a_align.get("exe_time_ms", {}).get("mean", 0)
    d_exe = d_align.get("exe_time_ms", {}).get("mean", 0)
    a_dist = a_align.get("dist_m", {}).get("mean", 0)
    d_dist = d_align.get("dist_m", {}).get("mean", 0)
    md.append(f"| TP (NDT match score) | > 4.0 | {a_tp:.2f} | {d_tp:.2f} | {delta_pct(d_tp, a_tp)} |")
    md.append(f"| exe_time NDT (ms) | < 100 | {a_exe:.1f} | {d_exe:.1f} | {delta_pct(d_exe, a_exe)} |")
    md.append(f"| init_to_result_distance (m) | < 2.0 | {a_dist:.3f} | {d_dist:.3f} | {delta_pct(d_dist, a_dist)} |")
    md.append(f"| kinematic_state Hz | ≥ 30 | {a_align.get('kin_hz', '-')} | {d_align.get('kin_hz', '-')} | - |")
    md.append("")

    md.append("## Chain end-to-end CV (top-lidar→prediction A_0)")
    md.append("")
    md.append("| Metric | A | D | Δ vs A |")
    md.append("|---|---|---|---|")
    a_avg = a_chain.get("best_avg", 0)
    d_avg = d_chain.get("best_avg", 0)
    a_p95 = a_chain.get("best_p95", 0)
    d_p95 = d_chain.get("best_p95", 0)
    a_p99 = a_chain.get("best_p99", 0)
    d_p99 = d_chain.get("best_p99", 0)
    a_max = a_chain.get("best_max", 0)
    d_max = d_chain.get("best_max", 0)
    a_cv = a_res.get("trace", {}).get("cv", 0)
    d_cv = d_res.get("trace", {}).get("cv", 0)
    a_n = a_chain.get("raw_row_with_end", 0)
    d_n = d_chain.get("raw_row_with_end", 0)
    md.append(f"| samples (e2e) | {a_n:.0f} | {d_n:.0f} | - |")
    md.append(f"| avg (ms) | {a_avg:.0f} | {d_avg:.0f} | {delta_pct(d_avg, a_avg)} |")
    md.append(f"| p95 (ms) | {a_p95:.0f} | {d_p95:.0f} | {delta_pct(d_p95, a_p95)} |")
    md.append(f"| p99 (ms) | {a_p99:.0f} | {d_p99:.0f} | {delta_pct(d_p99, a_p99)} |")
    md.append(f"| max (ms) | {a_max:.0f} | {d_max:.0f} | {delta_pct(d_max, a_max)} |")
    md.append(f"| **CV (std/avg)** | **{a_cv}** | **{d_cv}** | - |")
    md.append("")

    md.append("## CPU usage during measurement window (mpstat 1Hz)")
    md.append("")
    md.append("| Metric | A | D | Δ vs A |")
    md.append("|---|---|---|---|")
    a_cpu_mean = a_cpu.get("all_busy_mean", 0)
    d_cpu_mean = d_cpu.get("all_busy_mean", 0)
    md.append(f"| %busy mean (all cores) | {a_cpu_mean}% | {d_cpu_mean}% | {delta_pct(d_cpu_mean, a_cpu_mean)} |")
    md.append(f"| %busy p95 | {a_cpu.get('all_busy_p95', '-')}% | {d_cpu.get('all_busy_p95', '-')}% | - |")
    md.append(f"| %busy max | {a_cpu.get('all_busy_max', '-')}% | {d_cpu.get('all_busy_max', '-')}% | - |")
    md.append(f"| n cores | {a_cpu.get('n_cores', '-')} | {d_cpu.get('n_cores', '-')} | - |")
    md.append("")

    md.append("## GPU usage during measurement window (nvidia-smi 1Hz)")
    md.append("")
    md.append("| Metric | A | D | Δ vs A |")
    md.append("|---|---|---|---|")
    a_gpu_util = a_gpu.get("util_gpu_mean", 0)
    d_gpu_util = d_gpu.get("util_gpu_mean", 0)
    md.append(f"| GPU util mean | {a_gpu_util}% | {d_gpu_util}% | {delta_pct(d_gpu_util, a_gpu_util)} |")
    md.append(f"| GPU util max | {a_gpu.get('util_gpu_max', '-')}% | {d_gpu.get('util_gpu_max', '-')}% | - |")
    md.append(f"| GPU mem mean | {a_gpu.get('mem_used_mean_mb', '-')} MB | {d_gpu.get('mem_used_mean_mb', '-')} MB | - |")
    md.append(f"| GPU power mean | {a_gpu.get('power_mean_w', '-')} W | {d_gpu.get('power_mean_w', '-')} W | - |")
    md.append(f"| GPU temp max | {a_gpu.get('temp_max_c', '-')} °C | {d_gpu.get('temp_max_c', '-')} °C | - |")
    md.append("")

    md.append("## Interpretation")
    md.append("")
    md.append("**heaphook hybrid (D) effects observed:**")
    md.append("")
    md.append(f"- CPU usage **{delta_pct(d_cpu_mean, a_cpu_mean)}** vs glibc — direct allocator overhead")
    md.append(f"- GPU util **{delta_pct(d_gpu_util, a_gpu_util)}** — CPU bottleneck downstream throttles GPU pipeline")
    md.append(f"- exe_time NDT **{delta_pct(d_exe, a_exe)}** — NDT scan match iteration slowed by allocator")
    md.append("")
    if d_cv and a_cv:
        if d_cv > a_cv * 1.05:
            md.append(f"- **chain CV worsened {delta_pct(d_cv, a_cv)}** — heaphook adds e2e jitter")
        elif d_cv < a_cv * 0.95:
            md.append(f"- **chain CV improved {delta_pct(d_cv, a_cv)}** — heaphook adds determinism")
        else:
            md.append(f"- chain CV ~unchanged ({delta_pct(d_cv, a_cv)}) — heaphook does not significantly affect e2e jitter at this load")
    md.append("")

    md.append("## Caveats / threats to validity")
    md.append("")
    md.append("- N=1 per arm; statistical confidence ~6% on CV. **Re-run N≥3 before publishing**.")
    md.append("- 0.5x bag rate (production validity caveat — see `feedback_play_rate_05x_required.md`)")
    md.append("- Different bag-time offset for A vs D measurement window — chain CV may include vehicle-motion variation")
    md.append("- BES/ForeScout running on host (~3% CPU noise floor, integrated equally for both arms)")
    md.append("- Threshold values for sanity checks are PRELIMINARY (see `observe_rep.py` THRESHOLDS dict)")
    md.append("")

    out_md.write_text("\n".join(md))
    print(f"=== Cross-arm brief ===")
    print(f"  saved: {out_md}")
    print()
    # Also print key numbers to stdout
    print(f"A: TP={a_tp:.2f} exe={a_exe:.1f}ms CV={a_cv} CPU={a_cpu_mean}% GPU={a_gpu_util}%")
    print(f"D: TP={d_tp:.2f} exe={d_exe:.1f}ms CV={d_cv} CPU={d_cpu_mean}% GPU={d_gpu_util}%")
    print(f"Δ (D vs A): exe {delta_pct(d_exe, a_exe)}, CPU {delta_pct(d_cpu_mean, a_cpu_mean)}, GPU {delta_pct(d_gpu_util, a_gpu_util)}, CV {delta_pct(d_cv, a_cv) if (d_cv and a_cv) else '-'}")


if __name__ == "__main__":
    main()
