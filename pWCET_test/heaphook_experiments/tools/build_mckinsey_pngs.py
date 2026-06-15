#!/usr/bin/env python3
"""Generate 7 PNG charts for the McKinsey deck (Traditional Chinese).

F1  cv_cross_arm_bar.png        chain CV 跨 arm bar (N=5-6)
F2  cv_per_rep_strip.png         per-rep CV 分布
F3  cpu_vs_cv_tradeoff.png       CPU 成本 vs chain CV trade-off
F4  before_after_pause_artifact.png  21 秒 outlier 修正前後
F5  cpu_gpu_per_arm.png          CPU/GPU 用量
F6  memory_delta_per_arm.png     Track 1A 4 panel
F7  rss_vs_cv_tradeoff.png       RSS 成本 vs chain CV
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import numpy as np
from pathlib import Path

CJK_FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
CJK_FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FP = FontProperties(fname=CJK_FONT)
FP_BOLD = FontProperties(fname=CJK_FONT_BOLD)
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150

OUT_DIR = Path(__file__).parent.parent / "reports" / "figures" / "mckinsey"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# === DATA (2026-05-06 N=5-6 final) ===
A_CV = [0.310, 0.304, 0.354, 0.284, 0.246, 0.214]
D_CV = [0.275, 0.327, 0.308, 0.240, 0.275]
B_CV = [0.268, 0.189, 0.189, 0.194, 0.225]
KPI_TARGET = 0.15

A_MEAN = np.mean(A_CV); D_MEAN = np.mean(D_CV); B_MEAN = np.mean(B_CV)

A_CPU = 72.4; D_CPU = 78.2; B_CPU = 87.3
A_GPU = 51.9; D_GPU = 32.3; B_GPU = 25.1

A_MINFLT_DELTA = 461131
D_MINFLT_DELTA = 152745
B_MINFLT_DELTA = 146446
A_RSS_DELTA_MB = 1408.3
D_RSS_DELTA_MB = 1748.4
B_RSS_DELTA_MB = 1748.6
A_VOLCTX_DELTA = 101946
D_VOLCTX_DELTA = 7633
B_VOLCTX_DELTA = 92043
A_INVOLCTX_DELTA = 109408
D_INVOLCTX_DELTA = 57546
B_INVOLCTX_DELTA = 150170

COLOR_A = "#6c757d"
COLOR_D = "#3a7ca5"
COLOR_B = "#1d3557"
COLOR_KPI = "#c1121f"
COLOR_GOOD = "#2a9d8f"
COLOR_CAVEAT = "#e76f51"


def _apply_cjk(fig):
    """Apply CJK font to all text in figure."""
    for ax in fig.axes:
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_fontproperties(FP)
        if ax.get_xlabel():
            ax.xaxis.label.set_fontproperties(FP)
        if ax.get_ylabel():
            ax.yaxis.label.set_fontproperties(FP)
        if ax.get_title():
            ax.title.set_fontproperties(FP_BOLD)
        for txt in ax.texts:
            if txt.get_fontproperties().get_family()[0] != FP.get_family()[0]:
                txt.set_fontproperties(FP)
    if fig._suptitle:
        fig._suptitle.set_fontproperties(FP_BOLD)
    for txt in fig.texts:
        txt.set_fontproperties(FP)


def f1_cv_cross_arm_bar():
    fig, ax = plt.subplots(figsize=(8, 5))
    arms = ["A glibc", "D heaphook hybrid", "B stockpile"]
    means = [A_MEAN, D_MEAN, B_MEAN]
    ranges = [
        [A_MEAN - min(A_CV), max(A_CV) - A_MEAN],
        [D_MEAN - min(D_CV), max(D_CV) - D_MEAN],
        [B_MEAN - min(B_CV), max(B_CV) - B_MEAN],
    ]
    err = list(zip(*ranges))
    colors = [COLOR_A, COLOR_D, COLOR_B]
    bars = ax.bar(arms, means, yerr=err, capsize=8, color=colors,
                  alpha=0.85, edgecolor="black", linewidth=1.0)
    a_pct = 0
    d_pct = (D_MEAN - A_MEAN) / A_MEAN * 100
    b_pct = (B_MEAN - A_MEAN) / A_MEAN * 100
    deltas = ["baseline", f"{d_pct:+.1f}%", f"{b_pct:+.1f}%"]
    for i, (bar, d) in enumerate(zip(bars, deltas)):
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h + 0.025,
                f"{means[i]:.3f}\n{d}",
                ha="center", va="bottom", fontsize=12, fontweight="bold",
                fontproperties=FP_BOLD)
    ax.axhline(y=KPI_TARGET, color=COLOR_KPI, linestyle="--", linewidth=2)
    ax.text(2.4, KPI_TARGET + 0.005, f"KPI 目標 = {KPI_TARGET}",
            color=COLOR_KPI, fontsize=11, ha="right", va="bottom", fontweight="bold",
            fontproperties=FP_BOLD)
    ax.set_ylabel("Chain end-to-end CV (std/mean)", fontsize=13)
    ax.set_title("跨 arm chain CV — N=5-6 reps, 0.5x bag rate", fontsize=14, pad=15)
    ax.set_ylim(0, 0.42)
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)
    fig.text(0.5, 0.01, "Source: 18 reps total. Welch t-test  A vs D: p≈1.0 (沒差)  |  A vs B: p≈0.02 (顯著)",
             ha="center", fontsize=9, style="italic", color="#555")
    plt.tight_layout(rect=[0, 0.03, 1, 1])
    _apply_cjk(fig)
    fig.savefig(OUT_DIR / "f1_cv_cross_arm_bar.png", dpi=150)
    plt.close()
    print(f"✓ f1_cv_cross_arm_bar.png")


def f2_cv_per_rep_strip():
    fig, ax = plt.subplots(figsize=(8, 5))
    arm_data = [("A glibc", A_CV, COLOR_A), ("D heaphook hybrid", D_CV, COLOR_D), ("B stockpile", B_CV, COLOR_B)]
    for i, (name, vals, color) in enumerate(arm_data):
        x = np.full_like(vals, i, dtype=float) + np.random.uniform(-0.04, 0.04, len(vals))
        ax.scatter(x, vals, color=color, s=120, alpha=0.85, edgecolor="black", linewidth=1.2, zorder=3)
        ax.hlines(np.mean(vals), i - 0.18, i + 0.18, color=color, linewidth=2.5, zorder=2)
        ax.text(i + 0.22, np.mean(vals), f"mean\n{np.mean(vals):.3f}",
                fontsize=10, va="center", color=color, fontweight="bold", fontproperties=FP_BOLD)
    ax.axhline(y=KPI_TARGET, color=COLOR_KPI, linestyle="--", linewidth=2)
    ax.text(2.4, KPI_TARGET - 0.012, f"KPI = {KPI_TARGET}", color=COLOR_KPI,
            fontsize=11, ha="right", va="top", fontweight="bold", fontproperties=FP_BOLD)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels([f"A glibc\n(N={len(A_CV)})", f"D heaphook hybrid\n(N={len(D_CV)})", f"B stockpile\n(N={len(B_CV)})"], fontsize=12)
    ax.set_ylabel("Chain CV (std/mean)", fontsize=13)
    ax.set_title("每 rep CV 分布 — 點為單一 rep，橫線為平均", fontsize=14, pad=15)
    ax.set_ylim(0.10, 0.42)
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)
    ax.annotate("最接近 KPI\nB rep3 = 0.189", xy=(2, 0.189), xytext=(1.3, 0.16),
                fontsize=11, color=COLOR_B, fontweight="bold",
                fontproperties=FP_BOLD,
                arrowprops=dict(arrowstyle="->", color=COLOR_B, lw=1.5))
    fig.text(0.5, 0.01, "Source: 每 rep stats_path.yaml from caret_report. B rep1 cold-start dropped.",
             ha="center", fontsize=9, style="italic", color="#555")
    plt.tight_layout(rect=[0, 0.03, 1, 1])
    _apply_cjk(fig)
    fig.savefig(OUT_DIR / "f2_cv_per_rep_strip.png", dpi=150)
    plt.close()
    print(f"✓ f2_cv_per_rep_strip.png")


def f3_cpu_vs_cv_tradeoff():
    fig, ax = plt.subplots(figsize=(8, 5))
    arms = [("A glibc", A_CPU, A_MEAN, COLOR_A),
            ("D heaphook hybrid", D_CPU, D_MEAN, COLOR_D),
            ("B stockpile", B_CPU, B_MEAN, COLOR_B)]
    for name, cpu, cv, color in arms:
        ax.scatter(cpu, cv, color=color, s=400, alpha=0.85,
                   edgecolor="black", linewidth=1.5, zorder=3, label=name)
        ax.annotate(name, xy=(cpu, cv), xytext=(cpu + 1.5, cv),
                    fontsize=11, fontweight="bold", color=color, va="center",
                    fontproperties=FP_BOLD)
    cpus_sorted = sorted([(A_CPU, A_MEAN), (D_CPU, D_MEAN), (B_CPU, B_MEAN)])
    xs = [p[0] for p in cpus_sorted]; ys = [p[1] for p in cpus_sorted]
    ax.plot(xs, ys, "--", color="#999", alpha=0.6, linewidth=1.5, zorder=1)
    ax.axhline(y=KPI_TARGET, color=COLOR_KPI, linestyle="--", linewidth=2, alpha=0.7)
    ax.text(95, KPI_TARGET + 0.005, f"KPI = {KPI_TARGET}", color=COLOR_KPI,
            fontsize=10, ha="right", va="bottom", fontproperties=FP_BOLD)
    ax.set_xlabel("CPU all_busy 平均 (%)", fontsize=13)
    ax.set_ylabel("Chain CV", fontsize=13)
    ax.set_title("Trade-off：CPU 成本 vs Chain CV — 反向 monotonic", fontsize=14, pad=15)
    ax.set_xlim(65, 95)
    ax.set_ylim(0.13, 0.38)
    ax.grid(alpha=0.3)
    ax.set_axisbelow(True)
    ax.annotate("方向：CPU 多花 → CV 更穩",
                xy=(82, 0.22), xytext=(75, 0.34),
                fontsize=12, ha="center", fontweight="bold", color="#444",
                fontproperties=FP_BOLD,
                arrowprops=dict(arrowstyle="->", color="#444", lw=1.5))
    fig.text(0.5, 0.01, "Source: mpstat 1Hz × 30s window per rep. CV from stats_path.yaml.",
             ha="center", fontsize=9, style="italic", color="#555")
    plt.tight_layout(rect=[0, 0.03, 1, 1])
    _apply_cjk(fig)
    fig.savefig(OUT_DIR / "f3_cpu_vs_cv_tradeoff.png", dpi=150)
    plt.close()
    print(f"✓ f3_cpu_vs_cv_tradeoff.png")


def f4_before_after():
    fig, ax = plt.subplots(figsize=(8, 5))
    cats = ["前\n(A 0.5x rep1\n--immediate flag)", "後\n(canonical orch\n capture-after-resume)"]
    best_max = [21253, 484]
    cv_vals = [3.86, 0.304]
    bars = ax.bar(cats, best_max, color=[COLOR_KPI, COLOR_D],
                  alpha=0.85, edgecolor="black", linewidth=1.0, width=0.6)
    for bar, max_ms, cv in zip(bars, best_max, cv_vals):
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h + 500,
                f"max = {max_ms} ms\nCV = {cv}",
                ha="center", va="bottom", fontsize=12, fontweight="bold",
                fontproperties=FP_BOLD)
    ax.set_ylabel("chain best_max (ms) — 對數軸", fontsize=13)
    ax.set_yscale("log")
    ax.set_title("21 秒 outlier 已修 — capture-after-resume 把 wall-clock 污染砍掉",
                 fontsize=14, pad=15)
    ax.grid(axis="y", alpha=0.3, which="both")
    ax.set_axisbelow(True)
    ax.annotate("21097 ms = bag pause-burnin window\nchain instance 跨 pause → CARET wall-clock 吃進",
                xy=(0, 21253), xytext=(0.5, 6000),
                fontsize=10, ha="center", color="#555", style="italic",
                fontproperties=FP,
                arrowprops=dict(arrowstyle="->", color="#888", lw=1.0))
    fig.text(0.5, 0.01, "Source: A rep1 (14:57) vs A canonical reps — best_max from stats_path.yaml",
             ha="center", fontsize=9, style="italic", color="#555")
    plt.tight_layout(rect=[0, 0.03, 1, 1])
    _apply_cjk(fig)
    fig.savefig(OUT_DIR / "f4_before_after_pause_artifact.png", dpi=150)
    plt.close()
    print(f"✓ f4_before_after_pause_artifact.png")


def f5_cpu_gpu_per_arm():
    fig, ax = plt.subplots(figsize=(8, 5))
    arms = ["A glibc", "D heaphook hybrid", "B stockpile"]
    util = [A_GPU, D_GPU, B_GPU]
    cpu = [A_CPU, D_CPU, B_CPU]
    x = np.arange(len(arms))
    w = 0.36
    bars1 = ax.bar(x - w/2, cpu, w, label="CPU all_busy 平均 (%)",
                   color=[COLOR_A, COLOR_D, COLOR_B], alpha=0.85,
                   edgecolor="black", linewidth=1.0)
    bars2 = ax.bar(x + w/2, util, w, label="GPU 利用率 平均 (%)",
                   color=[COLOR_A, COLOR_D, COLOR_B], alpha=0.45,
                   edgecolor="black", linewidth=1.0, hatch="//")
    for bar, val in zip(list(bars1) + list(bars2), cpu + util):
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h + 1, f"{val:.0f}%",
                ha="center", va="bottom", fontsize=10, fontweight="bold",
                fontproperties=FP_BOLD)
    ax.set_xticks(x)
    ax.set_xticklabels(arms, fontsize=12)
    ax.set_ylabel("使用率 (%)", fontsize=13)
    ax.set_title("資源用量：CPU 漲 vs GPU 掉 — heaphook 推 CPU 反限 GPU pipeline",
                 fontsize=14, pad=15)
    ax.set_ylim(0, 100)
    leg = ax.legend(fontsize=11, loc="upper left", prop=FP)
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)
    fig.text(0.5, 0.01, "Source: mpstat / nvidia-smi 1Hz × 30s window per arm. Mean across N=2-3 reps.",
             ha="center", fontsize=9, style="italic", color="#555")
    plt.tight_layout(rect=[0, 0.03, 1, 1])
    _apply_cjk(fig)
    fig.savefig(OUT_DIR / "f5_cpu_gpu_per_arm.png", dpi=150)
    plt.close()
    print(f"✓ f5_cpu_gpu_per_arm.png")


def f6_memory_delta_per_arm():
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.5))
    arms = ["A glibc", "D heaphook hybrid", "B stockpile"]
    colors = [COLOR_A, COLOR_D, COLOR_B]
    WINDOW_S = 30

    # Panel 1: minflt rate
    ax = axes[0, 0]
    vals = [A_MINFLT_DELTA / WINDOW_S, D_MINFLT_DELTA / WINDOW_S, B_MINFLT_DELTA / WINDOW_S]
    bars = ax.bar(arms, vals, color=colors, alpha=0.85, edgecolor="black", linewidth=1.0)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width()/2, v + max(vals)*0.02,
                f"{v:,.0f}/s", ha="center", fontsize=10, fontweight="bold",
                fontproperties=FP_BOLD)
    ax.set_title("Minor page fault 速率 — pool 預配 vs lazy", fontsize=12)
    ax.set_ylabel("faults / 秒  (89-PID aggregate)")
    ax.grid(axis="y", alpha=0.3); ax.set_axisbelow(True)
    ax.text(1, vals[0]*0.5, "−67%", ha="center", fontsize=11, fontweight="bold", color=COLOR_GOOD,
            fontproperties=FP_BOLD)
    ax.text(2, vals[0]*0.5, "−68%", ha="center", fontsize=11, fontweight="bold", color=COLOR_GOOD,
            fontproperties=FP_BOLD)

    # Panel 2: RSS
    ax = axes[0, 1]
    vals = [A_RSS_DELTA_MB, D_RSS_DELTA_MB, B_RSS_DELTA_MB]
    bars = ax.bar(arms, vals, color=colors, alpha=0.85, edgecolor="black", linewidth=1.0)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width()/2, v + max(vals)*0.02,
                f"{v:.0f} MB", ha="center", fontsize=10, fontweight="bold",
                fontproperties=FP_BOLD)
    ax.set_title("ΔRSS（30 秒內）— pool 不釋放代價", fontsize=12)
    ax.set_ylabel("RSS Δ (MB)")
    ax.grid(axis="y", alpha=0.3); ax.set_axisbelow(True)
    ax.text(1, vals[0]*0.5, "+24%", ha="center", fontsize=11, fontweight="bold", color=COLOR_KPI,
            fontproperties=FP_BOLD)
    ax.text(2, vals[0]*0.5, "+24%", ha="center", fontsize=11, fontweight="bold", color=COLOR_KPI,
            fontproperties=FP_BOLD)

    # Panel 3: vol_ctx
    ax = axes[1, 0]
    vals = [A_VOLCTX_DELTA / WINDOW_S, D_VOLCTX_DELTA / WINDOW_S, B_VOLCTX_DELTA / WINDOW_S]
    bars = ax.bar(arms, vals, color=colors, alpha=0.85, edgecolor="black", linewidth=1.0)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width()/2, v + max(vals)*0.02,
                f"{v:,.0f}/s", ha="center", fontsize=10, fontweight="bold",
                fontproperties=FP_BOLD)
    ax.set_title("Δvol_ctx 速率 ★ — lock contention 直接訊號", fontsize=12)
    ax.set_ylabel("voluntary ctx switch / 秒")
    ax.grid(axis="y", alpha=0.3); ax.set_axisbelow(True)
    ax.text(1, vals[0]*0.5, "−93% ★", ha="center", fontsize=12, fontweight="bold", color=COLOR_GOOD,
            fontproperties=FP_BOLD)
    ax.text(2, vals[0]*0.5, "−10%", ha="center", fontsize=11, fontweight="bold", color="#888",
            fontproperties=FP_BOLD)

    # Panel 4: invol_ctx
    ax = axes[1, 1]
    vals = [A_INVOLCTX_DELTA / WINDOW_S, D_INVOLCTX_DELTA / WINDOW_S, B_INVOLCTX_DELTA / WINDOW_S]
    bars = ax.bar(arms, vals, color=colors, alpha=0.85, edgecolor="black", linewidth=1.0)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width()/2, v + max(vals)*0.02,
                f"{v:,.0f}/s", ha="center", fontsize=10, fontweight="bold",
                fontproperties=FP_BOLD)
    ax.set_title("Δinvol_ctx 速率 — scheduler thrash 警訊", fontsize=12)
    ax.set_ylabel("involuntary ctx switch / 秒")
    ax.grid(axis="y", alpha=0.3); ax.set_axisbelow(True)
    ax.text(1, vals[0]*0.5, "−47%", ha="center", fontsize=11, fontweight="bold", color=COLOR_GOOD,
            fontproperties=FP_BOLD)
    ax.text(2, vals[0]*0.5, "+37% ⚠", ha="center", fontsize=11, fontweight="bold", color=COLOR_KPI,
            fontproperties=FP_BOLD)

    fig.suptitle("Track 1A — 記憶體策略直接證據  |  N=3 per arm  |  0.5x bag rate, 30 秒窗",
                 fontsize=13)
    fig.text(0.5, 0.005,
             "Source: tools/snapshot_rss.sh pre/post during 30s measurement window. /proc/<pid>/{stat,status} aggregated across 89 PIDs.",
             ha="center", fontsize=9, style="italic", color="#555")
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    _apply_cjk(fig)
    fig.savefig(OUT_DIR / "f6_memory_delta_per_arm.png", dpi=150)
    plt.close()
    print(f"✓ f6_memory_delta_per_arm.png")


def f7_rss_vs_cv_tradeoff():
    fig, ax = plt.subplots(figsize=(8, 5))
    arms = [("A glibc", A_RSS_DELTA_MB, A_MEAN, COLOR_A),
            ("D heaphook hybrid", D_RSS_DELTA_MB, D_MEAN, COLOR_D),
            ("B stockpile", B_RSS_DELTA_MB, B_MEAN, COLOR_B)]
    for name, rss, cv, color in arms:
        ax.scatter(rss, cv, color=color, s=400, alpha=0.85,
                   edgecolor="black", linewidth=1.5, zorder=3, label=name)
        ax.annotate(name, xy=(rss, cv), xytext=(rss + 30, cv),
                    fontsize=11, fontweight="bold", color=color, va="center",
                    fontproperties=FP_BOLD)
    sorted_arms = sorted(arms, key=lambda a: a[1])
    xs = [a[1] for a in sorted_arms]; ys = [a[2] for a in sorted_arms]
    ax.plot(xs, ys, "--", color="#999", alpha=0.5, linewidth=1.5, zorder=1)
    ax.axhline(y=KPI_TARGET, color=COLOR_KPI, linestyle="--", linewidth=2, alpha=0.7)
    ax.text(1900, KPI_TARGET + 0.005, f"KPI = {KPI_TARGET}", color=COLOR_KPI,
            fontsize=10, ha="right", va="bottom", fontproperties=FP_BOLD)
    ax.set_xlabel("ΔRSS（30 秒內，MB）— pool 預配代價", fontsize=12)
    ax.set_ylabel("Chain CV（每 arm 平均）", fontsize=12)
    ax.set_title("Trade-off 第二軸：RSS 代價 vs Chain CV — memory 預配買 jitter 改善",
                 fontsize=13, pad=15)
    ax.set_xlim(1300, 1900)
    ax.set_ylim(0.18, 0.36)
    ax.grid(alpha=0.3)
    ax.set_axisbelow(True)
    fig.text(0.5, 0.01,
             "Source: rss_pre.txt vs rss_post.txt 30s window. Trade-off 軸從 CPU（F3）+ RSS（F7）兩維解讀。",
             ha="center", fontsize=9, style="italic", color="#555")
    plt.tight_layout(rect=[0, 0.03, 1, 1])
    _apply_cjk(fig)
    fig.savefig(OUT_DIR / "f7_rss_vs_cv_tradeoff.png", dpi=150)
    plt.close()
    print(f"✓ f7_rss_vs_cv_tradeoff.png")


if __name__ == "__main__":
    f1_cv_cross_arm_bar()
    f2_cv_per_rep_strip()
    f3_cpu_vs_cv_tradeoff()
    f4_before_after()
    f5_cpu_gpu_per_arm()
    f6_memory_delta_per_arm()
    f7_rss_vs_cv_tradeoff()
    print(f"\n7 PNGs saved to {OUT_DIR}")
