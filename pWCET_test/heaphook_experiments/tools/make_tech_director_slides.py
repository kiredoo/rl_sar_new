#!/usr/bin/env python3
"""Render zh-TW tech-director slide deck for the M0' POC + engineer supplement.

Audience separation:
  - tech-director deck (12 slides): no F1-F4 / G1 jargon, talks only
    about "D" as the proposed allocator; explains arms A/B/C/D from
    a product-decision angle; KEY vs secondary metric layering; each
    chart has 「怎麼看」 + 「insight」 annotation.
  - engineer supplement (4 slides): F1-F4 fix breakdown, sampler-
    perturbation allocator-specific finding, audit chain, schedule v5.

Output:
  reports/figures/slides_m0prime/for_tech_director/   (zh-TW)
  reports/figures/slides_m0prime/for_engineer_supplement/   (zh-TW)
"""
from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

sys.path.insert(0, str(Path(__file__).parent))
import figstyle  # noqa: F401  (sets up shared style)


# CJK font fallback so 中文 actually renders.
matplotlib.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "DejaVu Sans"]
matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["axes.unicode_minus"] = False

SLIDE_W, SLIDE_H = 16, 9
NAVY = "#1F2A44"
ACCENT = "#0B7AB8"
GREEN = "#2C9F4F"
RED = "#CC3311"
ORANGE = "#E67E00"
GREY_LIGHT = "#E5E7EA"
GREY_DARK = "#5A5F66"


def _slide(title: str, subtitle: str = "", footer_left: str = "", footer_right: str = ""):
    fig = plt.figure(figsize=(SLIDE_W, SLIDE_H), dpi=120)
    fig.patch.set_facecolor("white")

    fig.text(0.04, 0.94, title, fontsize=23, fontweight="bold", color=NAVY, va="center")
    if subtitle:
        fig.text(0.04, 0.89, subtitle, fontsize=13, color=GREY_DARK, va="center")
    fig.add_artist(plt.Line2D([0.04, 0.96], [0.86, 0.86],
                              color=ACCENT, linewidth=3, transform=fig.transFigure))

    if footer_left:
        fig.text(0.04, 0.04, footer_left, fontsize=9, color=GREY_DARK)
    if footer_right:
        fig.text(0.96, 0.04, footer_right, fontsize=9, color=GREY_DARK, ha="right")

    return fig


def _takeaway(fig, text: str, y: float = 0.135, label: str = "重點"):
    bbox = FancyBboxPatch(
        (0.04, y - 0.025), 0.92, 0.06,
        boxstyle="round,pad=0.005,rounding_size=0.005",
        linewidth=0, facecolor=GREY_LIGHT, transform=fig.transFigure
    )
    fig.patches.append(bbox)
    fig.text(0.06, y + 0.005, label, fontsize=11, fontweight="bold",
             color=NAVY, va="center")
    fig.text(0.13, y + 0.005, text, fontsize=12.5, color=NAVY, va="center")


def _wrap(text: str, width: int) -> str:
    return "\n".join(textwrap.wrap(text, width=width))


# ============================================================================
# TECH DIRECTOR DECK (zh-TW, 12 slides)
# ============================================================================

FOOT_L = "AGA Gen2 L0 Evidence Plane · POC 收尾報告 · 2026-04-30"
FOOT_R = "技術主管簡報 (zh-TW) · heaphook_experiments"


def td_01_cover(out: Path):
    fig = _slide("",
                 "",
                 footer_left=FOOT_L, footer_right=FOOT_R)
    fig.text(0.5, 0.72, "Autoware 記憶體分配器 POC 結論報告",
             fontsize=34, fontweight="bold", color=NAVY,
             ha="center", va="center")
    fig.text(0.5, 0.63, "「D」= 我們的提案：替代 glibc / stockpile 的 hybrid allocator",
             fontsize=18, color=ACCENT, ha="center", va="center", fontweight="bold")
    fig.text(0.5, 0.57, "thread-local O1heap fast path + 全域 TLSF fallback；目標：bounded WCET",
             fontsize=14, color=GREY_DARK, ha="center", va="center")
    fig.text(0.5, 0.51, "本次 POC = 2026-04-30 階段性結論（M0' N=2 × 3 arm）",
             fontsize=14, color=GREY_DARK, ha="center", va="center", fontstyle="italic")

    # Agenda
    bbox = FancyBboxPatch((0.15, 0.16), 0.70, 0.30,
                          boxstyle="round,pad=0.005,rounding_size=0.012",
                          linewidth=2, edgecolor=ACCENT, facecolor="white",
                          transform=fig.transFigure)
    fig.patches.append(bbox)
    fig.text(0.5, 0.42, "Agenda（10 頁，~10 min）", fontsize=14,
             fontweight="bold", color=ACCENT, ha="center")
    agenda = [
        "1. 結論 hero 卡（3 個 KPI 數字一眼看懂）",
        "2. D 是什麼 + 4-arm 實驗設計",
        "3-4. 衡量標準 + 實際結果",
        "5. 沒驗到的 + 方法論限制",
        "6. ⭐ 終極 KPI：critical-path CV<0.15（CARET）",
        "7-8. 鄰近量測 + 長期架構（Heijunka）",
        "9-10. Schedule + Appendix",
    ]
    for i, line in enumerate(agenda):
        fig.text(0.18, 0.39 - i * 0.030, line, fontsize=11, color=NAVY)
    fig.savefig(out)
    plt.close(fig)


def td_v2_02_hero_summary(out: Path):
    """Hero summary slide — 3 big KPI cards + 1-line conclusion."""
    fig = _slide("3 個 KPI 一眼看懂 — D 在資源層微勝、終極 KPI 待量",
                 "M0' N=2 × 3 arm · sampler-ON · protocol-3stage · paired bootstrap 95 % CI 不含 0",
                 FOOT_L, FOOT_R)

    kpis = [
        ("Δminflt vs A", "−78.2 %", "(D-v4 微勝 B 1pp)",
         "page fault 大幅下降；D 與 B 對 A 都 −77~78 %",
         "✅ 量到", GREEN),
        ("ΔRSS vs A",    "−28.6 %", "(D-v4 領先 B 6pp)",
         "30 s bag 期間 RSS 成長量；D 比 B 更省",
         "✅ 量到", GREEN),
        ("rss_pre vs A", "+49.6 %", "(架構成本)",
         "D 啟動時預配 ~7 GiB（per-thread O1heap pool）",
         "⚠ 設計取捨", ORANGE),
    ]
    n = len(kpis)
    margin_x = 0.04
    box_w = (1 - 2 * margin_x - 0.04 * (n - 1)) / n
    gap = 0.04
    y0 = 0.43
    box_h = 0.36
    for i, (label, big, sub, foot, status, color) in enumerate(kpis):
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
        fig.text(x0 + box_w / 2, y0 + box_h * 0.62, big, fontsize=46,
                 color=color, ha="center", va="center", fontweight="bold")
        fig.text(x0 + box_w / 2, y0 + box_h * 0.40, sub, fontsize=11,
                 color=NAVY, ha="center", va="center")
        fig.text(x0 + box_w / 2, y0 + 0.06, _wrap(foot, 22), fontsize=10,
                 color=NAVY, ha="center", va="bottom")
        fig.text(x0 + box_w / 2, y0 + 0.018, status, fontsize=11,
                 color=color, ha="center", va="bottom", fontweight="bold")

    # Reproducibility callout
    cy = 0.30
    bbox_r = FancyBboxPatch((0.06, cy - 0.04), 0.88, 0.06,
                            boxstyle="round,pad=0.005,rounding_size=0.012",
                            linewidth=2, edgecolor=GREEN, facecolor="white",
                            transform=fig.transFigure)
    fig.patches.append(bbox_r)
    fig.text(0.08, cy + 0.005, "Reproducibility 訊號",
             fontsize=12, fontweight="bold", color=GREEN, va="center")
    fig.text(0.30, cy + 0.005,
             "D-v4 rep1↔rep2 變異 = **0.01 %**　／　B = 4.0 %　／　A glibc = 8.8 %"
             "　— D 比 A 緊 3 個數量級",
             fontsize=12, color=NAVY, va="center")

    # 1-line conclusion
    fig.text(0.5, 0.215,
             "資源層：D 微勝；架構成本（rss_pre +50 %）為設計取捨；",
             fontsize=14, color=NAVY, ha="center", fontweight="bold")
    fig.text(0.5, 0.185,
             "**終極 KPI（端到端 CV < 0.15）尚未量** → Session 10 才能定論。",
             fontsize=14, color=ORANGE, ha="center", fontweight="bold")

    _takeaway(fig, "如果你只看一頁，看這頁。資源層 D 已驗有效；最終定論等 Layer 2 量到才能講。")
    fig.savefig(out)
    plt.close(fig)


def td_02_problem(out: Path):
    fig = _slide("我們解決什麼問題 — Autoware 記憶體行為的「不確定性」",
                 "確定性運算 (deterministic computation) 是自駕系統的核心需求；現況的 allocator 在這一塊有可量化的問題",
                 FOOT_L, FOOT_R)

    # Two columns: 問題 / 為什麼重要
    cols = [
        ("現況觀察", [
            "Autoware 在 component_container_mt 下跑 ~89 個 thread",
            "用 glibc 原生 allocator 時，記憶體使用呈現「不可預測的尖峰」",
            "在重 workload 下偶發 OOM、page fault rate 抖動大",
            "對自駕系統來說，「最差情況」無上限 = 不可接受",
        ], RED),
        ("為什麼是 allocator 的問題", [
            "ROS 各 callback 在 hot path 大量 malloc / free",
            "glibc malloc 在多 thread 競爭下會走 arena lock — 延遲跳",
            "既有研究：替換 allocator 能直接降低延遲變異",
            "TIER IV / Autoware 已知這條路；hybrid 設計就是針對這個情境",
        ], NAVY),
    ]
    n = len(cols)
    margin = 0.04
    gap = 0.04
    box_w = (1 - 2 * margin - gap) / n
    y0 = 0.24
    box_h = 0.55

    for i, (title, items, color) in enumerate(cols):
        x0 = margin + i * (box_w + gap)
        bbox = FancyBboxPatch((x0, y0), box_w, box_h,
                              boxstyle="round,pad=0.005,rounding_size=0.012",
                              linewidth=2, edgecolor=color, facecolor="white",
                              transform=fig.transFigure)
        fig.patches.append(bbox)
        fig.text(x0 + 0.015, y0 + box_h - 0.04, title,
                 fontsize=15, fontweight="bold", color=color, va="top")
        for j, line in enumerate(items):
            wrapped = _wrap(line, 30)
            fig.text(x0 + 0.015, y0 + box_h - 0.10 - j * 0.10,
                     "• " + wrapped, fontsize=12, color=NAVY, va="top")

    _takeaway(fig, "目標：找一個 allocator，讓 Autoware 的記憶體行為從「不可預測」變成「可保證上限」。")
    fig.savefig(out)
    plt.close(fig)


