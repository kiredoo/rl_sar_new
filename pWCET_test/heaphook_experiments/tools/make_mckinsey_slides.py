#!/usr/bin/env python3
"""Render McKinsey-consultant-grade slide PNGs for the M0' POC results.

Each slide is a single 16:9 PNG (1920×1080 paper-DPI) with:
  - Strong action-title (the conclusion, not the topic)
  - One key insight visualised
  - Supporting data inline
  - McKinsey-style hierarchy: title bar / chart area / takeaway box

Slides:
  01_executive_summary       — 1-line headline + 3 KPIs
  02_methodology             — 4 arms × N=2 × Tier 0 sampler-ON × protocol-3stage
  03_minflt                  — D-v4 leads by 1 pp; uses m0prime_estimation_minflt_n2.png as base
  04_rss_growth              — D-v4 leads by 6 pp; uses m0prime_estimation_rss_delta_n2.png
  05_rss_pre_tradeoff        — B leads by 58 pp on rss_pre (architectural cost)
  06_d_v4_reproducibility    — variance 0.01 % vs A's 8.8 %
  07_sampler_dependent_rank  — sampler-OFF vs sampler-ON ranking flip
  08_what_we_did_not_prove   — bounded WCET is unmeasured
  09_recommendation          — Schedule v5 next-steps
  10_audit_chain             — exp_settings.tsv as evidence anchor

Run:
  cd ~/repo/claude_ws4/heaphook_experiments
  python3 tools/make_mckinsey_slides.py --output reports/figures/slides_m0prime/
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch
import matplotlib.image as mpimg

sys.path.insert(0, str(Path(__file__).parent))
import figstyle


SLIDE_W, SLIDE_H = 16, 9   # inches; at 120 DPI = 1920×1080
# CJK font fallback so 麥肯錫白話 + 中文 actually render in PNGs.
# Noto Sans CJK is available on this host (`fc-list | grep CJK`).
matplotlib.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "DejaVu Sans"]
matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["axes.unicode_minus"] = False
NAVY = "#1F2A44"
ACCENT = "#0B7AB8"
GREEN = "#2C9F4F"
RED = "#CC3311"
GREY_LIGHT = "#E5E7EA"
GREY_DARK = "#5A5F66"


def _slide_skeleton(title: str, subtitle: str = ""):
    """Return (fig, content_ax) with title bar drawn at top."""
    fig = plt.figure(figsize=(SLIDE_W, SLIDE_H), dpi=120)
    fig.patch.set_facecolor("white")

    title_h = 0.18
    fig.text(0.04, 1 - title_h * 0.55, title,
             fontsize=24, fontweight="bold", color=NAVY, va="center")
    if subtitle:
        fig.text(0.04, 1 - title_h * 0.85, subtitle,
                 fontsize=13, color=GREY_DARK, va="center")
    fig.add_artist(plt.Line2D([0.04, 0.96], [1 - title_h - 0.005, 1 - title_h - 0.005],
                              color=ACCENT, linewidth=3, transform=fig.transFigure))

    # Footer
    fig.text(0.04, 0.04, "AGA Gen2 L0 Evidence Plane · POC 2026-04-30 · M0' N=2 (sampler-ON · protocol-3stage_flow6_burnin10)",
             fontsize=9, color=GREY_DARK)
    fig.text(0.96, 0.04, "heaphook_experiments / cross_abcd_v4.md § R-v3",
             fontsize=9, color=GREY_DARK, ha="right")

    content_ax = fig.add_axes([0.04, 0.10, 0.92, 1 - title_h - 0.16])
    content_ax.axis("off")
    return fig, content_ax


def _takeaway_box(fig, text: str, y: float = 0.135):
    """Bottom takeaway box, full-width."""
    bbox = FancyBboxPatch(
        (0.04, y - 0.025), 0.92, 0.06,
        boxstyle="round,pad=0.005,rounding_size=0.005",
        linewidth=0, facecolor=GREY_LIGHT, transform=fig.transFigure
    )
    fig.patches.append(bbox)
    fig.text(0.06, y + 0.005, "TAKEAWAY", fontsize=10, fontweight="bold",
             color=NAVY, va="center")
    fig.text(0.13, y + 0.005, text, fontsize=12, color=NAVY, va="center")


def slide_01_summary(out: Path):
    fig, ax = _slide_skeleton(
        "F1-F4 + G1 hybrid binary works; under sampler-ON parity D-v4 has a 1 pp Δminflt + 6 pp ΔRSS edge over stockpile",
        "M0' POC headline · 6 reps · 3 arms · sampler-ON · protocol-3stage_flow6_burnin10")

    # Three KPI cards horizontally
    kpis = [
        ("Δminflt vs A", "−78.2 %", "(D-v4)", "D-v4 narrowly beats B (−77.3 %)", GREEN),
        ("ΔRSS vs A",    "−28.6 %", "(D-v4)", "D-v4 wins by ~6 pp over B (−22.8 %)", GREEN),
        ("rss_pre vs A", "+49.6 %", "(D-v4)", "B is leaner (−7.8 %) — trade-off axis", RED),
    ]
    n = len(kpis)
    margin_x = 0.05
    box_w = (1 - 2 * margin_x - 0.04 * (n - 1)) / n
    gap = 0.04
    y0 = 0.30
    box_h = 0.36
    for i, (label, big, sub, foot, color) in enumerate(kpis):
        x0 = margin_x + i * (box_w + gap)
        bbox = FancyBboxPatch(
            (x0, y0), box_w, box_h,
            boxstyle="round,pad=0.005,rounding_size=0.012",
            linewidth=2, edgecolor=color, facecolor="white",
            transform=fig.transFigure
        )
        fig.patches.append(bbox)
        fig.text(x0 + box_w / 2, y0 + box_h - 0.04, label, fontsize=14,
                 color=GREY_DARK, ha="center", va="top", fontweight="bold")
        fig.text(x0 + box_w / 2, y0 + box_h * 0.55, big, fontsize=42,
                 color=color, ha="center", va="center", fontweight="bold")
        fig.text(x0 + box_w / 2, y0 + box_h * 0.32, sub, fontsize=12,
                 color=GREY_DARK, ha="center", va="center")
        fig.text(x0 + box_w / 2, y0 + 0.04, foot, fontsize=10,
                 color=NAVY, ha="center", va="bottom")

    _takeaway_box(fig, "Hybrid (D-v4) edges out stockpile (B) on dynamic memory metrics under realistic profiling conditions, while still paying the architectural rss_pre cost.")
    fig.savefig(out)
    plt.close(fig)


def slide_02_method(out: Path):
    fig, ax = _slide_skeleton(
        "Methodology — 4 arms × N=2 × Tier 0 sampler-ON × protocol-3stage_flow6_burnin10",
        "Apples-to-apples cross-arm comparison · evidence-chain anchored via env/exp_settings_<arm>.tsv per rep")

    rows = [
        ("Arm A (glibc baseline)", "pure glibc malloc · no LD_PRELOAD", "20260430-1606 / 1609", "—"),
        ("Arm B (stockpile)",      "libpreloaded_stockpile.so",         "20260430-1612 / 1616", "6fd1e556…"),
        ("Arm C (hybrid-unfixed)", "failure mode · 88 aborts · historical only", "(2026-04-21 + 22)", "(historical)"),
        ("Arm D-v4 (hybrid-fixed)", "libpreloaded_hybrid_o1heap_tlsf.so · F1-F4 + G1", "20260430-1619 / 1622", "4e7cb31d…"),
    ]
    cols = ["arm", "binary", "run_ids", "sha256"]
    col_widths = [0.20, 0.40, 0.22, 0.18]

    # Header
    x = 0.04
    y = 0.78
    for c, w in zip(cols, col_widths):
        ax.text(x + 0.005, y, c, fontsize=11, fontweight="bold", color=NAVY, transform=fig.transFigure)
        x += w
    fig.add_artist(plt.Line2D([0.04, 0.96], [y - 0.012, y - 0.012], color=NAVY, transform=fig.transFigure, linewidth=1.5))

    # Rows
    for i, row in enumerate(rows):
        ry = y - 0.05 - i * 0.06
        if i % 2 == 0:
            bg = FancyBboxPatch((0.04, ry - 0.018), 0.92, 0.05,
                                boxstyle="round,pad=0,rounding_size=0",
                                linewidth=0, facecolor=GREY_LIGHT, transform=fig.transFigure)
            fig.patches.append(bg)
        x = 0.04
        for v, w in zip(row, col_widths):
            ax.text(x + 0.005, ry, v, fontsize=11, color=NAVY,
                    transform=fig.transFigure, va="center")
            x += w

    # Settings panel
    sx, sy = 0.04, 0.30
    bbox = FancyBboxPatch((sx, sy - 0.04), 0.92, 0.20,
                          boxstyle="round,pad=0.005,rounding_size=0.012",
                          linewidth=2, edgecolor=ACCENT, facecolor="white",
                          transform=fig.transFigure)
    fig.patches.append(bbox)
    fig.text(sx + 0.015, sy + 0.135, "Per-rep instrumentation (every rep)",
             fontsize=12, fontweight="bold", color=ACCENT)
    settings_lines = [
        "• Tier 0 sampler ON · SMAPS_TOP_K=20 · SMAPS_PERIOD_MS=10000 · per-PID PSS / cgroup memory.stat / PSI",
        "• Bag protocol: BAG_FLOW_S=6 + BAG_BURNIN_S=10 (3-stage flow → pause → burn-in → resume)",
        "• env/exp_settings_<arm>.tsv (schema=1) records every knob + sha256 — reports cite run_id → one-step recipe lookup",
        "• Bag: ~/autoware_map/sample-rosbag at rate 1.0 (~30 s) · pgrep filter ~89 Autoware procs",
        "• N=2 reps per arm · paired bootstrap 10 k iters seed=42 for cross-arm Δ + 95 % CI",
    ]
    for j, line in enumerate(settings_lines):
        fig.text(sx + 0.015, sy + 0.10 - j * 0.022, line, fontsize=10.5,
                 color=NAVY, va="top")

    _takeaway_box(fig, "Every cell traceable from report number → run_id → env/exp_settings.tsv → cryptographic sha256 anchor.")
    fig.savefig(out)
    plt.close(fig)


def slide_with_figure(out: Path, action_title: str, subtitle: str, figure_path: Path, takeaway: str):
    """Generic slide: action title + embedded figure + takeaway."""
    fig, ax = _slide_skeleton(action_title, subtitle)
    if figure_path.exists():
        img = mpimg.imread(figure_path)
        # Place image in centre-content area
        img_ax = fig.add_axes([0.06, 0.18, 0.88, 0.62])
        img_ax.imshow(img)
        img_ax.axis("off")
    else:
        ax.text(0.5, 0.5, f"(figure not found: {figure_path})", ha="center",
                color=RED, transform=fig.transFigure)
    _takeaway_box(fig, takeaway)
    fig.savefig(out)
    plt.close(fig)


def slide_02b_what_we_fixed(out: Path):
    """McKinsey-白話 view of arm C -> arm D-v4 fix bundle."""
    fig, ax = _slide_skeleton(
        "F1-F4 + G1 fixes turned a broken allocator (arm C) into a clean one (arm D-v4) — 5 root causes resolved",
        "From 88 aborts + 89 grep OOM (arm C, unusable) to 4 aborts + 0 OOM (arm D-v4, glibc baseline parity)")

    # Big "before / after" comparison at top
    bar_y = 0.71
    bar_h = 0.10

    # Before card (arm C)
    bbox_b = FancyBboxPatch((0.04, bar_y), 0.42, bar_h,
                            boxstyle="round,pad=0.005,rounding_size=0.012",
                            linewidth=2, edgecolor=RED, facecolor="white",
                            transform=fig.transFigure)
    fig.patches.append(bbox_b)
    fig.text(0.06, bar_y + bar_h - 0.025, "arm C — unfixed hybrid (broken)",
             fontsize=12, color=RED, fontweight="bold")
    fig.text(0.06, bar_y + bar_h - 0.055, "88 aborts (terminate fail) · 89 grep OOM (memory exhausted)",
             fontsize=10.5, color=NAVY)
    fig.text(0.06, bar_y + 0.015, "→ unusable for any production claim",
             fontsize=10, color=GREY_DARK, fontstyle="italic")

    # Arrow
    fig.text(0.50, bar_y + bar_h / 2, "→", fontsize=40, color=ACCENT,
             ha="center", va="center", fontweight="bold")
    fig.text(0.50, bar_y - 0.005, "F1-F4 + G1", fontsize=10,
             color=ACCENT, ha="center", fontweight="bold")

    # After card (arm D-v4)
    bbox_a = FancyBboxPatch((0.54, bar_y), 0.42, bar_h,
                            boxstyle="round,pad=0.005,rounding_size=0.012",
                            linewidth=2, edgecolor=GREEN, facecolor="white",
                            transform=fig.transFigure)
    fig.patches.append(bbox_a)
    fig.text(0.56, bar_y + bar_h - 0.025, "arm D-v4 — F1-F4 + G1 fixed (clean)",
             fontsize=12, color=GREEN, fontweight="bold")
    fig.text(0.56, bar_y + bar_h - 0.055, "4 aborts · 0 grep OOM · matches glibc baseline (arm A)",
             fontsize=10.5, color=NAVY)
    fig.text(0.56, bar_y + 0.015, "→ clean run, ready for cross-allocator comparison",
             fontsize=10, color=GREY_DARK, fontstyle="italic")

    # Five fix cards in a row
    fixes = [
        ("F1",
         "資料結構並發保護",
         "多 thread 同時建分配池 → 重複建立 + 記憶體洩漏",
         "在桶鎖內 find-then-insert，closes 3 audit bugs"),
        ("F2",
         "啟動 NULL 防呆",
         "mmap 失敗或 pool 還沒備好 → SEGV crash",
         "MAP_FAILED + NULL handle 全路徑容錯"),
        ("F3",
         "動態容器邊界檢查",
         "擴容時陣列越界寫入 → 後鄰自旋鎖被破壞",
         "鎖內二次檢查邊界，OOB 寫入不可能"),
        ("F4",
         "預設初始化安全",
         "未初始化 wrapper 一被呼叫就 SEGV",
         "default-construct 即合法、操作即 no-op"),
        ("G1",
         "統計數字可信度",
         "計數器跨 thread 寫，遺失更新 → 數字不可信",
         "std::atomic<size_t> + fetch_add；報告數字權威"),
    ]
    n = len(fixes)
    margin = 0.04
    gap = 0.018
    box_w = (1 - 2 * margin - (n - 1) * gap) / n
    y0 = 0.20
    box_h = 0.40

    import textwrap
    # Approx chinese-char width for the box (CJK chars are wider).
    # Empirical: 14 CJK chars per ~0.18 figure-width (~16 inch slide).
    chars_per_box = max(8, int(box_w * 80))

    for i, (id_, title, problem, fix) in enumerate(fixes):
        x0 = margin + i * (box_w + gap)
        bbox = FancyBboxPatch((x0, y0), box_w, box_h,
                              boxstyle="round,pad=0.005,rounding_size=0.012",
                              linewidth=2, edgecolor=ACCENT, facecolor="white",
                              transform=fig.transFigure)
        fig.patches.append(bbox)
        # ID badge
        bid = FancyBboxPatch((x0 + 0.005, y0 + box_h - 0.05), 0.04, 0.038,
                             boxstyle="round,pad=0.002,rounding_size=0.006",
                             linewidth=0, facecolor=ACCENT,
                             transform=fig.transFigure)
        fig.patches.append(bid)
        fig.text(x0 + 0.005 + 0.02, y0 + box_h - 0.05 + 0.038 / 2, id_,
                 fontsize=12, fontweight="bold", color="white",
                 ha="center", va="center")
        # Title
        fig.text(x0 + 0.05, y0 + box_h - 0.045, title,
                 fontsize=11.5, fontweight="bold", color=NAVY, va="top")
        # Problem (red label + wrapped text)
        fig.text(x0 + 0.005, y0 + box_h - 0.10,
                 "原本問題", fontsize=8, color=RED,
                 fontweight="bold", va="top")
        problem_wrapped = "\n".join(textwrap.wrap(problem, width=chars_per_box))
        fig.text(x0 + 0.005, y0 + box_h - 0.125, problem_wrapped,
                 fontsize=9.2, color=NAVY, va="top")
        # Fix (green label + wrapped text)
        fig.text(x0 + 0.005, y0 + 0.10,
                 "修法", fontsize=8, color=GREEN,
                 fontweight="bold", va="top")
        fix_wrapped = "\n".join(textwrap.wrap(fix, width=chars_per_box))
        fig.text(x0 + 0.005, y0 + 0.075, fix_wrapped,
                 fontsize=9.2, color=NAVY, va="top")

    _takeaway_box(fig, "5 個獨立但鄰近的根因 — 每個都可能被誤以為是 hybrid 設計缺陷；其實是實作 bug，靠 audit + TDD 5 個 commit 全收掉。")
    fig.savefig(out)
    plt.close(fig)


def slide_06_reproducibility(out: Path):
    fig, ax = _slide_skeleton(
        "D-v4 reproducibility 0.01 % — 3 orders of magnitude tighter than glibc",
        "rep1 vs rep2 Δminflt variance · same binary · same host · same 30 s bag")

    arms = [("A glibc",   1080142, 1175011, "8.8 %",  RED),
            ("B stockpile", 261371,  251078, "4.0 %",  ACCENT),
            ("D-v4 hybrid", 245351,  245315, "0.01 %", GREEN)]

    n = len(arms)
    box_w = 0.27
    gap = 0.038
    margin_x = (1 - n * box_w - (n - 1) * gap) / 2
    y0 = 0.26
    box_h = 0.50

    for i, (label, r1, r2, var, color) in enumerate(arms):
        x0 = margin_x + i * (box_w + gap)
        # Card
        bbox = FancyBboxPatch((x0, y0), box_w, box_h,
                              boxstyle="round,pad=0.005,rounding_size=0.012",
                              linewidth=2, edgecolor=color, facecolor="white",
                              transform=fig.transFigure)
        fig.patches.append(bbox)
        fig.text(x0 + box_w / 2, y0 + box_h - 0.045, label, fontsize=16,
                 color=NAVY, ha="center", fontweight="bold")
        # Two reps as points
        cx = x0 + box_w / 2
        rep_y = y0 + 0.32
        fig.text(cx, rep_y + 0.04, "rep1", fontsize=10, color=GREY_DARK, ha="center")
        fig.text(cx, rep_y, f"{r1:,}", fontsize=18, color=NAVY, ha="center", fontweight="bold")
        fig.text(cx, rep_y - 0.05, "rep2", fontsize=10, color=GREY_DARK, ha="center")
        fig.text(cx, rep_y - 0.09, f"{r2:,}", fontsize=18, color=NAVY, ha="center", fontweight="bold")
        # Variance big
        fig.text(cx, y0 + 0.04, var, fontsize=32, color=color, ha="center",
                 fontweight="bold")
        fig.text(cx, y0 + 0.012, "rep1↔rep2 variance", fontsize=9,
                 color=GREY_DARK, ha="center")

    _takeaway_box(fig, "D-v4 produces near-identical Δminflt across reps — empirical signal that hybrid bounded-allocation translates into bounded measurement noise. Layer 2 CARET (Session 10) will test if this carries to e2e jitter.")
    fig.savefig(out)
    plt.close(fig)


def slide_07_sampler_flip(out: Path):
    fig, ax = _slide_skeleton(
        "Cross-arm ranking depends on sampler mode — perturbation is allocator-specific",
        "Δminflt vs A glibc · same binaries · same bag · only sampler ON/OFF differs")

    rows = [
        ("A glibc",   "−1.5 %",  ACCENT),
        ("D-v4 hybrid", "+11 %",  ACCENT),
        ("B stockpile", "+48 %",  RED),
    ]
    # Sampler perturbation per arm
    px = 0.06
    py = 0.66
    fig.text(px, py + 0.10, "Sampler tax (sampler-ON vs sampler-OFF Δminflt)", fontsize=14,
             fontweight="bold", color=NAVY)
    fig.text(px, py + 0.07, "Why: glibc tcache absorbs the smaps_rollup ancillary mallocs · stockpile global pool serializes them",
             fontsize=10, color=GREY_DARK)
    for i, (label, val, color) in enumerate(rows):
        ly = py - i * 0.045
        fig.text(px + 0.005, ly, label, fontsize=12, color=NAVY, va="center")
        fig.text(px + 0.20, ly, val, fontsize=18, color=color, va="center",
                 fontweight="bold")

    # Two ranking columns: sampler-OFF vs sampler-ON
    fig.text(0.06, 0.40, "Cross-arm ranking flips between regimes:", fontsize=13,
             fontweight="bold", color=NAVY)

    box_w = 0.42
    box_h = 0.22
    gap = 0.04
    bx_off = 0.06
    bx_on = bx_off + box_w + gap
    by = 0.16

    # OFF
    bbox_off = FancyBboxPatch((bx_off, by), box_w, box_h,
                              boxstyle="round,pad=0.005,rounding_size=0.012",
                              linewidth=2, edgecolor=GREY_DARK, facecolor=GREY_LIGHT,
                              transform=fig.transFigure)
    fig.patches.append(bbox_off)
    fig.text(bx_off + 0.015, by + box_h - 0.025, "Sampler-OFF (apples-to-apples)",
             fontsize=12, fontweight="bold", color=NAVY)
    fig.text(bx_off + 0.015, by + box_h - 0.06,
             "B  Δminflt −83 %  ←  WINS", fontsize=11.5, color=GREEN, fontweight="bold")
    fig.text(bx_off + 0.015, by + box_h - 0.085,
             "D-v4 Δminflt −79 %", fontsize=11.5, color=NAVY)
    fig.text(bx_off + 0.015, by + box_h - 0.115,
             "B leads by 4 pp under sampler-OFF",
             fontsize=10, color=GREY_DARK, fontstyle="italic")

    # ON
    bbox_on = FancyBboxPatch((bx_on, by), box_w, box_h,
                             boxstyle="round,pad=0.005,rounding_size=0.012",
                             linewidth=2, edgecolor=ACCENT, facecolor="white",
                             transform=fig.transFigure)
    fig.patches.append(bbox_on)
    fig.text(bx_on + 0.015, by + box_h - 0.025, "Sampler-ON (M0' apples-to-apples · production-like)",
             fontsize=12, fontweight="bold", color=ACCENT)
    fig.text(bx_on + 0.015, by + box_h - 0.06,
             "D-v4 Δminflt −78.2 %  ←  WINS", fontsize=11.5, color=GREEN, fontweight="bold")
    fig.text(bx_on + 0.015, by + box_h - 0.085,
             "B Δminflt −77.3 %", fontsize=11.5, color=NAVY)
    fig.text(bx_on + 0.015, by + box_h - 0.115,
             "D-v4 leads by 1 pp because B suffers more sampler tax",
             fontsize=10, color=GREY_DARK, fontstyle="italic")

    _takeaway_box(fig, "Honest cross-arm Δ requires declaring the sampler mode column. Production-like (sampler-ON) measurement gives D-v4 the edge.")
    fig.savefig(out)
    plt.close(fig)


def slide_08_not_proven(out: Path):
    fig, ax = _slide_skeleton(
        "What M0' did NOT prove — bounded WCET (the actual product KPI) remains unmeasured",
        "Tesla measurement discipline: bind every claim to existing measurement")

    cells = [
        ("✅ proven", [
            "F1-F4 + G1 produces a working hybrid binary",
            "D-v4 −78 % page faults vs A glibc (sampler-ON, N=2, CI excludes zero)",
            "D-v4 reproducibility 0.01 % across reps (binary determinism signal)",
            "CARET trace capture pipeline works on this host (62 MB UST trace verified)",
            "Sampler perturbation is allocator-specific — quantified per arm",
        ], GREEN),
        ("❌ NOT proven", [
            "Bounded e2e callback / chain latency jitter (the actual product KPI)",
            "Bounded per-call malloc latency (Layer 1 — necessary precondition)",
            "Long-soak (15+ min) leak / fragmentation drift / OOM stability",
            "Cross-host reproducibility · alternative bag · rate sweep",
            "Functional behaviour (rviz pose, NDT iter, planning latency) recorded",
            "F1 memory-model UB safe in release (formal proof; release builds work today)",
        ], RED),
    ]

    n = len(cells)
    margin = 0.04
    gap = 0.04
    box_w = (1 - 2 * margin - gap) / n
    y0 = 0.26
    box_h = 0.50

    for i, (header, items, color) in enumerate(cells):
        x0 = margin + i * (box_w + gap)
        bbox = FancyBboxPatch((x0, y0), box_w, box_h,
                              boxstyle="round,pad=0.005,rounding_size=0.012",
                              linewidth=2, edgecolor=color, facecolor="white",
                              transform=fig.transFigure)
        fig.patches.append(bbox)
        fig.text(x0 + box_w / 2, y0 + box_h - 0.04, header, fontsize=16,
                 fontweight="bold", color=color, ha="center")
        for j, line in enumerate(items):
            fig.text(x0 + 0.015, y0 + box_h - 0.09 - j * 0.045,
                     "• " + line, fontsize=10.5, color=NAVY, va="top")

    _takeaway_box(fig, "Schedule v5 places the load-bearing experiment (CARET Layer 2 jitter) at Session 10 — 2 sessions from milestone close, not at the end.")
    fig.savefig(out)
    plt.close(fig)


def slide_09_recommendation(out: Path):
    fig, ax = _slide_skeleton(
        "Schedule v5 — Layer 2 (CARET jitter) is the milestone-closing experiment, run NEXT",
        "Karpathy / Tesla principle: cheapest PASS / FAIL test of central hypothesis runs first")

    sessions = [
        ("Session  9",  "C15 protocol fix side-by-side · M2 Tier 0 metrics · caret_report smoke",          "30-90 min", ACCENT),
        ("Session 10",  "CARET Layer 2 jitter N=2 × 3 arm  ⭐ MILESTONE CLOSER",                            "~3 hr",    GREEN),
        ("Session 11",  "Layer 1 alloc latency (bcc / bpftrace) · Phase 3 S0 selective-apply prototype",   "1 day",    ACCENT),
        ("Session 12",  "M4 Phase 2.5b D-v4 frag (O1heap + TLSF FragProvider via audit_v2 G2-G4 decouple)", "1 day",    ACCENT),
        ("Session 13",  "M5 synthesis_v1 close · DECISIONS PASS / PARTIAL row",                             "0.5 day",  GREEN),
        ("Session 14",  "long-soak A + B + D-v4 with full Tier 0 + frag + Layer 1 + Layer 2",               "1 day",    ACCENT),
    ]

    fig.text(0.05, 0.78, "Re-prioritised Sessions 9-14 (synthesis_v1.md § 11.2)",
             fontsize=14, fontweight="bold", color=NAVY)

    y0 = 0.71
    row_h = 0.085
    for i, (sess, content, dur, color) in enumerate(sessions):
        ry = y0 - i * row_h
        # Session label box
        bbox_s = FancyBboxPatch((0.05, ry - 0.026), 0.10, 0.045,
                                boxstyle="round,pad=0.003,rounding_size=0.005",
                                linewidth=0, facecolor=color,
                                transform=fig.transFigure)
        fig.patches.append(bbox_s)
        fig.text(0.10, ry - 0.005, sess, fontsize=11.5, fontweight="bold",
                 color="white", ha="center", va="center")
        fig.text(0.17, ry - 0.005, content, fontsize=11, color=NAVY,
                 va="center")
        fig.text(0.92, ry - 0.005, dur, fontsize=10, color=GREY_DARK,
                 ha="right", va="center")

    # Three pre-registered gates panel
    gx, gy = 0.05, 0.16
    bbox_g = FancyBboxPatch((gx, gy - 0.04), 0.90, 0.06,
                            boxstyle="round,pad=0.005,rounding_size=0.012",
                            linewidth=2, edgecolor=GREEN, facecolor="white",
                            transform=fig.transFigure)
    fig.patches.append(bbox_g)
    fig.text(gx + 0.012, gy + 0.005, "Pre-registered fail-fast gates:", fontsize=10.5,
             fontweight="bold", color=GREEN, va="center")
    fig.text(gx + 0.18, gy + 0.005,
             "G-protocol (Session 9)  ·  G-jitter (Session 10) ⭐  ·  G-S0 (Session 11)",
             fontsize=10.5, color=NAVY, va="center")

    _takeaway_box(fig, "Six sessions to milestone close. The single load-bearing experiment is in Session 10. PASS → hybrid story closes; FAIL → pivot to S0 selective-apply or alt allocators.", y=0.085)
    fig.savefig(out)
    plt.close(fig)


def slide_10_audit(out: Path):
    fig, ax = _slide_skeleton(
        "Evidence chain — every number in this deck has a one-step path to the recipe",
        "Reports cite run_id · run_id has env/exp_settings_<arm>.tsv · TSV sha256 is the cryptographic anchor")

    code = """env/exp_settings_A.tsv  (schema=1, written by tools/run_ab_phase.sh at phase start)