def td_03_d_is(out: Path):
    fig = _slide("我們的提案 — D allocator：per-thread 小池 + 全域 fallback",
                 "用「每個 thread 自己的快路徑」迴避 arena lock；只有溢出才走較慢的 fallback",
                 FOOT_L, FOOT_R)

    # Diagram: thread → per-thread pool → fallback
    # Use simple boxes
    cy = 0.52
    fig.text(0.07, cy + 0.20, "設計原則", fontsize=14, fontweight="bold", color=NAVY)
    bullets = [
        "每個 thread 配一塊 4 MiB 的私有 pool（fast path）",
        "malloc 大部分情況直接從自己 pool 切 — O(1) 時間，無鎖競爭",
        "pool 裝不下或太大塊 → fallback 到全域 TLSF 池（仍 bounded）",
        "free 時把 pointer 放回原 thread 的 pool 由原 thread 回收（thread-safe）",
    ]
    for i, b in enumerate(bullets):
        fig.text(0.08, cy + 0.13 - i * 0.045, "• " + b,
                 fontsize=12, color=NAVY)

    # Comparison table
    rows = [
        ("Thread 數量",        "1 個全域 arena", "89 個獨立 pool"),
        ("malloc 走哪",        "全 thread 競爭一個鎖",  "自己 pool，無鎖"),
        ("最差情況延遲",        "理論無上限（鎖等待）",   "有上限（per-thread 鎖內 O(1)）"),
        ("代價",              "啟動快、記憶體小",      "啟動時就吃 ~89 × 4 MiB"),
    ]
    tx = 0.55
    ty = cy + 0.22
    fig.text(tx, ty, "對照 glibc malloc",
             fontsize=14, fontweight="bold", color=NAVY)

    col_widths = [0.13, 0.13, 0.13]
    headers = ["", "glibc 現況", "D 提案"]
    cx = tx
    fig.text(cx, ty - 0.06, headers[0], fontsize=11, color=GREY_DARK)
    fig.text(cx + col_widths[0], ty - 0.06, headers[1], fontsize=11,
             fontweight="bold", color=GREY_DARK)
    fig.text(cx + col_widths[0] + col_widths[1], ty - 0.06, headers[2],
             fontsize=11, fontweight="bold", color=ACCENT)
    fig.add_artist(plt.Line2D([tx, tx + sum(col_widths)],
                              [ty - 0.075, ty - 0.075],
                              color=NAVY, linewidth=1.5, transform=fig.transFigure))
    for i, row in enumerate(rows):
        ry = ty - 0.10 - i * 0.045
        for j, cell in enumerate(row):
            color = NAVY if j != 2 else ACCENT
            fontw = "bold" if j == 0 else "normal"
            fig.text(tx + sum(col_widths[:j]), ry, cell,
                     fontsize=10.5, color=color, fontweight=fontw, va="center")

    _takeaway(fig, "技術主管理解角度 — D 的賣點是「最差情況有上限」，代價是「啟動多吃 ~360 MB 記憶體」。後者是已知的設計取捨。")
    fig.savefig(out)
    plt.close(fig)


def td_04_arms(out: Path):
    fig = _slide("為什麼 4 個對照組 A/B/C/D — 隔離設計效應 vs 實作 bug",
                 "差一個變因看一個效應的對照實驗設計",
                 FOOT_L, FOOT_R)

    arms = [
        ("A", "現況 baseline", "glibc 原生 malloc",
         "業界 default；「不換 allocator」的對照",
         "做為「目前 Autoware 跑出來的數字」基準",
         GREY_DARK),
        ("B", "另一種既有解",  "TIER IV 之前用過的 stockpile allocator",
         "比 glibc 簡單、純池式管理",
         "確認「換 allocator 真的有差」、設定 D 要打贏的對手",
         ACCENT),
        ("C", "D 的設計 + 已知 bug 版本", "（沒修 bug 前的 D）",
         "驗證 bug 修了之後跑得起來",
         "**沒有產品意義**，只做 fix 確認；對技術主管不重要",
         RED),
        ("D", "我們的提案",     "D 的設計 + bug 修好後的版本",
         "本次 POC 的主角",
         "對 A 和 B 的比較結果，就是這份報告的結論",
         GREEN),
    ]

    n = len(arms)
    margin = 0.04
    gap = 0.02
    box_w = (1 - 2 * margin - (n - 1) * gap) / n
    y0 = 0.18
    box_h = 0.62

    for i, (id_, role, what, char, why, color) in enumerate(arms):
        x0 = margin + i * (box_w + gap)
        bbox = FancyBboxPatch((x0, y0), box_w, box_h,
                              boxstyle="round,pad=0.005,rounding_size=0.012",
                              linewidth=2.5, edgecolor=color, facecolor="white",
                              transform=fig.transFigure)
        fig.patches.append(bbox)
        # Big arm letter
        fig.text(x0 + box_w / 2, y0 + box_h - 0.06, id_,
                 fontsize=44, fontweight="bold", color=color,
                 ha="center", va="center")
        fig.text(x0 + box_w / 2, y0 + box_h - 0.13, role,
                 fontsize=12, color=NAVY, ha="center", va="center",
                 fontweight="bold")
        fig.text(x0 + 0.012, y0 + box_h - 0.20, "是什麼", fontsize=9.5,
                 color=GREY_DARK, fontweight="bold")
        fig.text(x0 + 0.012, y0 + box_h - 0.225, _wrap(what, 14),
                 fontsize=10, color=NAVY, va="top")
        fig.text(x0 + 0.012, y0 + box_h - 0.32, "特性", fontsize=9.5,
                 color=GREY_DARK, fontweight="bold")
        fig.text(x0 + 0.012, y0 + box_h - 0.345, _wrap(char, 14),
                 fontsize=10, color=NAVY, va="top")
        fig.text(x0 + 0.012, y0 + box_h - 0.43, "為什麼有它", fontsize=9.5,
                 color=GREY_DARK, fontweight="bold")
        fig.text(x0 + 0.012, y0 + box_h - 0.455, _wrap(why, 14),
                 fontsize=10, color=NAVY, va="top")

    _takeaway(fig, "技術主管要看的是 D 對 A、D 對 B 的比較。C 是工程過程的中間態，不是產品候選。")
    fig.savefig(out)
    plt.close(fig)


def td_05_key_metrics(out: Path):
    fig = _slide("KEY metrics — 4 個指標決定 D 是否成功",
                 "其中 2 個本次量到了、2 個尚未量到（下階段）",
                 FOOT_L, FOOT_R)

    rows = [
        ("✅", "Δminflt（minor page fault 次數）",
         "30s bag 內，所有 Autoware procs 累積的 minor fault 增量",
         "間接反映 allocator 走 mmap-grow / 觸發 page-table 工作的頻率；越低越好",
         "本次量到", GREEN),
        ("✅", "ΔRSS（resident memory growth）",
         "30s bag 內，所有 Autoware procs RSS 增加量",
         "反映 allocator 從 OS 多要了多少記憶體；越低代表 reuse 效率越好",
         "本次量到", GREEN),
        ("⏳", "端到端 callback / chain 延遲抖動 (CARET)",
         "從感知 → 規劃 → 控制 chain 的 e2e 延遲 p99 - p50 變動",
         "**真產品 KPI** — 這個指標才能說「確定性運算」改善",
         "下階段量", ORANGE),
        ("⏳", "單次 malloc 延遲 tail (bcc / bpftrace)",
         "每次 malloc/free 從進入到回傳的奈秒分佈 p99 / p99.9",
         "Layer 1 證據 — bounded WCET claim 的必要前提",
         "下階段量", ORANGE),
    ]

    fig.text(0.04, 0.79, "✅ = 本次 POC 已量；⏳ = 下階段才量",
             fontsize=11, color=GREY_DARK)

    y0 = 0.20
    row_h = 0.13
    for i, (mark, name, what, why, status, color) in enumerate(rows):
        ry = 0.78 - 0.05 - i * row_h
        # Status badge
        bid = FancyBboxPatch((0.045, ry - 0.045), 0.05, 0.05,
                             boxstyle="round,pad=0.003,rounding_size=0.006",
                             linewidth=0, facecolor=color,
                             transform=fig.transFigure)
        fig.patches.append(bid)
        fig.text(0.07, ry - 0.020, mark, fontsize=20, color="white",
                 ha="center", va="center", fontweight="bold")

        fig.text(0.11, ry - 0.005, name, fontsize=14,
                 fontweight="bold", color=NAVY)
        fig.text(0.11, ry - 0.035, "● " + what, fontsize=10.5, color=NAVY)
        fig.text(0.11, ry - 0.055, "● " + why, fontsize=10.5, color=GREY_DARK)
        fig.text(0.92, ry - 0.005, status, fontsize=11, color=color,
                 fontweight="bold", ha="right")

    _takeaway(fig, "本次 POC 看的是「資源使用」(Δminflt + ΔRSS)；「延遲」這兩個 KPI 是下階段才能講。")
    fig.savefig(out)
    plt.close(fig)


def td_06_secondary_metrics(out: Path):
    fig = _slide("次要 metrics — 補充佐證 / caveat 用",
                 "不是判斷 D 成不成功的決定指標，但讀報告會看到，先說明",
                 FOOT_L, FOOT_R)

    rows = [
        ("rss_pre", "啟動穩態的記憶體（bag 還沒跑前）",
         "D 的 +50 % rss_pre 是設計取捨（per-thread pool），不是 bug",
         "trade-off"),
        ("aborts / OOM 數",          "30s 內的失敗事件",
         "D 應該跟 A 一樣 ≤ 4 aborts；C 88 aborts 是 fix 前的對照",
         "已過關"),
        ("nprocs",                  "捕捉到的 Autoware proc 數",
         "理論 89；偶發 90 是 Autoware launch race，跟 allocator 無關",
         "環境噪音"),
        ("PSI memory pressure",      "OS 整機記憶體壓力指標",
         "本機 78 GB RAM 用 13-21 GB → PSI=0 正常，不是「沒量到」",
         "本機都 0"),
        ("PSS / USS",               "去掉共享記憶體重複計算後的真實佔用",
         "比 RSS 更精準，但 Δ trend 跟 RSS 一致；輔助指標",
         "輔助"),
        ("cgroup memory.events",    "kernel 級 OOM-kill / 限流事件",
         "本機 cgroup v2 memory controller 沒掛 → 全空，跨機要重量",
         "本機無資料"),
        ("frag_ratio (allocator-internal)", "1 − allocated/capacity",
         "D 的 fragmentation 指標；Phase 2.5b 才量",
         "下階段"),
        ("alloc latency histogram", "單次 malloc 微秒分佈",
         "已歸入 KEY metrics 第 4 項（下階段量）",
         "下階段"),
    ]

    fig.text(0.04, 0.79, "本次量到 5 個次要指標 + 3 個下階段才量",
             fontsize=11, color=GREY_DARK)

    cols = [t["en"] if isinstance(t, dict) else t for t in
            ["指標", "是什麼", "本次說了什麼", "狀態"]]
    col_widths = [0.20, 0.27, 0.36, 0.10]

    cx = 0.04
    cy = 0.71
    for j, c in enumerate(cols):
        fig.text(cx + sum(col_widths[:j]) + 0.01, cy, c,
                 fontsize=11, fontweight="bold", color=NAVY)
    fig.add_artist(plt.Line2D([cx, cx + sum(col_widths)],
                              [cy - 0.012, cy - 0.012],
                              color=NAVY, linewidth=1.5, transform=fig.transFigure))

    for i, row in enumerate(rows):
        ry = cy - 0.04 - i * 0.06
        if i % 2 == 0:
            bg = FancyBboxPatch((cx, ry - 0.022), sum(col_widths), 0.052,
                                boxstyle="round,pad=0,rounding_size=0",
                                linewidth=0, facecolor=GREY_LIGHT,
                                transform=fig.transFigure)
            fig.patches.append(bg)
        for j, v in enumerate(row):
            fontw = "bold" if j == 0 else "normal"
            color = NAVY if j != 3 else ACCENT
            wrapped = _wrap(v, max(8, int(col_widths[j] * 60)))
            fig.text(cx + sum(col_widths[:j]) + 0.01, ry,
                     wrapped, fontsize=10, color=color,
                     fontweight=fontw, va="center")

    _takeaway(fig, "次要 metrics 在報告裡會看到，但「D 對 A、D 對 B 誰好誰壞」是看 KEY metrics 決定。")
    fig.savefig(out)
    plt.close(fig)


def td_06b_metrics_glossary(out: Path):
    fig = _slide("Metrics 一覽表 — 所有指標的「定義 + 單位 + 角色」",
                 "閱讀後續結果頁前先看這張，避免單位混淆",
                 FOOT_L, FOOT_R)

    rows = [
        ("KEY", "Δminflt",                    "次（count）",                         "30 s bag 期間 minor page fault 累積增量",                "本次量到", GREEN),
        ("KEY", "ΔRSS",                       "KiB（同時換算 MiB）",                   "30 s bag 期間 RSS 成長量；越低代表 reuse 效率高",           "本次量到", GREEN),
        ("KEY", "e2e callback 延遲抖動",       "微秒 µs (p99 − p50)",                 "感知 → 規劃 → 控制 chain 端到端延遲變動 (CARET)；產品 KPI", "下階段量",  ORANGE),
        ("KEY", "單次 malloc 延遲 tail",       "奈秒 ns (p99 / p99.9)",                "每次 malloc 從進入到回傳；bounded WCET 必要前提",            "下階段量",  ORANGE),
        ("次要", "rss_pre",                   "KiB（MiB）",                           "bag 還沒跑前的 steady-state RSS",                          "本次量到", ACCENT),
        ("次要", "aborts",                    "次（count）",                          "30 s 內 SIGABRT / pre-SIGINT crash 數",                     "本次量到", ACCENT),
        ("次要", "grep OOM",                  "次（count）",                          "log 中「Cannot allocate memory」字串出現次數",              "本次量到", ACCENT),
        ("次要", "nprocs",                    "個（count）",                          "pgrep 捕捉到的 Autoware procs 數量；理論 89",                "本次量到", ACCENT),
        ("次要", "PSI memory pressure",       "% 比例 / µs 累計",                      "kernel 報告的整機記憶體壓力；本機都 0",                      "本次量到", ACCENT),
        ("次要", "PSS / USS aggregate",        "KiB（MiB）",                           "smaps_rollup 統計的真實記憶體（去重複計算）",                "本次量到", ACCENT),
        ("次要", "cgroup memory.events",       "次（count）",                          "cgroup-level OOM-kill / 限流事件",                          "本次無資料", ACCENT),
        ("次要", "frag_ratio",                "比例 (0-1)",                            "1 − allocated/capacity；越接近 0 越完整使用",               "下階段量",  ORANGE),
    ]

    cols = ["分類", "metric", "單位", "是什麼", "本次狀態"]
    col_widths = [0.07, 0.20, 0.16, 0.39, 0.10]

    cx = 0.04
    cy = 0.78
    for j, c in enumerate(cols):
        fig.text(cx + sum(col_widths[:j]) + 0.005, cy, c,
                 fontsize=11.5, fontweight="bold", color=NAVY)
    fig.add_artist(plt.Line2D([cx, cx + sum(col_widths)],
                              [cy - 0.012, cy - 0.012],
                              color=NAVY, linewidth=1.5, transform=fig.transFigure))

    for i, row in enumerate(rows):
        ry = cy - 0.04 - i * 0.0455
        if i % 2 == 0:
            bg = FancyBboxPatch((cx, ry - 0.018), sum(col_widths), 0.040,
                                boxstyle="round,pad=0,rounding_size=0",
                                linewidth=0, facecolor=GREY_LIGHT,
                                transform=fig.transFigure)
            fig.patches.append(bg)
        cat_color = GREEN if row[0] == "KEY" else GREY_DARK
        # Cat badge
        fig.text(cx + 0.005, ry, row[0], fontsize=10,
                 fontweight="bold", color=cat_color, va="center")
        fig.text(cx + col_widths[0] + 0.005, ry, row[1],
                 fontsize=10, fontweight="bold", color=NAVY, va="center")
        fig.text(cx + sum(col_widths[:2]) + 0.005, ry, row[2],
                 fontsize=10, color=ACCENT, va="center")
        fig.text(cx + sum(col_widths[:3]) + 0.005, ry, _wrap(row[3], 36),
                 fontsize=10, color=NAVY, va="center")
        fig.text(cx + sum(col_widths[:4]) + 0.005, ry, row[4],
                 fontsize=10, color=row[5], fontweight="bold", va="center")

    _takeaway(fig, "「KEY 4 個」決定 D 是否成功；其餘是佐證。本次只量到 4 個 KEY 中的 2 個（資源類）；延遲類兩個下階段才有。")
    fig.savefig(out)
    plt.close(fig)


def td_07_results_minflt(out: Path, fig_path: Path):
    fig = _slide("KEY 1 — Δminflt：D 比 A 少 78 %、比 B 多領先 1pp",
                 "在 production-like 量測下（含 Tier 0 sampler、有 NDT/EKF 暖機）",
                 FOOT_L, FOOT_R)

    # Embed figure on left half
    if fig_path.exists():
        img = mpimg.imread(fig_path)
        img_ax = fig.add_axes([0.04, 0.20, 0.52, 0.62])
        img_ax.imshow(img)
        img_ax.axis("off")

    # Right half: how to read + insight
    rx = 0.58
    fig.text(rx, 0.78, "怎麼看這張圖",
             fontsize=14, fontweight="bold", color=ACCENT)
    how_lines = [
        "• 上半：每個 arm 兩個圓點 = 兩次重複實驗（rep1 / rep2）",
        "• 中間虛線 = 該 arm 的平均",
        "• 下半：bootstrap 重抽樣分佈 — 把「rep 兩個值」隨機抽 10000 次算 Δ",
        "• 兩條短線 = 95 % 信賴區間；▼ = Δ 平均",
        "• 0 線（黑虛線）= 「跟 A 一樣」；CI 不含 0 表示差距是真實的",
    ]
    for i, line in enumerate(how_lines):
        fig.text(rx, 0.74 - i * 0.035, _wrap(line, 50),
                 fontsize=11, color=NAVY)

    fig.text(rx, 0.51, "Insight",
             fontsize=14, fontweight="bold", color=GREEN)
    insights = [
        "• B 跟 D 都比 A 少 ~77-78 % page faults，差距很大且 CI 不重疊 0",
        "• D 比 B 還少 1 個 pp（241 萬 vs 256 萬），在 sampler-ON 下 D 微贏",
        "• D 的兩個 rep 完全重疊 — 變異 0.01 %（reproducibility 強）",
        "• 但這是 sampler-ON 比較；sampler-OFF 反而 B 贏 4 pp（後面 caveat）",
    ]
    for i, line in enumerate(insights):
        fig.text(rx, 0.47 - i * 0.04, _wrap(line, 50),
                 fontsize=11, color=NAVY)

    _takeaway(fig, "在 production-like 條件下 D 微幅領先；但 ranking 對 sampler 模式敏感（後續會說明）。")
    fig.savefig(out)
    plt.close(fig)


def td_08_results_rss(out: Path, fig_path: Path):
    fig = _slide("KEY 2 — ΔRSS：D 比 A 少漲 29 %、比 B 多領先 6pp",
                 "30 s bag 期間記憶體成長量",
                 FOOT_L, FOOT_R)

    if fig_path.exists():
        img = mpimg.imread(fig_path)
        img_ax = fig.add_axes([0.04, 0.20, 0.52, 0.62])
        img_ax.imshow(img)
        img_ax.axis("off")

    rx = 0.58
    fig.text(rx, 0.78, "怎麼看這張圖",
             fontsize=14, fontweight="bold", color=ACCENT)
    how_lines = [
        "• 同樣的 estimation plot 結構（上半 per-rep + 下半 bootstrap Δ）",
        "• y 軸單位是 KiB；A 漲 ~1,389,000 KiB ≈ 1.4 GiB",
        "• B 漲 1,073 MiB；D 漲 968 MiB",
    ]
    for i, line in enumerate(how_lines):
        fig.text(rx, 0.74 - i * 0.035, _wrap(line, 50),
                 fontsize=11, color=NAVY)

    fig.text(rx, 0.61, "Insight",
             fontsize=14, fontweight="bold", color=GREEN)
    insights = [
        "• D 是三 arm 中 RSS 漲最少的 — 比 B 還少 ~80 MiB（6 pp）",
        "• 解讀：D 的 per-thread pool 內部 reuse 效率 > B 的全域池",
        "• 與 Δminflt 同向 — D 的 allocator 走 OS 拿新 page 的頻率較低",
        "• D 變異 0.2 %、B 4.3 %、A 2.1 % — 又是 D 最 reproducible",
    ]
    for i, line in enumerate(insights):
        fig.text(rx, 0.57 - i * 0.04, _wrap(line, 50),
                 fontsize=11, color=NAVY)

    _takeaway(fig, "ΔRSS 結果與 Δminflt 一致 — D 在動態記憶體效率上有優勢。")
    fig.savefig(out)
    plt.close(fig)


def td_09_results_rss_pre(out: Path, fig_path: Path):
    fig = _slide("反向 — rss_pre：D 比 A 多吃 50 %、B 反而最瘦",
                 "啟動穩態記憶體；這是 D 設計的已知代價，不是缺陷",
                 FOOT_L, FOOT_R)

    if fig_path.exists():
        img = mpimg.imread(fig_path)
        img_ax = fig.add_axes([0.04, 0.20, 0.52, 0.62])
        img_ax.imshow(img)
        img_ax.axis("off")

    rx = 0.58
    fig.text(rx, 0.78, "怎麼看這張圖",
             fontsize=14, fontweight="bold", color=ACCENT)
    how_lines = [
        "• A 啟動 ~13.9 GiB；B 啟動 ~12.8 GiB；D 啟動 ~20.8 GiB",
        "• D 比 A 多 ~6.9 GiB ≈ 89 thread × ~80 MiB 平均（包含其他結構）",
        "• B 比 A 還少 ~1.1 GiB — stockpile 簡化結構，記憶體最省",
    ]
    for i, line in enumerate(how_lines):
        fig.text(rx, 0.74 - i * 0.035, _wrap(line, 50),
                 fontsize=11, color=NAVY)

    fig.text(rx, 0.61, "Insight",
             fontsize=14, fontweight="bold", color=ORANGE)
    insights = [
        "• D 多吃的 ~7 GiB 是預先配置的 per-thread pool（4 MiB × 89）+ 其他結構",
        "• 這是 D 設計的「換空間取低延遲」trade-off — 設計就這樣",
        "• 未來可調 pool size（目前是預設 4 MiB），若 8 GB RAM 環境會吃緊",
        "• 對車載運算單元（>32 GB）：可接受；對嵌入式（<8 GB）：要評估",
    ]
    for i, line in enumerate(insights):
        fig.text(rx, 0.57 - i * 0.04, _wrap(line, 50),
                 fontsize=11, color=NAVY)

    _takeaway(fig, "rss_pre 是 D 設計的可預期代價；技術主管要評估的是「目標平台 RAM 是否充裕」。")
    fig.savefig(out)
    plt.close(fig)


def td_10_repro(out: Path):
    fig = _slide("D 的可重現性高出 3 個數量級 — 行為穩定的訊號",
                 "rep1 / rep2 重跑同一 binary、同 host、同 bag",
                 FOOT_L, FOOT_R)

    arms = [("A glibc",   1080142, 1175011, "8.8 %",  RED),
            ("B 既有解",  261371,  251078, "4.0 %",  ACCENT),
            ("D 提案",    245351,  245315, "0.01 %", GREEN)]

    n = len(arms)
    box_w = 0.27
    gap = 0.038
    margin_x = (1 - n * box_w - (n - 1) * gap) / 2
    y0 = 0.30
    box_h = 0.45

    for i, (label, r1, r2, var, color) in enumerate(arms):
        x0 = margin_x + i * (box_w + gap)
        bbox = FancyBboxPatch((x0, y0), box_w, box_h,
                              boxstyle="round,pad=0.005,rounding_size=0.012",
                              linewidth=2, edgecolor=color, facecolor="white",
                              transform=fig.transFigure)
        fig.patches.append(bbox)
        fig.text(x0 + box_w / 2, y0 + box_h - 0.045, label, fontsize=15,
                 color=NAVY, ha="center", fontweight="bold")
        cx = x0 + box_w / 2
        rep_y = y0 + 0.30
        fig.text(cx, rep_y + 0.03, "rep1", fontsize=10, color=GREY_DARK, ha="center")
        fig.text(cx, rep_y, f"{r1:,}", fontsize=18, color=NAVY, ha="center", fontweight="bold")
        fig.text(cx, rep_y - 0.04, "rep2", fontsize=10, color=GREY_DARK, ha="center")
        fig.text(cx, rep_y - 0.07, f"{r2:,}", fontsize=18, color=NAVY, ha="center", fontweight="bold")
        fig.text(cx, y0 + 0.04, var, fontsize=30, color=color, ha="center",
                 fontweight="bold")
        fig.text(cx, y0 + 0.012, "rep1↔rep2 變異", fontsize=9,
                 color=GREY_DARK, ha="center")

    fig.text(0.5, 0.24, "怎麼看這張圖", fontsize=13, fontweight="bold", color=ACCENT, ha="center")
    fig.text(0.5, 0.21,
             "• 同一個 binary、同一台機器、同一個 30s bag 跑兩次；數字差多少 = 量測噪音 + allocator 自身決定論",
             fontsize=11, color=NAVY, ha="center")
    fig.text(0.5, 0.185,
             "• D 兩次相差 36 (差 0.01 %)；A 兩次相差 95 k (差 8.8 %)",
             fontsize=11, color=NAVY, ha="center")

    _takeaway(fig, "D 的決定性遠比 glibc 高 — 雖然這還沒驗到延遲層，但已暗示 bounded WCET 的可能性。")
    fig.savefig(out)
    plt.close(fig)