─────────────────────────────────────────────────────────────────────
key                          value
arm                          A
phase_started_at             2026-04-30T08:06:52Z
host                         52-0b30668-05
kernel                       6.8.0-40-generic
ros_distro                   unknown
rmw_implementation           rmw_cyclonedds_cpp
ros_domain_id                4
play_rate                    1
bag_path                     /home/aga_pc1a/autoware_map/sample-rosbag
protocol_mode                3stage_flow6_burnin10
bag_flow_s                   6
bag_burnin_s                 10
smaps_top_k                  20
smaps_period_ms              10000
tier0_sampler                on
caret_libcaret_loaded        off
caret_record_active          off
heaphook_so_path             (none)
heaphook_so_sha256           (n/a)
heaphook_so_size_bytes       (n/a)
─────────────────────────────────────────────────────────────────────"""

    ax.text(0.5, 0.85, code, family="monospace", fontsize=9.5, color=NAVY,
            transform=fig.transFigure, ha="center", va="top")

    chain_y = 0.20
    chain_steps = [
        ("synthesis_v1.md § 1", "headline"),
        ("cross_abcd_v4.md § R-v3", "data table"),
        ("runs/<id>/MANIFEST.md", "## Experiment settings"),
        ("env/exp_settings_<arm>.tsv", "schema=1 + sha256"),
    ]
    fig.text(0.5, chain_y + 0.04, "Audit chain (one click per step)", fontsize=12,
             fontweight="bold", color=NAVY, ha="center")

    n = len(chain_steps)
    margin = 0.05
    box_w = (1 - 2 * margin) / n - 0.025
    gap = 0.025
    bx0 = margin
    by = chain_y - 0.045
    for i, (label, sub) in enumerate(chain_steps):
        x = bx0 + i * (box_w + gap)
        bbox = FancyBboxPatch((x, by), box_w, 0.06,
                              boxstyle="round,pad=0.005,rounding_size=0.012",
                              linewidth=2, edgecolor=ACCENT, facecolor="white",
                              transform=fig.transFigure)
        fig.patches.append(bbox)
        fig.text(x + box_w / 2, by + 0.044, label, fontsize=10,
                 fontweight="bold", color=NAVY, ha="center")
        fig.text(x + box_w / 2, by + 0.018, sub, fontsize=9,
                 color=GREY_DARK, ha="center")
        if i < n - 1:
            fig.text(x + box_w + gap / 2, by + 0.030, "→", fontsize=20,
                     color=ACCENT, ha="center", va="center")

    _takeaway_box(fig, "No fabricated number. Every cell traceable to a sha256-anchored TSV in an immutable run dir.")
    fig.savefig(out)
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--output", required=True, type=Path,
                   help="Output directory for PNG slides")
    p.add_argument("--figures-base", type=Path,
                   default=Path("reports/figures"),
                   help="Base path for source figures (m0prime_*.png)")
    args = p.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    figstyle.apply(preset="paper")

    base = args.figures_base

    slide_01_summary(args.output / "01_executive_summary.png")
    slide_02_method(args.output / "02_methodology.png")
    slide_02b_what_we_fixed(args.output / "02b_what_we_fixed_arm_c_to_d_v4.png")
    slide_with_figure(
        args.output / "03_minflt_winner.png",
        "D-v4 leads B by 1 pp on Δminflt under sampler-ON parity",
        "Gardner-Altman estimation · 95 % CI bars · ▼ mean Δ · CIs do not overlap zero",
        base / "m0prime_estimation_minflt_n2.png",
        "D-v4 nudges ahead of B (−78.2 % vs −77.3 %); both clearly beat A. Paired bootstrap N=2 seed=42 — the 1 pp gap is real but small.",
    )
    slide_with_figure(
        args.output / "04_rss_growth.png",
        "D-v4 grows ~6 pp less RSS than B during the bag — a clearer hybrid edge",
        "ΔRSS post-pre · sampler-ON apples-to-apples · per-rep scatter + bootstrap Δ vs A",
        base / "m0prime_estimation_rss_delta_n2.png",
        "Per-thread O1heap pool absorbs allocations without escalating to mmap-grow as often as the global stockpile pool — visible in ΔRSS.",
    )
    slide_with_figure(
        args.output / "05_rss_pre_tradeoff.png",
        "Stockpile wins the rss_pre axis decisively — hybrid pays a +50 % architectural tax",
        "rss_pre = pre-bag steady-state RSS · per-thread O1heap pool 4 MiB × ~89 threads (audit B9 / N4)",
        base / "m0prime_estimation_rss_pre_n2.png",
        "Hybrid's rss_pre cost is a deliberate trade-off, not a regression. Pool-size sweep (audit_v2 G2) is the lever to reduce it without changing allocator semantics.",
    )
    slide_06_reproducibility(args.output / "06_d_v4_reproducibility.png")
    slide_07_sampler_flip(args.output / "07_sampler_dependent_ranking.png")
    slide_08_not_proven(args.output / "08_what_we_did_not_prove.png")
    slide_09_recommendation(args.output / "09_schedule_v5_next_steps.png")
    slide_10_audit(args.output / "10_audit_chain.png")

    sys.stderr.write(f"wrote 10 slides to {args.output}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