def td_11_not_proven(out: Path):
    fig = _slide("還沒驗到的 — 真正的產品 KPI（端到端延遲抖動）",
                 "Tesla 量測紀律：沒量過的不能 claim；下一階段才能下定論",
                 FOOT_L, FOOT_R)

    cells = [
        ("✅ 本次量到", [
            "D 跟 A 的「資源使用 metric」差距（Δminflt / ΔRSS）",
            "D 的 binary 跑得起來、不再 crash（vs 沒修 bug 的 C）",
            "D 的 reproducibility 數量級優於 glibc (0.01 % vs 8.8 %)",
            "Sampler 干擾對不同 allocator 不同（後續工程細節再講）",
        ], GREEN),
        ("❌ 還沒量 / 下階段做", [
            "**端到端 callback chain 延遲抖動 (CARET)** — 真產品 KPI",
            "**單次 malloc 延遲 tail (bcc / bpftrace)** — 必要前提",
            "長時間 soak（15 分以上）的記憶體洩漏 / 碎片化",
            "Functional behaviour 紀錄（rviz pose / NDT / planning latency）",
            "跨機 reproducibility / 替換 bag / 改變 sample rate",
        ], RED),
    ]

    n = len(cells)
    margin = 0.04
    gap = 0.04
    box_w = (1 - 2 * margin - gap) / n
    y0 = 0.20
    box_h = 0.58

    for i, (header, items, color) in enumerate(cells):
        x0 = margin + i * (box_w + gap)
        bbox = FancyBboxPatch((x0, y0), box_w, box_h,
                              boxstyle="round,pad=0.005,rounding_size=0.012",
                              linewidth=2, edgecolor=color, facecolor="white",
                              transform=fig.transFigure)
        fig.patches.append(bbox)
        fig.text(x0 + box_w / 2, y0 + box_h - 0.045, header, fontsize=16,
                 fontweight="bold", color=color, ha="center")
        for j, line in enumerate(items):
            fig.text(x0 + 0.015, y0 + box_h - 0.10 - j * 0.075,
                     "• " + _wrap(line, 32), fontsize=11.5, color=NAVY,
                     va="top")

    _takeaway(fig, "本階段是「資源使用」打贏；下階段要看「延遲」是否打贏，才能說 D 是 production-ready 的決定。")
    fig.savefig(out)
    plt.close(fig)


def td_11b_methodology_defense(out: Path):
    fig = _slide("方法論可靠性自審 — 我們做對什麼、還缺什麼",
                 "Stanford EECS 嚴審 + Tesla 量測紀律的雙視角；不替自己護航",
                 FOOT_L, FOOT_R)

    cells = [
        ("✓ 做對的（讓結論可信）", [
            "Same-binary / same-host：cross-arm Δ 全在同一 .so + 同一機器；不混 historical mixed sha256",
            "預先註冊 gate（PASS/PARTIAL/FAIL 數字寫死）→ 沒事後 gerrymandering",
            "Paired bootstrap 95 % CI（不只 mean）→ Δ 方向是否穩健直接看 CI 是否含 0",
            "Sampler-OFF + sampler-ON 兩路線交叉驗證 → 抓到 sampler 對不同 allocator 不同的偏誤",
            "證據鏈 sha256 釘錨：env/exp_settings_<arm>.tsv → MANIFEST.md → 報告引用 run_id",
            "Bug audit 兩輪（v1 + v2）+ TDD 紅綠 demo + 新 bug 找出 4 個才修 stats atomicity",
            "Protocol gap 抓到後重跑 6 reps（M0 → M0'），舊 reps 進 superseded/ 留 audit trail",
            "用 user 既有自動化（不重造輪子）— 6 + 10 pause-unpause 對齊 run_n_interrel_tracing_tmux",
        ], GREEN),
        ("✗ 不足的（未來改進）", [
            "**N=2 仍不足 paper-grade** — 想做 effect-size + 95 % CI 嚴 inferential 至少 N=5；bootstrap CI 嚴格要 N=30",
            "**單機 / 單 bag / 單 rate** — cross-host reproducibility / 替 bag / 改變 sample rate 都沒驗",
            "**30 s 短窗** — long-soak (15+ min) 是最有可能找出 leak / fragmentation drift 的場景，本次未跑",
            "**Sampler +11 % (D-v4) 仍邊緣** — 雖在 ±15 % 內但接近上限；理想要降到 < 5 %",
            "**Functional observability 缺** (C13 G-rviz)：rviz 上自車是否走對只能肉眼看；未來要紀錄 NDT iter / pose error",
            "**Bringup readiness check 是 timing heuristic** (C14)：sleep 75 s 不檢查所有 component 真的 ready",
            "**F1 memory-model UB 仍 deferred** — release build 跑得起，但形式上未證明安全；TSan 驗證留待 hygiene round",
            "**cgroup v2 memory controller 本機沒掛** → memory.events 全空；要跨機補 Tier 0 (e)",
            "**bounded-WCET claim 0 evidence**（已在 § 11 ackowledge）→ Layer 2 CARET 是 milestone-closer",
        ], ORANGE),
    ]

    n = len(cells)
    margin = 0.04
    gap = 0.04
    box_w = (1 - 2 * margin - gap) / n
    y0 = 0.18
    box_h = 0.62

    for i, (header, items, color) in enumerate(cells):
        x0 = margin + i * (box_w + gap)
        bbox = FancyBboxPatch((x0, y0), box_w, box_h,
                              boxstyle="round,pad=0.005,rounding_size=0.012",
                              linewidth=2, edgecolor=color, facecolor="white",
                              transform=fig.transFigure)
        fig.patches.append(bbox)
        fig.text(x0 + box_w / 2, y0 + box_h - 0.04, header, fontsize=14,
                 fontweight="bold", color=color, ha="center")
        for j, line in enumerate(items):
            fig.text(x0 + 0.012, y0 + box_h - 0.10 - j * 0.062,
                     "• " + _wrap(line, 32), fontsize=10.5, color=NAVY, va="top")

    _takeaway(fig, "結論的「方向」（D 對 A 有效、D 對 B 微勝）有方法論支撐；「絕對數字 / 跨情境概化」需要下階段補強。")
    fig.savefig(out)
    plt.close(fig)


def td_11c_frag_plan(out: Path):
    fig = _slide("Fragmentation 量測 — 已建半套基礎建設，D-v4 量測排在 Session 12",
                 "Phase 2.5a 已通電（arm A）；2.5b 將擴到 D-v4 + B；2.5c 跨 arm 綜合",
                 FOOT_L, FOOT_R)

    fig.text(0.04, 0.79, "為什麼今天沒在 D-v4 量到 fragmentation",
             fontsize=14, fontweight="bold", color=NAVY)
    why = [
        "Allocator-internal fragmentation 不是 OS 看得到的 metric — 必須由 allocator 自己暴露",
        "glibc 提供 mallinfo2() 介面 → Phase 2.5a 已用 GlibcMallinfo2FragProvider 在 arm A 跑通",
        "D-v4 hybrid 的 O1heap + TLSF 各自有內部統計 (oom_count / capacity / allocated)，但沒有對外介面",
        "audit_v2 找到 hybrid 的 ENABLE_STATS 是「直接綁進 allocator」(D-grade decouple) → 必須先 R2-R5 解耦才能加 FragProvider",
    ]
    for i, line in enumerate(why):
        fig.text(0.05, 0.74 - i * 0.04, "• " + _wrap(line, 75),
                 fontsize=11, color=NAVY)

    fig.text(0.04, 0.55, "Phase 2.5b 規劃（Session 12 跑）",
             fontsize=14, fontweight="bold", color=ACCENT)
    plan = [
        ("量什麼", "frag_ratio = 1 − allocated/capacity；每秒 1 次取樣；分 O1heap 池與 TLSF 池兩條曲線"),
        ("怎麼量", "新 C++ providers (O1heapFragProvider + TLSFFragProvider) 嵌入 sampler `.so`；env-driven dispatch"),
        ("先 decouple",
         "audit_v2 G2-G4：把 hybrid stats counters 從 hardcoded 改 provider 介面（HybridStatsView API）"),
        ("驗哪些 arm",  "D-v4 N=2 + B N=2 跨 arm 比；A 用既有 mallinfo2 (Phase 2.5a 已通)"),
        ("Pre-registered gate",
         "`reports/frag_2_5b_gate.md` 已 commit；7 個 C-criteria（perturbation / completeness / schema / sanity / per-thread enumeration / two-provider mode）"),
        ("期望結論",
         "D-v4 vs B 在 30 s bag 內 frag_ratio 趨勢；長 soak 才能看真正 drift（Session 14）"),
    ]
    for i, (label, desc) in enumerate(plan):
        ry = 0.51 - i * 0.045
        fig.text(0.05, ry, label, fontsize=11, fontweight="bold", color=ACCENT)
        fig.text(0.18, ry, _wrap(desc, 75), fontsize=11, color=NAVY)

    fig.text(0.04, 0.21, "為什麼 fragmentation 重要",
             fontsize=13, fontweight="bold", color=GREEN)
    fig.text(0.05, 0.18,
             "• 短時間看不出問題的 allocator，long-soak 後才會因 fragmentation 拒絕分配 — 是 D 的「bounded WCET」claim 的另一個必要條件",
             fontsize=11, color=NAVY)
    fig.text(0.05, 0.155,
             "• 若 D-v4 frag 趨勢平穩、B 在 30s 內就漲 → 直接證據 D 在「長期使用」上比 B 強",
             fontsize=11, color=NAVY)

    _takeaway(fig, "本次 POC 沒量 frag；frag_2_5b_gate.md 已預先註冊 PASS / PARTIAL / FAIL；Session 12 出結果後可進報告。")
    fig.savefig(out)
    plt.close(fig)


def td_11d_caret_cv(out: Path):
    fig = _slide("最終 KPI — critical-path e2e latency CV < 0.15（CARET + caret_report 量）",
                 "Coefficient of Variation = σ/μ；自駕確定性的單一最重要產品指標",
                 FOOT_L, FOOT_R)

    fig.text(0.04, 0.79, "為什麼 CV 是最終 KPI（不只看 p99 或 mean）",
             fontsize=14, fontweight="bold", color=NAVY)
    why = [
        "bounded WCET claim 只描述「最壞點」，不描述「整體分佈穩定度」",
        "CV = stddev / mean = 「相對變異率」 → CV < 0.15 = 標準差不超過平均的 15 %",
        "自駕系統最在乎的是「可預測」 → 慢一點但穩 > 快一點但抖（控制系統可以加 margin 但無法處理 jitter）",
        "Autoware Universe 級的產品聲明，這個數字是必過門檻",
    ]
    for i, line in enumerate(why):
        fig.text(0.05, 0.74 - i * 0.04, "• " + _wrap(line, 75),
                 fontsize=11, color=NAVY)

    fig.text(0.04, 0.55, "怎麼量 — CARET trace + caret_report path analysis pipeline",
             fontsize=14, fontweight="bold", color=ACCENT)
    pipeline = [
        ("Step 1", "ros2 caret record",
         "啟動時 LD_PRELOAD libcaret.so + 平行跑 ros2 caret record；trace 落 ~/.ros/tracing/"),
        ("Step 2", "定義 critical path（target_path.json）",
         "perception → planning → control chain 名單；user 既有 target_path_latest_CH_*.json 已有模板"),
        ("Step 3", "caret_report/sample_autoware/run.sh <trace>",
         "用 user 既有自動化跑 path analysis；產 callback-by-callback timeline + e2e latency histogram"),
        ("Step 4", "extract_chain_jitter.py（待寫）",
         "從 caret_report 輸出抓出每條 chain 的 mean / stddev / p50 / p99 / **CV**；輸出 schema=1 TSV"),
        ("Step 5", "PASS/FAIL 判定",
         "預先註冊 caret_jitter_gate.md：D-v4 critical-path CV < 0.15 = PASS；< A 但 ≥ 0.15 = PARTIAL"),
    ]
    for i, (step, name, desc) in enumerate(pipeline):
        ry = 0.51 - i * 0.045
        fig.text(0.05, ry, step, fontsize=10.5, fontweight="bold", color=ACCENT)
        fig.text(0.115, ry, name, fontsize=11, fontweight="bold", color=NAVY)
        fig.text(0.40, ry, _wrap(desc, 65), fontsize=10.5, color=NAVY)

    fig.text(0.04, 0.27, "跟既有 metric 的關係",
             fontsize=13, fontweight="bold", color=GREEN)
    rel = [
        "● 資源層（Δminflt / ΔRSS / rss_pre / frag_ratio）= 「allocator 自己用了多少」 → 已量",
        "● Layer 1（單次 malloc latency p99）= 「allocator 內部最差情況」 → Session 11 量",
        "● **Layer 2（critical-path e2e latency CV）= 「整個系統最終的確定性」 → Session 10 量 ⭐**",
    ]
    for i, line in enumerate(rel):
        fig.text(0.05, 0.23 - i * 0.03, line, fontsize=11, color=NAVY)

    _takeaway(fig, "若 D-v4 在 Session 10 跑出 CV < 0.15 且優於 A/B → 立刻可以對 TIER IV / Autoware Universe 講「確定性提昇」product story；CV 跨不過去 → 轉 Heijunka L2 才能補上。")
    fig.savefig(out)
    plt.close(fig)


def td_11e_heijunka(out: Path):
    fig = _slide("未來路徑：用 Heijunka 平準化把記憶體 burst 攤平 — D 還能再升級",
                 "L0 (本次 POC 證據) → L1 (Memory Classifier) → L2 (Heijunka Governor) → L3 (Runtime Adapters) → L4 (Product)",
                 FOOT_L, FOOT_R)

    fig.text(0.04, 0.79, "現況痛點 — 「單個 D 還不夠」",
             fontsize=14, fontweight="bold", color=NAVY)
    pain = [
        "D allocator 提供「per-thread 內 bounded malloc」— 單 thread 看延遲有上限",
        "但「多 thread 同時 alloc burst」仍可能讓 fallback / TLSF 池被打爆 → 整體 WCET 仍在惡化",
        "Autoware 真實 workload：感知 callback 在 lidar frame tick 上同步觸發 → 所有 thread 同時要記憶體（同步 burst）",
        "純靠 allocator 解最差情況不夠 — 必須在分配「之上」做排程控制",
    ]
    for i, line in enumerate(pain):
        fig.text(0.05, 0.74 - i * 0.04, "• " + _wrap(line, 75),
                 fontsize=11, color=NAVY)

    fig.text(0.04, 0.55, "Heijunka（豐田生產系統的「平準化」） 應用到記憶體",
             fontsize=14, fontweight="bold", color=ACCENT)

    layers = [
        ("L1", "Memory Classifier", "把 malloc 依 size 分 C0-C5 6 類；perception/control 等不同類有不同行為", ACCENT),
        ("L2", "Heijunka Governor", "監控各類 alloc rate；偵測 burst → 動態 throttle / pool migration / priority queue 排程", GREEN),
        ("L3", "Runtime Adapters",  "ROS callback hook + scheduler integration；讓 governor 的決定真的 inject 進 callback 排程",  ACCENT),
        ("L4", "Product Surface",   "TIER IV 對外 claim：「在最壞 lidar tick 同步 burst 下 WCET 仍 bounded」",                    NAVY),
    ]
    for i, (id_, name, desc, color) in enumerate(layers):
        ry = 0.51 - i * 0.05
        bid = FancyBboxPatch((0.05, ry - 0.018), 0.04, 0.038,
                             boxstyle="round,pad=0.002,rounding_size=0.005",
                             linewidth=0, facecolor=color,
                             transform=fig.transFigure)
        fig.patches.append(bid)
        fig.text(0.07, ry, id_, fontsize=12, fontweight="bold",
                 color="white", ha="center", va="center")
        fig.text(0.10, ry, name, fontsize=12, fontweight="bold",
                 color=color, va="center")
        fig.text(0.27, ry, _wrap(desc, 75), fontsize=11, color=NAVY,
                 va="center")

    fig.text(0.04, 0.27, "落地步驟（從本次 POC 接得上）",
             fontsize=13, fontweight="bold", color=GREEN)
    steps = [
        "短期：本次 L0 evidence 已可找出 burst-heavy 的 ROS node → 先選擇性套用 D（Phase 3 S0, Session 11）",
        "中期：L1 Memory Classifier — alloc tag size class；觀察 per-class burst pattern",
        "長期：L2 Heijunka Governor — throttle / pool-migration 決策；需修改 ROS executor",
    ]
    for i, line in enumerate(steps):
        fig.text(0.05, 0.23 - i * 0.045, "• " + line,
                 fontsize=10.5, color=NAVY)

    _takeaway(fig, "D 是 L0/L3 層的 building block；要拿到產品級 determinism claim，L1 + L2 (Heijunka) 才是終局——這也是 AGA Gen2 平台的設計方向。")
    fig.savefig(out)
    plt.close(fig)


def td_12_next(out: Path):
    fig = _slide("下一階段路徑 — 6 個 session 內定論",
                 "重要實驗（CARET 端到端延遲）排在 Session 10，不要拖到最後",
                 FOOT_L, FOOT_R)

    sessions = [
        ("Session 9",  "量測協定收尾 + Tier 0 metric 整合",       "30-90 min", ACCENT),
        ("Session 10", "**CARET 端到端延遲抖動 ⭐ 關鍵 milestone**", "~3 hr",   GREEN),
        ("Session 11", "單次 malloc 延遲 + 選擇性套用試做",        "1 day",   ACCENT),
        ("Session 12", "Allocator 內部碎片化指標",                 "1 day",   ACCENT),
        ("Session 13", "**最終結論報告**：PASS / PARTIAL",          "0.5 day", GREEN),
        ("Session 14", "長時間 soak 測試（15+ min）",              "1 day",   ACCENT),
    ]

    fig.text(0.04, 0.79, "Schedule v5 重排（Karpathy / Tesla 原則：先跑承重實驗）",
             fontsize=12, color=GREY_DARK)

    y0 = 0.74
    row_h = 0.085
    for i, (sess, content, dur, color) in enumerate(sessions):
        ry = y0 - i * row_h
        bbox_s = FancyBboxPatch((0.04, ry - 0.026), 0.10, 0.045,
                                boxstyle="round,pad=0.003,rounding_size=0.005",
                                linewidth=0, facecolor=color,
                                transform=fig.transFigure)
        fig.patches.append(bbox_s)
        fig.text(0.09, ry - 0.005, sess, fontsize=11.5, fontweight="bold",
                 color="white", ha="center", va="center")
        fig.text(0.16, ry - 0.005, content, fontsize=12, color=NAVY,
                 va="center")
        fig.text(0.92, ry - 0.005, dur, fontsize=10, color=GREY_DARK,
                 ha="right", va="center")

    fig.text(0.5, 0.20, "三個預先註冊的 fail-fast gate（PASS/FAIL 判定都先寫好）",
             fontsize=12, fontweight="bold", color=ACCENT, ha="center")
    fig.text(0.5, 0.17,
             "G-protocol (Session 9) · G-jitter (Session 10) ⭐ · G-S0 (Session 11)",
             fontsize=11, color=NAVY, ha="center")
    fig.text(0.5, 0.145,
             "如果 Session 10 的 CARET FAIL，立刻轉「選擇性套用 D」路徑，不浪費後面 4 個 session",
             fontsize=10.5, color=GREY_DARK, ha="center", fontstyle="italic")

    _takeaway(fig,
              "若 Session 10 通過 → Session 13 報「D 通過」；若 Session 10 不通過 → 轉選擇性套用，仍有路。",
              y=0.085)
    fig.savefig(out)
    plt.close(fig)


# ============================================================================
# ENGINEER SUPPLEMENT (zh-TW, 4 slides)
# ============================================================================

ENG_FOOT_L = "AGA Gen2 L0 Evidence Plane · 工程師補充 · 2026-04-30"
ENG_FOOT_R = "heaphook_experiments / synthesis_v1.md § 9 / § 12"


def eng_01_fixes(out: Path):
    fig = _slide("從 C 到 D — 5 個獨立 root cause 修了什麼",
                 "技術主管不需要看；工程 reviewer / 接手者必看",
                 ENG_FOOT_L, ENG_FOOT_R)

    fixes = [
        ("F1",
         "資料結構並發保護",
         "FreedPointersMap::push 多 thread race 重複建 _MapNode + 洩 FreedPointers",
         "桶鎖內 find-then-insert；同個 commit 同時包含紅測 + fix（TDD）"),
        ("F2",
         "啟動 NULL 防呆",
         "mmap 失敗回 MAP_FAILED / O1heap pool 還沒設好被叫 → SEGV",
         "全路徑 NULL handle + MAP_FAILED 容錯；6 個既有 gtest 守護"),
        ("F3",
         "TLSF 動態容器邊界",
         "increase_mmap_area 對 num_mmap_areas_ 在鎖外讀，鎖內擴容仍 OOB",
         "鎖內二次邊界檢查；test_hybrid_correctness::F3 守護"),
        ("F4",
         "預設初始化安全",
         "O1heapWrapper / TLSFConteWrapper 沒 default-init 守護 → 未配置就用",
         "wrapper 加 sentinel；default ctor 後 alloc/owns/dealloc 全 no-op"),
        ("G1",
         "統計計數可信度",
         "tl_count_ / proc_count_ 多 thread 寫，遺失更新 → 報告數字不可信",
         "std::atomic<size_t> + fetch_add(memory_order_relaxed)；6 LoC"),
    ]
    n = len(fixes)
    margin = 0.04
    gap = 0.018
    box_w = (1 - 2 * margin - (n - 1) * gap) / n
    y0 = 0.18
    box_h = 0.62

    for i, (id_, title, problem, fix) in enumerate(fixes):
        x0 = margin + i * (box_w + gap)
        bbox = FancyBboxPatch((x0, y0), box_w, box_h,
                              boxstyle="round,pad=0.005,rounding_size=0.012",
                              linewidth=2, edgecolor=ACCENT, facecolor="white",
                              transform=fig.transFigure)
        fig.patches.append(bbox)
        bid = FancyBboxPatch((x0 + 0.005, y0 + box_h - 0.05), 0.04, 0.038,
                             boxstyle="round,pad=0.002,rounding_size=0.006",
                             linewidth=0, facecolor=ACCENT,
                             transform=fig.transFigure)
        fig.patches.append(bid)
        fig.text(x0 + 0.025, y0 + box_h - 0.031, id_,
                 fontsize=12, fontweight="bold", color="white",
                 ha="center", va="center")
        fig.text(x0 + 0.05, y0 + box_h - 0.04, title,
                 fontsize=11.5, fontweight="bold", color=NAVY, va="top")

        fig.text(x0 + 0.005, y0 + box_h - 0.11, "原本問題",
                 fontsize=9, color=RED, fontweight="bold")
        fig.text(x0 + 0.005, y0 + box_h - 0.135, _wrap(problem, 18),
                 fontsize=10, color=NAVY, va="top")

        fig.text(x0 + 0.005, y0 + 0.20, "修法",
                 fontsize=9, color=GREEN, fontweight="bold")
        fig.text(x0 + 0.005, y0 + 0.175, _wrap(fix, 18),
                 fontsize=10, color=NAVY, va="top")

    fig.text(0.5, 0.04,
             "效果：arm C 88 aborts + 89 grep OOM → arm D-v4 4 aborts + 0 grep OOM（與 A glibc 同等級）",
             fontsize=12, color=NAVY, ha="center", fontweight="bold")
    fig.savefig(out)
    plt.close(fig)


def eng_02_sampler(out: Path):
    fig = _slide("Sampler 干擾對不同 allocator 不同 — ranking 對 sampler 模式敏感",
                 "因此 cross-arm 比較須在同 sampler 模式下做（apples-to-apples）",
                 ENG_FOOT_L, ENG_FOOT_R)

    rows = [("A glibc + tcache",       "−1.5 %",  ACCENT, "tcache 吸收 89-PID smaps_rollup 的 ancillary mallocs"),
            ("D hybrid",               "+11 %",   ACCENT, "per-thread O1heap fast path 吸收大部分；少量落 TLSF"),
            ("B stockpile (簡化)",     "+48 %",   RED,    "全 ancillary alloc 落單一全域池 → 序列化 + 鎖等待")]

    fig.text(0.06, 0.75,
             "Sampler 取樣為了量 PSS / cgroup 而打 89 個 PID 的 /proc/<pid>/smaps_rollup",
             fontsize=12, color=NAVY)
    fig.text(0.06, 0.71,
             "本身會在 SUT 內觸發 ancillary mallocs；不同 allocator 吸收能力不同",
             fontsize=11, color=GREY_DARK)

    fig.text(0.06, 0.61, "Sampler 帶來的 Δminflt 變化（sampler-ON vs sampler-OFF）",
             fontsize=13, fontweight="bold", color=NAVY)

    for i, (label, val, color, mech) in enumerate(rows):
        ry = 0.55 - i * 0.07
        fig.text(0.07, ry, label, fontsize=12, fontweight="bold", color=NAVY)
        fig.text(0.27, ry, val, fontsize=20, color=color, fontweight="bold")
        fig.text(0.36, ry, mech, fontsize=11, color=NAVY)

    fig.text(0.06, 0.27, "結果：cross-arm ranking 在兩種模式下不同",
             fontsize=13, fontweight="bold", color=ACCENT)
    fig.text(0.06, 0.235, "• sampler-OFF: B Δminflt −83 % 勝 D-v4 −79 %（B 領先 4 pp）",
             fontsize=11, color=NAVY)
    fig.text(0.06, 0.205, "• sampler-ON  : D-v4 Δminflt −78.2 % 勝 B −77.3 %（D-v4 領先 1 pp）",
             fontsize=11, color=NAVY)

    _takeaway(fig, "Production-like 量測（sampler-ON）= D 微勝；apples-to-apples 結論一定要先固定 sampler 模式。")
    fig.savefig(out)
    plt.close(fig)


def eng_03_audit(out: Path):
    fig = _slide("證據鏈 — 報告每個數字一步追到「當時的設定 + sha256」",
                 "tools/run_ab_phase.sh 在 phase 啟動時 dump exp_settings.tsv；compute_summary.sh 攤進 MANIFEST",
                 ENG_FOOT_L, ENG_FOOT_R)

    code = """env/exp_settings_A.tsv  (schema=1, 由 tools/run_ab_phase.sh 在 phase 開始時寫)
─────────────────────────────────────────────────────────────────
key                          value
arm                          A
phase_started_at             2026-04-30T08:06:52Z
host                         52-0b30668-05
kernel                       6.8.0-40-generic
rmw_implementation           rmw_cyclonedds_cpp
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
─────────────────────────────────────────────────────────────────"""

    fig.text(0.5, 0.79, code, family="monospace", fontsize=10, color=NAVY,
             transform=fig.transFigure, ha="center", va="top")

    chain_y = 0.20
    chain = [
        ("synthesis_v1 § 1", "headline"),
        ("cross_abcd § R-v3", "數字表"),
        ("MANIFEST.md", "## Experiment settings"),
        ("env/exp_settings_<arm>.tsv", "schema=1 + sha256"),
    ]
    fig.text(0.5, chain_y + 0.04, "證據鏈（每步一個 click）",
             fontsize=12, fontweight="bold", color=NAVY, ha="center")
    n = len(chain)
    margin = 0.05
    box_w = (1 - 2 * margin) / n - 0.025
    gap = 0.025
    bx0 = margin
    by = chain_y - 0.045
    for i, (label, sub) in enumerate(chain):
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

    _takeaway(fig, "沒有捏造數字 — 報告每一格回追到 sha256 釘錨的 immutable run 目錄。")
    fig.savefig(out)
    plt.close(fig)


def eng_04_schedule(out: Path):
    fig = _slide("Schedule v5 重排細節 — Layer 2 提前到 Session 10",
                 "Karpathy / Tesla 原則：承重實驗先跑、雙分支預先註冊、stop-loss 限縮",
                 ENG_FOOT_L, ENG_FOOT_R)

    fig.text(0.04, 0.79, "為什麼 Layer 2 (CARET) 必須在 Session 10",
             fontsize=14, fontweight="bold", color=NAVY)
    bullets = [
        "整個 POC 押在「hybrid 端到端延遲抖動 < stockpile」這個假設",
        "在 Session 14 才量 = 等於浪費 Session 10-13 在不確定的中間品上",
        "CARET v0.6.2 + caret_report 已備齊（驗過 62 MB trace OK）",
        "若 Session 10 FAIL：立刻轉 S0 selective-apply 路徑，Session 11 接得上",
        "若 Session 10 PASS：Session 11-13 全變成支撐證據，故事順",
    ]
    for i, b in enumerate(bullets):
        fig.text(0.05, 0.74 - i * 0.04, "• " + _wrap(b, 60),
                 fontsize=11, color=NAVY)

    fig.text(0.04, 0.43, "三個預先註冊的 fail-fast gate",
             fontsize=14, fontweight="bold", color=ACCENT)
    gates = [
        ("G-protocol",       "Session 9",       "play_bag.sh pause-unpause 修正驗證", ACCENT),
        ("G-jitter ⭐",       "Session 10",      "CARET e2e jitter — milestone closer", GREEN),
        ("G-S0",             "Session 11",      "選擇性套用 D 是否能達到 jitter 目標", ACCENT),
    ]
    for i, (name, when, desc, color) in enumerate(gates):
        ry = 0.38 - i * 0.05
        bid = FancyBboxPatch((0.05, ry - 0.018), 0.12, 0.035,
                             boxstyle="round,pad=0.002,rounding_size=0.005",
                             linewidth=0, facecolor=color,
                             transform=fig.transFigure)
        fig.patches.append(bid)
        fig.text(0.11, ry - 0.001, name, fontsize=10.5, fontweight="bold",
                 color="white", ha="center", va="center")
        fig.text(0.19, ry - 0.001, when, fontsize=10.5, color=GREY_DARK,
                 va="center")
        fig.text(0.29, ry - 0.001, desc, fontsize=11, color=NAVY,
                 va="center")

    _takeaway(fig, "每個 gate 預先寫死 PASS / PARTIAL / FAIL 標準 — 沒有事後 gerrymandering。")
    fig.savefig(out)
    plt.close(fig)


def eng_05_aborts(out: Path):
    fig = _slide("為什麼每個 arm 都有 ~4 個 abort — 跟 allocator 無關，是 Autoware 拆機殘留",
                 "工程師被問到時拿這頁回答；A glibc / D-v4 hybrid 同數，B stockpile +1",
                 ENG_FOOT_L, ENG_FOOT_R)

    fig.text(0.04, 0.79, "觀察 — 三個 arm 都穩定有相近 abort 數",
             fontsize=14, fontweight="bold", color=NAVY)
    rows = [
        ("A glibc",   "rep1: 4 · rep2: 4",  "這是 baseline；跟 allocator 無關",  NAVY),
        ("B stockpile", "rep1: 5 · rep2: 5",  "比 A 多 1 — stockpile 全域池在 SIGINT 期間多走一條清理路徑",  ORANGE),
        ("D-v4 hybrid", "rep1: 4 · rep2: 4",  "跟 A 同；F1-F4 fix 把 hybrid 從 88 abort 修回 baseline 4",  GREEN),
        ("C 失敗",     "88（歷史）",          "fix 前的 hybrid bug 觸發大規模 abort；C 不是產品候選",  RED),
    ]
    for i, (label, count, expl, color) in enumerate(rows):
        ry = 0.74 - i * 0.045
        fig.text(0.05, ry, label, fontsize=12, fontweight="bold", color=color)
        fig.text(0.18, ry, count, fontsize=12, color=NAVY)
        fig.text(0.32, ry, _wrap(expl, 60), fontsize=11, color=NAVY)

    fig.text(0.04, 0.50, "根因分析（基於 t1.log 觀察 + Autoware 拆機 semantics）",
             fontsize=14, fontweight="bold", color=ACCENT)
    causes = [
        "• SIGINT 送進 ros2 launch 時，composable_container 透過 component manager 嘗試卸載 ~89 個 node",
        "• 卸載順序由 launch description 決定，部分 node 對「parent shutdown 之前 child 還沒收到 destroy」的競態沒守好",
        "• 經過 timeout（預設 5s）後 launch 用 SIGTERM 強制；少數 node 有 atexit 處理在 SIGTERM 下 throw → abort",
        "• 觀察到的常見抱怨者（從歷史 t1.log）：vehicle_cmd_gate · trajectory_follower · planning lifecycle node · sensing 端某些 driver wrapper",
        "• Autoware-側 issue 已存在多版本；本量測不修 Autoware（per project memory `feedback_no_autoware_modification.md`），故 4-aborts 視為 baseline 環境噪音",
    ]
    for i, line in enumerate(causes):
        fig.text(0.05, 0.46 - i * 0.04, _wrap(line, 90),
                 fontsize=10.5, color=NAVY)

    fig.text(0.04, 0.22, "工程師被問到時的回答模板",
             fontsize=14, fontweight="bold", color=GREEN)
    answer = ("「4 個 abort 是 Autoware 在 component_container_mt 拆機時的環境噪音，"
              "三個 allocator 都同數，不是 D 引入的。要徹底為零需要修 Autoware shutdown "
              "lifecycle，但本 POC 規範禁止改 Autoware。Cross-arm 比較數字不受影響。」")
    fig.text(0.05, 0.18, _wrap(answer, 90), fontsize=11.5,
             color=NAVY, fontstyle="italic")

    _takeaway(fig, "4 aborts ≠ D 的 bug；C 88 aborts 才是 D 的 bug（已在 F1-F4 修掉，現在 D-v4 = baseline 4）。")
    fig.savefig(out)
    plt.close(fig)


# ============================================================================
# TD v2 (10-slide layout) — replaces 17-slide v1
# ============================================================================


def td_v2_02_proposal_with_image(out: Path, fig_path: Path):
    """Combines old 02+03+04 + embeds user's td_arm_d_workflow.png."""
    fig = _slide("我們的提案 D + 4-arm 實驗設計（O1heap fast path + TLSF fallback）",
                 "問題：Autoware 記憶體確定性 → 提案 D：thread-local O1heap + 全域 TLSF 雙層配置",
                 FOOT_L, FOOT_R)

    # Left: workflow image (~60% width)
    if fig_path.exists():
        img = mpimg.imread(fig_path)
        img_ax = fig.add_axes([0.03, 0.20, 0.58, 0.62])
        img_ax.imshow(img)
        img_ax.axis("off")

    # Right top: 4-arm 對照
    rx = 0.63
    fig.text(rx, 0.79, "4-arm 對照組", fontsize=13, fontweight="bold", color=NAVY)
    arms = [
        ("A",   "glibc 原生",        "業界 baseline",     GREY_DARK),
        ("B",   "stockpile",        "TIER IV 既有解",    ACCENT),
        ("C",   "未修 D",            "驗證 fix（不是候選）", RED),
        ("D-v4", "我們的提案",        "F1-F4+G1 修好的 D",  GREEN),
    ]
    for i, (id_, what, role, color) in enumerate(arms):
        ry = 0.74 - i * 0.05
        fig.text(rx, ry, id_, fontsize=14, fontweight="bold", color=color, va="center")
        fig.text(rx + 0.045, ry, what, fontsize=11, color=NAVY, va="center")
        fig.text(rx + 0.18, ry, role, fontsize=10, color=GREY_DARK, va="center")

    # Right bottom: 兩條補充註解
    fig.text(rx, 0.50, "補充（對齊 source code）", fontsize=12, fontweight="bold", color=ACCENT)
    notes = [
        "(a) 「O1heap fast path」實際範圍 = bytes ≤ "
        "**~4 MiB** (DEFAULT_O1HEAP_POOL_SIZE)；圖中「小/中塊」"
        "舉例 10K/5K/100K 正確，但實際上限是 4 MiB",
        "(b) 啟動時每個 thread 第一次 alloc 觸發 mmap(4 MiB)；"
        "**89 thread × 4 MiB ≈ +356 MiB pre-alloc**，"
        "這是 D 的 rss_pre +50 % 的根因（架構成本，非 bug）",
    ]
    for i, line in enumerate(notes):
        fig.text(rx, 0.46 - i * 0.10, "● " + _wrap(line, 36),
                 fontsize=10, color=NAVY, va="top")

    _takeaway(fig, "D 對「小/中塊」走快路徑 (≤4 MiB)；大塊走 TLSF fallback — 那是延遲 tail 的主要風險源（→ Session 10 量 CV<0.15）。")
    fig.savefig(out)
    plt.close(fig)


def td_v2_03_metrics_kpi(out: Path):
    fig = _slide("衡量 D 是否成功：4 個 KEY metrics + 終極 KPI = critical-path CV<0.15",
                 "資源層 2 個 + 延遲層 2 個；終極判定看 CV（端到端延遲變異率）",
                 FOOT_L, FOOT_R)

    rows = [
        ("✅", "Δminflt", "次 (count)",
         "30 s bag 期間 minor page fault 累積；越低越好",
         "本次量到", GREEN, "資源層"),
        ("✅", "ΔRSS", "KiB / MiB",
         "30 s bag 期間 RSS 成長；越低 = reuse 效率高",
         "本次量到", GREEN, "資源層"),
        ("⏳", "單次 malloc latency p99 / p99.9", "ns",
         "每次 malloc 進入到回傳的奈秒分佈尾端",
         "Session 11 量", ORANGE, "延遲層 1"),
        ("⏳", "**critical-path e2e CV (= σ/μ) ⭐**", "比例（無單位）",
         "感知→規劃→控制 chain 端到端延遲變異率；目標 **CV < 0.15**",
         "Session 10 量", RED, "**延遲層 2 = 終極 KPI**"),
    ]

    fig.text(0.04, 0.79, "「終極 KPI」= 自駕系統真正在乎「可預測性」 — 不只是快、是穩",
             fontsize=11, color=GREY_DARK)

    y0 = 0.20
    row_h = 0.135
    for i, (mark, name, unit, what, status, color, layer) in enumerate(rows):
        ry = 0.74 - i * row_h
        bid = FancyBboxPatch((0.045, ry - 0.045), 0.05, 0.05,
                             boxstyle="round,pad=0.003,rounding_size=0.006",
                             linewidth=0, facecolor=color,
                             transform=fig.transFigure)
        fig.patches.append(bid)
        fig.text(0.07, ry - 0.020, mark, fontsize=20, color="white",
                 ha="center", va="center", fontweight="bold")

        fig.text(0.11, ry - 0.005, name, fontsize=14,
                 fontweight="bold", color=NAVY)
        fig.text(0.11, ry - 0.034, "● " + what + f"  ／  單位：{unit}",
                 fontsize=10.5, color=NAVY)
        fig.text(0.11, ry - 0.058, "● " + layer,
                 fontsize=10.5, color=GREY_DARK)
        fig.text(0.92, ry - 0.005, status, fontsize=11, color=color,
                 fontweight="bold", ha="right")

    fig.text(0.04, 0.18,
             "次要 metrics（rss_pre / aborts / OOM / nprocs / PSI / PSS / cgroup events / frag_ratio）"
             "→ 完整一覽 + 單位請見 engineer deck #9。",
             fontsize=10, color=GREY_DARK, fontstyle="italic")

    _takeaway(fig, "本次量到 2 個 KEY（資源層）；延遲層 2 個 KEY 是 Session 10-11 才有結果，CV<0.15 是 milestone closer。")
    fig.savefig(out)
    plt.close(fig)


def td_v2_04_results_3up(out: Path, base: Path):
    fig = _slide("結果（資源層）三圖一覽：D 與 B 都比 A 顯著省，D 動態效率微勝，rss_pre 是設計取捨",
                 "怎麼看每張圖 + insight 寫在底下；3 圖 paired bootstrap 10 k iters seed=42；CI 都不含 0",
                 FOOT_L, FOOT_R)

    figs = [
        ("① Δminflt vs A   D −78.2 % · B −77.3 %",
         "m0prime_estimation_minflt_n2.png",
         "怎麼看：上半每 arm 兩個圓點 = 兩次重跑；下半 bootstrap Δ 分佈 + 95 % CI 條\n"
         "Insight：D 與 B 都顯著降低 Page fault；D **微勝 B 1 pp**；CI 不含 0"),
        ("② ΔRSS vs A     D −28.6 % · B −22.8 %",
         "m0prime_estimation_rss_delta_n2.png",
         "怎麼看：30 s bag 期間 RSS 成長量；越低 = allocator reuse 效率越高\n"
         "Insight：D 比 B **領先 6 pp**；per-thread pool 內部 reuse 比全域池有效"),
        ("③ rss_pre vs A   D **+49.6 %** · B −7.8 %",
         "m0prime_estimation_rss_pre_n2.png",
         "怎麼看：bag 還沒跑前的 steady-state RSS（啟動完就站著的記憶體）\n"
         "Insight：D 多吃 ~7 GiB = 89 thread × 4 MiB pre-alloc；**這是 trade-off 不是 regression**"),
    ]
    n = 3
    margin = 0.03
    gap = 0.015
    panel_w = (1 - 2 * margin - (n - 1) * gap) / n
    panel_y = 0.42
    panel_h = 0.36

    for i, (title, fname, body) in enumerate(figs):
        x0 = margin + i * (panel_w + gap)
        path = base / fname
        if path.exists():
            img = mpimg.imread(path)
            ax = fig.add_axes([x0, panel_y, panel_w, panel_h])
            ax.imshow(img)
            ax.axis("off")
        # Header above
        fig.text(x0 + panel_w / 2, panel_y + panel_h + 0.025, title,
                 fontsize=11.5, fontweight="bold", color=NAVY, ha="center")
        # Body text below — 怎麼看 + insight
        fig.text(x0 + 0.005, panel_y - 0.015, body,
                 fontsize=9.5, color=NAVY, va="top")

    # Reproducibility callout (bottom band)
    cy = 0.18
    bbox = FancyBboxPatch((0.04, cy - 0.04), 0.92, 0.06,
                          boxstyle="round,pad=0.005,rounding_size=0.012",
                          linewidth=2, edgecolor=GREEN, facecolor="white",
                          transform=fig.transFigure)
    fig.patches.append(bbox)
    fig.text(0.06, cy + 0.005, "Reproducibility",
             fontsize=12, fontweight="bold", color=GREEN, va="center")
    fig.text(0.20, cy + 0.005,
             "D-v4: **0.01 %** · B: 4.0 % · A: 8.8 %　— D 比 A 緊 3 個數量級",
             fontsize=11, color=NAVY, va="center")

    _takeaway(fig, "資源層 D 微勝 B；rss_pre 是 trade-off 不是 regression；但這是「資源使用」結果——「延遲」結果（CV<0.15）才是終極 KPI，下一步量。")
    fig.savefig(out)
    plt.close(fig)


def td_v2_05_caveats(out: Path):
    fig = _slide("沒驗到的（範圍） + 方法論限制 — 結論「方向」可信，「跨情境概化」需下階段補",
                 "Tesla 量測紀律 + Stanford EECS 嚴審雙視角",
                 FOOT_L, FOOT_R)

    cells = [
        ("⚠ 沒驗到的（範圍 caveat）", [
            "**bounded WCET**（Layer 1 alloc latency / Layer 2 e2e CV）— 真產品 KPI",
            "**Long-soak 15+ min** — leak / fragmentation drift / cgroup OOM",
            "**Functional behaviour** 紀錄（rviz pose / NDT iter / planning latency）",
            "**Cross-host / 替 bag / rate sweep** — external validity",
            "**選擇性套用 (S0)** — 只在 perception subtree 套 D 是否更佳",
        ], ORANGE),
        ("⚠ 方法論限制（誠實宣告）", [
            "**N=2 reps** 仍低於 paper-grade（inferential 至少 N=5；bootstrap CI 嚴格 N≥30）",
            "**單機 single host / 單 bag / 單 rate** — concept proof 等級",
            "**Sampler 對 D-v4 +11 %** 仍邊緣（在 ±15 % 內但接近上限）",
            "**F1 mem-model UB 仍 deferred** — release build 跑得起，TSan 形式驗證留待 hygiene round",
            "**cgroup v2 memory controller 本機沒掛** → memory.events 全空；要跨機補",
        ], RED),
    ]

    n = len(cells)
    margin = 0.04
    gap = 0.04
    box_w = (1 - 2 * margin - gap) / n
    y0 = 0.18
    box_h = 0.62

    for i, (header, items, color) in enumerate(cells):
        x0 = margin + i * (box_w + gap)
        bbox = FancyBboxPatch((x0, y0), box_w, box_h,
                              boxstyle="round,pad=0.005,rounding_size=0.012",
                              linewidth=2, edgecolor=color, facecolor="white",
                              transform=fig.transFigure)
        fig.patches.append(bbox)
        fig.text(x0 + box_w / 2, y0 + box_h - 0.045, header, fontsize=14,
                 fontweight="bold", color=color, ha="center")
        for j, line in enumerate(items):
            fig.text(x0 + 0.012, y0 + box_h - 0.10 - j * 0.085,
                     "• " + _wrap(line, 36), fontsize=11, color=NAVY, va="top")

    _takeaway(fig, "結論「方向」（D 對 A 有效、D 對 B 微勝）有方法論支撐；「絕對數字 + 跨情境概化」要 Sessions 10-14 補完。")
    fig.savefig(out)
    plt.close(fig)


def td_v2_07_adjacent(out: Path):
    fig = _slide("鄰近量測規劃：Fragmentation（Session 12）+ Long-soak（Session 14）",
                 "兩條軸都有預先註冊 gate；frag 看 D 內部碎片；long-soak 看時間維度穩定性",
                 FOOT_L, FOOT_R)

    # Top half: Fragmentation
    fig.text(0.04, 0.79, "Fragmentation 量測（Phase 2.5b → Session 12）",
             fontsize=14, fontweight="bold", color=ACCENT)
    frag = [
        "現況：Phase 2.5a 已驗 sampler 在 arm A 通電（schema=1 frag_summary.tsv）",
        "下階段：擴 D-v4 + B；audit_v2 G2-G4 解耦 → 加 O1heapFragProvider + TLSFFragProvider",
        "量什麼：frag_ratio = 1 − allocated/capacity；每秒 1 次；分 O1heap 與 TLSF 兩條曲線",
        "預先註冊 gate：`reports/frag_2_5b_gate.md`（7 個 C-criteria）",
    ]
    for i, line in enumerate(frag):
        fig.text(0.05, 0.74 - i * 0.04, "• " + _wrap(line, 75),
                 fontsize=11, color=NAVY)

    # Bottom half: Long-soak
    fig.text(0.04, 0.51, "Long-soak 量測（Session 14）",
             fontsize=14, fontweight="bold", color=GREEN)
    soak = [
        "目的：30 s 短窗看不出的 leak / fragmentation drift / cgroup OOM 在長時間才顯化",
        "規劃：A + B + D-v4 各跑 ≥ 15 min × 2 reps；Tier 0 + frag + Layer 1 + Layer 2 全套同時",
        "預期 surface：D-v4 內 thread-local pool 是否累積 frag；TLSF fallback 是否在大塊請求下漸劣",
        "若 long-soak D 仍穩定 → bounded-WCET 在「長期」軸也成立；若不穩 → 重議設計",
    ]
    for i, line in enumerate(soak):
        fig.text(0.05, 0.46 - i * 0.04, "• " + _wrap(line, 75),
                 fontsize=11, color=NAVY)

    _takeaway(fig, "本次 POC 沒量這兩軸；frag (Session 12) + long-soak (Session 14) 預先註冊；定論待後續。")
    fig.savefig(out)
    plt.close(fig)


def td_v2_09_schedule_gates(out: Path):
    fig = _slide("Schedule v5：6 session 內定論；3 個預先註冊 fail-fast gate 寫死 PASS / FAIL",
                 "Karpathy / Tesla 原則：載重實驗（CARET CV）排在 Session 10，不是末尾",
                 FOOT_L, FOOT_R)

    sessions = [
        ("Session 9",  "C15 protocol fix 驗證 + M2 Tier 0 metric 整合",                 "30-90 min", ACCENT),
        ("Session 10", "**CARET e2e jitter ⭐ 終極 KPI 量測（CV<0.15）**",               "~3 hr",   GREEN),
        ("Session 11", "Layer 1 alloc latency + Phase 3 S0 selective-apply 試做",        "1 day",   ACCENT),
        ("Session 12", "M4 Phase 2.5b D-v4 frag rep",                                   "1 day",   ACCENT),
        ("Session 13", "**M5 synthesis_v1 close ＋ DECISIONS PASS / PARTIAL row**",      "0.5 day", GREEN),
        ("Session 14", "Long-soak A + B + D-v4 with full Tier 0 + frag + Layer 1 + 2",  "1 day",   ACCENT),
    ]
    fig.text(0.04, 0.79, "重排後 schedule（Layer 2 提前到 Session 10）",
             fontsize=12, color=GREY_DARK)
    y0 = 0.74
    row_h = 0.07
    for i, (sess, content, dur, color) in enumerate(sessions):
        ry = y0 - i * row_h
        bbox_s = FancyBboxPatch((0.04, ry - 0.022), 0.10, 0.04,
                                boxstyle="round,pad=0.003,rounding_size=0.005",
                                linewidth=0, facecolor=color,
                                transform=fig.transFigure)
        fig.patches.append(bbox_s)
        fig.text(0.09, ry - 0.003, sess, fontsize=11, fontweight="bold",
                 color="white", ha="center", va="center")
        fig.text(0.16, ry - 0.003, content, fontsize=11.5, color=NAVY, va="center")
        fig.text(0.92, ry - 0.003, dur, fontsize=10, color=GREY_DARK,
                 ha="right", va="center")

    fig.text(0.04, 0.27, "三個預先註冊 fail-fast gate（PASS / PARTIAL / FAIL 標準寫死）",
             fontsize=13, fontweight="bold", color=ACCENT)
    gates = [
        ("G-protocol", "Session 9",   "play_bag.sh pause-unpause 修正驗證"),
        ("G-jitter ⭐", "Session 10", "CARET e2e CV < 0.15 → PASS；CV ≥ 0.15 → PARTIAL"),
        ("G-S0",       "Session 11",  "perception-only 套 D 是否達 jitter 目標"),
    ]
    for i, (name, when, desc) in enumerate(gates):
        ry = 0.22 - i * 0.04
        fig.text(0.05, ry, name, fontsize=11, fontweight="bold",
                 color=ACCENT if "⭐" not in name else GREEN, va="center")
        fig.text(0.18, ry, when, fontsize=10.5, color=GREY_DARK, va="center")
        fig.text(0.30, ry, desc, fontsize=10.5, color=NAVY, va="center")

    _takeaway(fig, "Session 10 通過 → Session 13 報「D 通過 milestone」；Session 10 不過 → Session 11 轉 S0；Session 13 仍能下定論。")
    fig.savefig(out)
    plt.close(fig)


def td_v2_10_appendix_pointer(out: Path):
    fig = _slide("Appendix — 想 deep dive？指向 engineer deck（15 頁）+ 自動報告 + audit chain",
                 "全部材料的入口；技術主管 Q&A 後盾",
                 FOOT_L, FOOT_R)

    sections = [
        ("Engineer deck（工程師版細節 15 頁）",
         "reports/figures/slides_m0prime/for_engineer_supplement/",
         [
             "01 D workflow 完整圖 + code line ref · 02 F1-F4+G1 修了什麼 · 03 sampler 干擾",
             "04-06 三個 KEY chart 完整版 · 07 Reproducibility · 08-09 metrics 詳目+詞彙",
             "10 Methodology defense · 11 Audit chain · 12-13 Frag/Heijunka 細節",
             "14 Schedule v5 · 15 為何 4 abort 回答模板",
         ]),
        ("自動產生數據報告（同 seed 可重現）",
         "reports/cross_abcd_v4_m0prime_zh-TW.md",
         [
             "全 6 reps raw + per-arm mean±SD + bootstrap 95% CI；單位欄含 KiB/MiB",
             "由 tools/make_cross_arm_report.py --lang zh-TW --seed 42 重生",
         ]),
        ("Audit chain（每個數字回追到 sha256）",
         "runs/_poc-2026-04-30/active/<arm-rep>/env/exp_settings_<arm>.tsv",
         [
             "每 rep 的 protocol/sampler/CARET/binary sha256 全紀錄",
             "MANIFEST.md auto-append ## Experiment settings + sha256 釘錨",
         ]),
    ]
    y0 = 0.76
    section_h = 0.21
    for i, (header, path, bullets) in enumerate(sections):
        ry = y0 - i * section_h
        fig.text(0.04, ry, header, fontsize=13, fontweight="bold", color=NAVY)
        fig.text(0.04, ry - 0.030, path, fontsize=10, color=ACCENT, family="monospace")
        for j, b in enumerate(bullets):
            fig.text(0.06, ry - 0.060 - j * 0.030, "● " + b,
                     fontsize=10, color=NAVY, va="top")

    _takeaway(fig, "報告中任何疑問 → 從這 3 條路徑都能追到 raw 數據與當時設定。")
    fig.savefig(out)
    plt.close(fig)


# ============================================================================
# Engineer deck v2 — D design detail page (NEW)
# ============================================================================


def eng_v2_01_d_design(out: Path, fig_path: Path):
    fig = _slide("D allocator workflow（完整版） — 對齊 source code line 引用",
                 "thread-local O1heap fast path + process-level TLSF fallback；"
                 "重點程式位置標於本頁",
                 ENG_FOOT_L, ENG_FOOT_R)

    if fig_path.exists():
        img = mpimg.imread(fig_path)
        # Take ~70% of slide for image
        img_ax = fig.add_axes([0.03, 0.20, 0.65, 0.62])
        img_ax.imshow(img)
        img_ax.axis("off")

    rx = 0.70
    fig.text(rx, 0.79, "Code 對齊（hybrid_o1heap_tlsf_allocator.cpp）",
             fontsize=13, fontweight="bold", color=ACCENT)
    refs = [
        (":22",  "static thread_local O1heapWrapper g_tl_o1heap(DEFAULT_O1HEAP_POOL_SIZE)"),
        (":20",  "DEFAULT_O1HEAP_POOL_SIZE = 1<<22 = 4 MiB"),
        (":75",  "if (align <= O1HEAP_ALIGNMENT && bytes <= max_alloc_size)"),
        (":76",  "ptr = g_tl_o1heap.do_alloc(bytes)  ← O1heap path"),
        (":83",  "ptr = fallback_pool_.do_memalign(bytes, align)  ← TLSF fallback"),
        (":161", "g_tl_o1heap.do_dealloc(ptr)  ← 同 thread free"),
        (":167", "freed_ptrs_map_.push(ptr_tid, ptr)  ← 跨 thread free"),
        (":29",  "FreedPointersMap freed_ptrs_map_;  ← F1 audit fix 修這裡的 race"),
    ]
    for i, (ln, code) in enumerate(refs):
        ry = 0.74 - i * 0.04
        fig.text(rx, ry, ln, fontsize=10, fontweight="bold", color=GREEN, va="center")
        fig.text(rx + 0.04, ry, code, fontsize=9, color=NAVY, family="monospace", va="center")

    fig.text(rx, 0.39, "兩條補充註腳", fontsize=12, fontweight="bold", color=ACCENT)
    notes = [
        "(a) O1heap 範圍上限 = ~4 MiB（DEFAULT_O1HEAP_POOL_SIZE）；"
        "圖中「小/中塊」舉例 10K/5K/100K 正確",
        "(b) 啟動時每 thread 第一次 alloc 觸發 mmap(4 MiB)；"
        "89×4 MiB ≈ +356 MiB pre-alloc → rss_pre +50 % 根因",
    ]
    for i, line in enumerate(notes):
        fig.text(rx, 0.35 - i * 0.10, "● " + _wrap(line, 35),
                 fontsize=10, color=NAVY, va="top")

    fig.text(0.04, 0.04,
             "圖原圖出處：技術主管手繪（path A 直接嵌入；本頁是 engineer 版）",
             fontsize=8, color=GREY_DARK)
    fig.savefig(out)
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--output-base", required=True, type=Path)
    p.add_argument("--figures-base", type=Path,
                   default=Path("reports/figures"))
    args = p.parse_args()

    td_dir = args.output_base / "for_tech_director"
    eng_dir = args.output_base / "for_engineer_supplement"

    # Clean both dirs to remove old v1 PNGs.
    import shutil
    if td_dir.exists():
        shutil.rmtree(td_dir)
    if eng_dir.exists():
        shutil.rmtree(eng_dir)
    td_dir.mkdir(parents=True, exist_ok=True)
    eng_dir.mkdir(parents=True, exist_ok=True)
    base = args.figures_base

    # ----- Tech director deck v2 — 11 slides (hero added at #2) -----
    td_01_cover(td_dir / "01_cover.png")
    td_v2_02_hero_summary(td_dir / "02_hero_summary.png")
    td_v2_02_proposal_with_image(td_dir / "03_proposal_arm_d_workflow.png",
                                  base / "td_arm_d_workflow.png")
    td_v2_03_metrics_kpi(td_dir / "04_metrics_and_kpi.png")
    td_v2_04_results_3up(td_dir / "05_results_3up.png", base)
    td_v2_05_caveats(td_dir / "06_caveats_and_methodology.png")
    td_11d_caret_cv(td_dir / "07_caret_cv_final_kpi.png")
    td_v2_07_adjacent(td_dir / "08_frag_and_long_soak.png")
    td_11e_heijunka(td_dir / "09_heijunka_future.png")
    td_v2_09_schedule_gates(td_dir / "10_schedule_and_gates.png")
    td_v2_10_appendix_pointer(td_dir / "11_appendix_pointer.png")

    # ----- Engineer supplement deck v2 — 15 slides -----
    eng_v2_01_d_design(eng_dir / "01_d_design_detail.png",
                        base / "td_arm_d_workflow.png")
    eng_01_fixes(eng_dir / "02_fixes_C_to_D.png")
    eng_02_sampler(eng_dir / "03_sampler_allocator_specific.png")
    td_07_results_minflt(eng_dir / "04_chart_minflt_full.png",
                         base / "m0prime_estimation_minflt_n2.png")
    td_08_results_rss(eng_dir / "05_chart_rss_growth_full.png",
                     base / "m0prime_estimation_rss_delta_n2.png")
    td_09_results_rss_pre(eng_dir / "06_chart_rss_pre_full.png",
                         base / "m0prime_estimation_rss_pre_n2.png")
    td_10_repro(eng_dir / "07_reproducibility_detail.png")
    td_06_secondary_metrics(eng_dir / "08_secondary_metrics_detail.png")
    td_06b_metrics_glossary(eng_dir / "09_metrics_glossary_full.png")
    td_11b_methodology_defense(eng_dir / "10_methodology_defense_full.png")
    eng_03_audit(eng_dir / "11_audit_chain.png")
    td_11c_frag_plan(eng_dir / "12_frag_plan_detail.png")
    td_11e_heijunka(eng_dir / "13_heijunka_detail.png")
    eng_04_schedule(eng_dir / "14_schedule_v5_detail.png")
    eng_05_aborts(eng_dir / "15_why_4_aborts.png")

    sys.stderr.write(f"wrote 11 tech-director slides (v2 + hero) to {td_dir}\n")
    sys.stderr.write(f"wrote 15 engineer-supplement slides (v2) to {eng_dir}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
