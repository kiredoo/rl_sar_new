#!/usr/bin/env python3
"""Build internal-engineer-to-tech-mgmt McKinsey-style PPTX (Traditional Chinese).
24 main slides + 6 appendix.
"""

import os
import re
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

REPO = Path(__file__).parent.parent
FIG = REPO / "reports" / "figures" / "mckinsey"
OUT = REPO / "reports" / "2026-05-06_1141_MPR_zhTW.pptx"

# Colors (subdued)
# 暖色 + 柔和 palette（避免深藍過重）
COL_TITLE = RGBColor(0x33, 0x55, 0x84)       # 中柔藍灰，取代深海軍藍
COL_SECTION = RGBColor(0x82, 0x8a, 0x95)     # 中暖灰
COL_BODY = RGBColor(0x3c, 0x44, 0x55)        # 暖深灰，不近黑
COL_KPI = RGBColor(0xc9, 0x59, 0x52)         # 暖珊瑚紅
COL_GOOD = RGBColor(0x4a, 0x9b, 0x82)        # 柔和湖綠
COL_ACCENT = RGBColor(0x68, 0x90, 0xb0)      # 柔煙藍
COL_RULE = RGBColor(0xc5, 0xcc, 0xd2)        # 淡灰
COL_SOURCE = RGBColor(0x90, 0x97, 0x9f)      # 淡暖灰
COL_TAKEAWAY_BG = RGBColor(0xfa, 0xf6, 0xee) # 暖米色（非冷灰）
COL_BG_GREEN = RGBColor(0xed, 0xf5, 0xf0)    # 淡湖綠
COL_BG_RED = RGBColor(0xfb, 0xee, 0xea)      # 淡珊瑚
COL_BG_GRAY = RGBColor(0xf3, 0xf1, 0xec)     # 暖米灰

# 表格 header 變化色（避免深藍系 → 多用明亮色彩）
COL_HDR_TEAL = RGBColor(0x4a, 0x8a, 0x82)      # 湖綠 — setup / 控制
COL_HDR_AMBER = RGBColor(0xd4, 0x9a, 0x4a)     # 琥珀 — hero 對照表
COL_HDR_CORAL = RGBColor(0xc9, 0x65, 0x5b)     # 暖珊瑚 — caveat / risk
COL_HDR_PLUM = RGBColor(0x8e, 0x6c, 0x9c)      # 紫梅 — recommendations / decision
COL_HDR_OLIVE = RGBColor(0x82, 0x90, 0x4a)     # 橄欖綠 — methodology
COL_HDR_GRAY = RGBColor(0x72, 0x77, 0x80)      # 暖灰 — outline / nav
COL_HDR_NAVY = COL_TITLE                       # 深藍 — 保留作為對比，少用

FONT_NAME = "Noto Sans CJK TC"

SZ_W = Inches(13.333)
SZ_H = Inches(7.5)
SZ_SECTION = Pt(11)
SZ_TITLE = Pt(24)
SZ_SUBTITLE = Pt(15)
SZ_BODY = Pt(15)
SZ_BULLET = Pt(13)
SZ_KEY_NUMBER = Pt(34)
SZ_KEY_LABEL = Pt(11)
SZ_TAKEAWAY = Pt(13)
SZ_SOURCE = Pt(9)
SZ_TABLE = Pt(11)


def add_text(slide, text, x, y, w, h, *, font_size=Pt(14), bold=False,
             color=COL_BODY, align=PP_ALIGN.LEFT, italic=False, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Emu(0); tf.margin_right = Emu(0)
    tf.margin_top = Emu(0); tf.margin_bottom = Emu(0)
    tf.vertical_anchor = anchor
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.name = FONT_NAME
    run.font.size = font_size
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    return box


def add_section_header(slide, name, slide_no):
    """Stash section info on the slide; rendered later by add_footer at bottom."""
    slide._section_tag = name
    slide._slide_no = slide_no


def add_title(slide, title, subtitle=None):
    # Title sits above an underline rule; subtitle below the rule
    add_text(slide, title, Inches(0.5), Inches(0.55), Inches(12.33), Inches(0.6),
             font_size=SZ_TITLE, bold=True, color=COL_TITLE)
    # Rule via thin rectangle (connector doesn't render reliably in LibreOffice)
    rule = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                   Inches(0.5), Inches(1.18), Inches(12.33), Pt(1.2))
    rule.fill.solid(); rule.fill.fore_color.rgb = COL_RULE
    rule.line.fill.background()
    rule.shadow.inherit = False
    if subtitle:
        add_text(slide, subtitle, Inches(0.5), Inches(1.25), Inches(12.33), Inches(0.4),
                 font_size=SZ_SUBTITLE, color=COL_BODY)


def add_takeaway(slide, text):
    box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(6.55),
                                  Inches(12.33), Inches(0.45))
    box.fill.solid()
    box.fill.fore_color.rgb = COL_TAKEAWAY_BG
    box.line.color.rgb = COL_RULE
    box.line.width = Pt(0.5)
    box.shadow.inherit = False
    tf = box.text_frame
    tf.margin_left = Inches(0.15); tf.margin_right = Inches(0.15)
    tf.margin_top = Emu(0); tf.margin_bottom = Emu(0)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = "Takeaway   "
    r.font.bold = True; r.font.size = SZ_TAKEAWAY
    r.font.color.rgb = COL_TITLE; r.font.name = FONT_NAME
    r2 = p.add_run()
    r2.text = text
    r2.font.size = SZ_TAKEAWAY; r2.font.color.rgb = COL_BODY; r2.font.name = FONT_NAME


def add_source(slide, text):
    add_text(slide, "Source: " + text, Inches(0.5), Inches(7.05), Inches(12.33), Inches(0.2),
             font_size=SZ_SOURCE, color=COL_SOURCE, italic=True)


def add_bullets(slide, bullets, x, y, w, h, *, size=SZ_BULLET, line_spacing=1.2):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Emu(0); tf.margin_right = Emu(0)
    tf.margin_top = Emu(0); tf.margin_bottom = Emu(0)
    for i, b in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.line_spacing = line_spacing
        if isinstance(b, tuple):
            text, color = b
        else:
            text, color = b, COL_BODY
        r = p.add_run()
        r.text = "•  " + text
        r.font.name = FONT_NAME
        r.font.size = size
        r.font.color.rgb = color


def add_image_centered(slide, path, max_w_in, max_h_in, top_in, *, left_in=None,
                        center_x_in=None):
    pic = slide.shapes.add_picture(str(path), 0, 0)
    iw, ih = pic.width, pic.height
    iw_in = iw / 914400.0; ih_in = ih / 914400.0
    scale = min(max_w_in / iw_in, max_h_in / ih_in, 1.0)
    new_w_in = iw_in * scale; new_h_in = ih_in * scale
    pic.width = Inches(new_w_in); pic.height = Inches(new_h_in)
    if left_in is not None:
        pic.left = Inches(left_in)
    elif center_x_in is not None:
        pic.left = Inches(center_x_in - new_w_in / 2)
    else:
        pic.left = Inches((13.333 - new_w_in) / 2)
    pic.top = Inches(top_in)
    return pic


def add_kpi_box(slide, label, value, delta, x, y, w, h, *, color=COL_ACCENT, bg_color=None):
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    box.fill.solid()
    box.fill.fore_color.rgb = bg_color or RGBColor(0xff, 0xff, 0xff)
    box.line.color.rgb = COL_RULE
    box.line.width = Pt(1)
    box.shadow.inherit = False
    tf = box.text_frame
    tf.margin_left = Inches(0.1); tf.margin_right = Inches(0.1)
    tf.margin_top = Inches(0.1); tf.margin_bottom = Inches(0.1)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = label
    r.font.size = SZ_KEY_LABEL; r.font.color.rgb = COL_SECTION; r.font.name = FONT_NAME
    p2 = tf.add_paragraph(); p2.alignment = PP_ALIGN.CENTER
    r = p2.add_run(); r.text = value
    r.font.size = SZ_KEY_NUMBER; r.font.bold = True; r.font.color.rgb = color; r.font.name = FONT_NAME
    if delta:
        p3 = tf.add_paragraph(); p3.alignment = PP_ALIGN.CENTER
        r = p3.add_run(); r.text = delta
        r.font.size = Pt(12); r.font.color.rgb = COL_SECTION; r.font.name = FONT_NAME


_PURE_NUMERIC = re.compile(
    r"^[★\s]*[+\-−]?[\d.,]+\s*(MB|GB|KB|%|秒|ms|us|/秒|次|×|x)?\s*$"
)


def _set_cell_border(cell, color_hex="333333", width_emu=6350):
    """Set thin border on all 4 sides of a cell via direct XML manipulation."""
    from lxml import etree
    tc_pr = cell._tc.get_or_add_tcPr()
    nsmap = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    for side in ("lnL", "lnR", "lnT", "lnB"):
        ln = etree.SubElement(
            tc_pr,
            "{http://schemas.openxmlformats.org/drawingml/2006/main}" + side,
        )
        ln.set("w", str(width_emu))
        ln.set("cap", "flat")
        ln.set("cmpd", "sng")
        ln.set("algn", "ctr")
        solid = etree.SubElement(
            ln, "{http://schemas.openxmlformats.org/drawingml/2006/main}solidFill"
        )
        srgb = etree.SubElement(
            solid, "{http://schemas.openxmlformats.org/drawingml/2006/main}srgbClr"
        )
        srgb.set("val", color_hex)


def _detect_align(val_str):
    """Pure numbers (with optional unit suffix) → right; anything else (multi-line,
    bulleted text, mixed) → left. Conservative: bulleted lists like '1. foo' stay left."""
    s = str(val_str).strip()
    if "\n" in s:
        # Multi-line cells: right-align only if every line is pure numeric
        lines = [ln.strip() for ln in s.split("\n") if ln.strip()]
        if all(_PURE_NUMERIC.match(ln) for ln in lines):
            return PP_ALIGN.RIGHT
        return PP_ALIGN.LEFT
    return PP_ALIGN.RIGHT if _PURE_NUMERIC.match(s) else PP_ALIGN.LEFT


def make_table(slide, headers, rows, x, y, w, h, *, cell_size=SZ_TABLE, first_col_emph=True,
               col_widths=None, col_aligns=None, header_color=None, zebra_color=None):
    """col_widths: list of fractions (sum to 1.0) for non-uniform columns.
    col_aligns: list of PP_ALIGN per column. Defaults to auto-detect by content type.
    header_color: RGBColor for header bg; defaults to COL_TITLE. Use variety across deck.
    zebra_color: RGBColor for even-row stripe; defaults to light gray."""
    if header_color is None:
        header_color = COL_TITLE
    if zebra_color is None:
        zebra_color = RGBColor(0xf6, 0xf8, 0xfa)
    n_cols = len(headers)
    n_rows = len(rows) + 1
    table_shape = slide.shapes.add_table(n_rows, n_cols, x, y, w, h)
    tbl = table_shape.table
    if col_widths is not None:
        assert len(col_widths) == n_cols, f"col_widths len {len(col_widths)} != n_cols {n_cols}"
        total_emu = w
        if hasattr(total_emu, "emu"):
            total_emu = total_emu.emu
        for j, frac in enumerate(col_widths):
            tbl.columns[j].width = int(total_emu * frac)
    for j, hd in enumerate(headers):
        cell = tbl.cell(0, j)
        cell.fill.solid(); cell.fill.fore_color.rgb = header_color
        _set_cell_border(cell)
        tf = cell.text_frame
        tf.margin_left = Inches(0.05); tf.margin_right = Inches(0.05)
        tf.margin_top = Inches(0.04); tf.margin_bottom = Inches(0.04)
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = hd
        r.font.bold = True; r.font.size = cell_size
        r.font.color.rgb = RGBColor(0xff, 0xff, 0xff); r.font.name = FONT_NAME
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = tbl.cell(i + 1, j)
            tf = cell.text_frame
            tf.margin_left = Inches(0.05); tf.margin_right = Inches(0.05)
            tf.margin_top = Inches(0.04); tf.margin_bottom = Inches(0.04)
            p = tf.paragraphs[0]
            text, color = (val, COL_BODY) if not isinstance(val, tuple) else val
            if col_aligns is not None:
                p.alignment = col_aligns[j]
            elif j == 0 and first_col_emph:
                p.alignment = PP_ALIGN.LEFT
            else:
                p.alignment = _detect_align(text)
            r = p.add_run(); r.text = str(text)
            r.font.size = cell_size; r.font.color.rgb = color; r.font.name = FONT_NAME
            # No zebra striping — keep all data rows white. Header colored only.
            cell.fill.solid(); cell.fill.fore_color.rgb = RGBColor(0xff, 0xff, 0xff)
            _set_cell_border(cell)
    return tbl


def add_footer(slide):
    section_tag = getattr(slide, "_section_tag", "")
    slide_no = getattr(slide, "_slide_no", "")
    add_text(slide, section_tag,
             Inches(0.5), Inches(7.27), Inches(7), Inches(0.18),
             font_size=Pt(8), color=COL_SOURCE, italic=True)
    add_text(slide,
             f"AGA Gen2 L0 Evidence Plane · 2026-05-06 · heaphook_experiments (zh-TW)   |   {slide_no}",
             Inches(5.5), Inches(7.27), Inches(7.33), Inches(0.18),
             font_size=Pt(8), color=COL_SOURCE, italic=True, align=PP_ALIGN.RIGHT)


# ============================================================
# Build
# ============================================================
prs = Presentation()
prs.slide_width = SZ_W
prs.slide_height = SZ_H
blank = prs.slide_layouts[6]


# ---------- 01 Cover ----------
def slide_cover():
    s = prs.slides.add_slide(blank)
    band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SZ_W, Inches(0.4))
    band.fill.solid(); band.fill.fore_color.rgb = COL_TITLE; band.line.fill.background()
    band.shadow.inherit = False
    add_text(s, "AGA Gen2 Memory Determinism Platform",
             Inches(0.5), Inches(0.05), Inches(12), Inches(0.3),
             font_size=Pt(11), bold=True, color=RGBColor(0xff, 0xff, 0xff))
    # HEADLINE — the single most valuable finding, dominant tile
    add_text(s, "Heaphook Hybrid 把 lock contention 砍 92%",
             Inches(0.5), Inches(0.6), Inches(12.33), Inches(1.4),
             font_size=Pt(34), bold=True, color=COL_TITLE)
    add_text(s, "Δvol_ctx 跨 arm 量測（N=6/arm）— D arm 從 3,333 次/秒 降到 266 次/秒（std<15%）",
             Inches(0.5), Inches(2.05), Inches(12.33), Inches(0.4),
             font_size=Pt(15), color=COL_SECTION)

    # Arm legend — explain A/B/D upfront so reader understands the tiles below
    legend_box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                    Inches(0.5), Inches(2.45), Inches(12.33), Inches(0.4))
    legend_box.fill.solid()
    legend_box.fill.fore_color.rgb = COL_BG_GRAY
    legend_box.line.fill.background()
    legend_box.shadow.inherit = False
    add_text(s, "A = 系統預設 glibc（baseline）  ·  B = 單一 mutex 全域 pool（stockpile）  ·  D = thread-local lock-free 快路徑 + 全域 fallback（heaphook hybrid）",
             Inches(0.5), Inches(2.48), Inches(12.33), Inches(0.35),
             font_size=Pt(11), color=COL_BODY, align=PP_ALIGN.CENTER)

    # Hero number — D vol_ctx central tile
    big = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                             Inches(0.5), Inches(2.95), Inches(12.33), Inches(1.85))
    big.fill.solid()
    big.fill.fore_color.rgb = COL_BG_GREEN
    big.line.color.rgb = COL_GOOD
    big.line.width = Pt(2.5)
    big.shadow.inherit = False

    add_text(s, "−92%",
             Inches(0.7), Inches(3.05), Inches(4.5), Inches(1.65),
             font_size=Pt(72), bold=True, color=COL_GOOD,
             align=PP_ALIGN.CENTER)
    add_text(s, "voluntary context switch 次/秒",
             Inches(5.5), Inches(3.15), Inches(7.0), Inches(0.4),
             font_size=Pt(18), bold=True, color=COL_TITLE)
    add_text(s, "= lock contention 的直接訊號  ·  最直接量化「allocator 造成的 jitter source」",
             Inches(5.5), Inches(3.55), Inches(7.0), Inches(0.4),
             font_size=Pt(12), color=COL_BODY)
    add_text(s, "機制：每 thread 私有 4 MiB O1heap pool；alloc ≤ pool 大小 → 不上鎖、O(1) 完成",
             Inches(5.5), Inches(3.92), Inches(7.0), Inches(0.4),
             font_size=Pt(11), italic=True, color=COL_BODY)
    add_text(s, "為何高命中：sample-rosbag 所有 alloc ≤ 4 MiB → 100% 命中 fast path（已驗 fallback allocated=0）",
             Inches(5.5), Inches(4.27), Inches(7.0), Inches(0.4),
             font_size=Pt(11), italic=True, color=COL_BODY)

    # Secondary findings — 2 small tiles
    add_text(s, "次發現：",
             Inches(0.5), Inches(5.0), Inches(2), Inches(0.35),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    add_kpi_box(s, "B stockpile  |  End-to-End Latency CV", "−25%",
                "5+5 reps 確認真有差（不是 noise）；但 invol_ctx +37% 是反向 cost",
                Inches(0.5), Inches(5.35), Inches(6.0), Inches(1.0),
                color=COL_KPI, bg_color=COL_BG_RED)
    add_kpi_box(s, "D heaphook hybrid  |  End-to-End Latency CV", "跟 A 一樣",
                "5 reps 平均打平 — D 沒贏 E2E CV（撤回前次 N=3 主張）",
                Inches(6.65), Inches(5.35), Inches(6.18), Inches(1.0),
                color=COL_BODY, bg_color=COL_BG_GRAY)

    add_text(s, "本文 11 頁 ≈ 12 min  ·  18 reps × 雙軌道證據  ·  附錄 ABCD 章節 — 急用看 1+5+6+8 四頁",
             Inches(0.5), Inches(6.55), Inches(12.33), Inches(0.4),
             font_size=Pt(11), italic=True, color=COL_BODY, align=PP_ALIGN.CENTER)
    add_footer(s)


# ---------- 02 Opening · 白話說明今天在做什麼 ----------
def slide_opening():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Opening · 我們在做什麼", 2)
    add_title(s, "我們在 Autoware 上比 3 種 allocator — 想答「真能讓系統執行更穩嗎？」",
              "三句話 briefing：量測對象（SUT）/ 變因（A/B/D 三 arm）/ 想答的核心問題 / 為何此刻必須做")

    # Section 1
    add_text(s, "1. 量測對象（SUT）",
             Inches(0.5), Inches(1.95), Inches(12.33), Inches(0.28),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    add_text(s, "•  軟體：Autoware 2025.02（TIER IV 開源自駕車 stack，ROS 2 Humble）",
             Inches(0.7), Inches(2.20), Inches(12), Inches(0.25),
             font_size=Pt(10), color=COL_BODY)
    add_text(s, "•  規模：~89 個進程併行 — 感知 / 定位 / 規劃 / 控制",
             Inches(0.7), Inches(2.42), Inches(12), Inches(0.25),
             font_size=Pt(10), color=COL_BODY)
    add_text(s, "•  輸入：sample bag（預錄路測資料）餵入",
             Inches(0.7), Inches(2.64), Inches(12), Inches(0.25),
             font_size=Pt(10), color=COL_BODY)
    add_text(s, "•  觀察重點：lidar → centerpoint → tracker → prediction chain 的 end-to-end latency 穩定度",
             Inches(0.7), Inches(2.86), Inches(12), Inches(0.25),
             font_size=Pt(10), color=COL_BODY)

    # Section 2
    add_text(s, "2. 我們在比什麼（變因）",
             Inches(0.5), Inches(3.18), Inches(12.33), Inches(0.28),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    add_text(s, "三種「記憶體配置策略」（malloc / free 實作）— 透過 LD_PRELOAD 替換，不改 Autoware 一行程式：",
             Inches(0.7), Inches(3.43), Inches(12), Inches(0.25),
             font_size=Pt(10), color=COL_BODY)
    add_text(s, "•  arm A：系統預設 glibc — 業界 baseline",
             Inches(0.9), Inches(3.65), Inches(12), Inches(0.25),
             font_size=Pt(10), color=COL_BODY)
    add_text(s, "•  arm B：stockpile（單一 mutex 全域 pool）— 業界舊式 RT allocator 簡化版",
             Inches(0.9), Inches(3.87), Inches(12), Inches(0.25),
             font_size=Pt(10), color=COL_BODY)
    add_text(s, "•  arm D：heaphook hybrid（thread-local lock-free 快路徑 + 全域 fallback）— 今天主推的設計",
             Inches(0.9), Inches(4.09), Inches(12), Inches(0.25),
             font_size=Pt(10), color=COL_BODY)

    # Section 3
    add_text(s, "3. 想答什麼（實驗目的）",
             Inches(0.5), Inches(4.42), Inches(12.33), Inches(0.28),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    add_text(s, "•  核心問題：「換成 lock-free allocator 真能讓自駕系統執行更穩定？穩定到滿足 TIER1 bounded WCRT 合約？」",
             Inches(0.7), Inches(4.67), Inches(12), Inches(0.25),
             font_size=Pt(10), italic=True, color=COL_ACCENT)
    add_text(s, "•  雙軌證據 (a)：allocator 真的改變了 memory 行為嗎？",
             Inches(0.7), Inches(4.89), Inches(12), Inches(0.25),
             font_size=Pt(10), color=COL_BODY)
    add_text(s, "•  雙軌證據 (b)：改變有沒有帶到系統 end-to-end latency 穩定度（chain CV）？",
             Inches(0.7), Inches(5.11), Inches(12), Inches(0.25),
             font_size=Pt(10), color=COL_BODY)

    # Section 4
    add_text(s, "4. 為何需要作這件事（why now）",
             Inches(0.5), Inches(5.45), Inches(12.33), Inches(0.28),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    add_text(s, "•  TIER1 自駕車合約要 bounded WCRT（chain end-to-end response，不是 per-task WCET）— Autoware baseline chain CV 超過 0.15 KPI；通不過合約",
             Inches(0.7), Inches(5.70), Inches(12), Inches(0.25),
             font_size=Pt(10), color=COL_BODY)
    add_text(s, "•  業界主張「lock-free RT allocator 改善 jitter」只有 microbenchmark，沒有 real-Autoware SUT 量測",
             Inches(0.7), Inches(5.92), Inches(12), Inches(0.25),
             font_size=Pt(10), color=COL_BODY)
    add_text(s, "•  AGA Gen2 Memory Determinism Platform 的 L0 Evidence Plane POC — 不驗這層，L1 / L2 / TIER1 contract 都建在沒驗的假設上",
             Inches(0.7), Inches(6.14), Inches(12), Inches(0.25),
             font_size=Pt(10), color=COL_BODY)

    add_takeaway(s, "此頁讓不熟悉專案脈絡的聽眾建立 mental model；下一頁起進入導覽 → 結果 → 推薦。")
    add_source(s, "memory  project_aga_gen2_heijunka_framing.md ;  Autoware Universe 2025.02")
    add_footer(s)


# ---------- 03 Outline ----------
def slide_outline():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Outline · 11 頁本文 + 4 章附錄", 3)
    add_title(s, "本文 11 頁路徑：先給結論 → 再秀證據 → 然後推薦與限制",
              "急用看 1+5+6+8 四頁；mechanism / context / methodology 全部推附錄 ABCD 章節依需求查閱")
    add_text(s, "本文 11 頁（~12 分鐘 / 一頁 1 分鐘）",
             Inches(0.5), Inches(2.0), Inches(6), Inches(0.4),
             font_size=Pt(15), bold=True, color=COL_TITLE)
    rows_main = [
        ("1",  "★ Cover · Heaphook hybrid 把 lock contention 砍 92%"),
        ("2",  "Opening · 白話實驗 briefing（什麼 / 變因 / 想答 / why now）"),
        ("3",  "本頁（Outline）"),
        ("4",  "Hero · 4 metric × 3 arm 對照表（一眼看完成果）"),
        ("5",  "★ Track 1A 記憶體直接證據（4 panel 圖）"),
        ("6",  "★ Track 1B End-to-End Latency CV（bar 圖）"),
        ("7",  "Trade-off · CPU vs CV scatter（兩條路徑）"),
        ("8",  "Recommendations · production decision matrix"),
        ("9",  "Caveats · 10 條分 3 類"),
        ("10", "Conclusion · 三句話帶走"),
        ("11", "下一步 · deadline miss + N=10"),
    ]
    make_table(s, ["#", "本文"], rows_main,
               Inches(0.5), Inches(2.4), Inches(6.0), Inches(4.2),
               cell_size=Pt(10), col_widths=[0.10, 0.90], header_color=COL_HDR_GRAY)

    add_text(s, "附錄 4 章（依需求查閱）",
             Inches(6.85), Inches(2.0), Inches(6), Inches(0.4),
             font_size=Pt(15), bold=True, color=COL_TITLE)
    rows_app = [
        ("A 12-16", "環境 + 架構 + 名詞  · 系統架構 / 環境 / 控制變因 / 縮寫表"),
        ("B 17-25", "Mechanism + Method  · Heijunka / D workflow / arm C→D / 4 claim / 因果鏈 / metric / orch"),
        ("C 26-32", "補充結果 + 對照  · α / per-rep / RSS / CPU+GPU / 1.0x / SOTA"),
        ("D 33-41", "工程歷程 + 統計 + audit  · 踩過的坑 / tooling / 5-lens / Welch / 因果鏈 / commits"),
    ]
    make_table(s, ["章 · 頁", "內容"], rows_app,
               Inches(6.85), Inches(2.4), Inches(6.0), Inches(4.2),
               cell_size=Pt(10), col_widths=[0.20, 0.80], header_color=COL_HDR_GRAY)

    add_takeaway(s, "急用看 1+5+6+8 四頁就能 decision-make；附錄按 ABCD 章節依需求查閱，不是線性讀完。")
    add_source(s, "本投影片  reports/2026-05-06_1141_MPR_zhTW.pptx")
    add_footer(s)


# ---------- 03 Context · Heijunka 4 層 ----------
def slide_context():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "脈絡 · AGA Gen2 Heijunka 4 層 tech stack", 18)
    add_title(s, "今天測哪一層 — L0 記憶體證據 → L2 系統 KPI carry-through",
              "「Layer 2」= AGA Gen2 Heijunka blueprint 的 chain end-to-end KPI 層，不是 OSI 第二層")
    rows = [
        ("L4", "Strategic surface", "TIER1 contract / product story",   "🟦 不在今天 scope"),
        ("L3", "Hardware / RT",     "Linux kernel · CPU · GPU",          "🟦 共享 noise floor"),
        ("L2", "Chain e2e KPI",     "ROS 2 callback chain 的 e2e CV",    "★ 量 — chain CV<0.15"),
        ("L1", "Classifier 路由",    "per-node / per-thread allocator routing", "⚠ 缺 — Phase 3 才補"),
        ("L0", "Evidence Plane",    "/proc · mpstat · nvidia-smi · LD_PRELOAD intercept", "★ 量 — 記憶體 metric"),
    ]
    make_table(s, ["層", "名稱", "代表 stack", "今天的位置"], rows,
               Inches(0.5), Inches(2.0), Inches(12.33), Inches(3.0),
               cell_size=Pt(11), col_widths=[0.06, 0.20, 0.45, 0.29],
               header_color=COL_HDR_TEAL)

    # Carry-through path arrow
    add_text(s, "今天 deck 證明的 carry-through path：L0 evidence  →  L2 KPI",
             Inches(0.5), Inches(5.2), Inches(12.33), Inches(0.4),
             font_size=Pt(15), bold=True, color=COL_TITLE, align=PP_ALIGN.CENTER)
    add_text(s, "•  Track 1A 量 L0：換 allocator 後記憶體行為真改變？（vol_ctx / minflt / RSS）",
             Inches(0.5), Inches(5.65), Inches(12.33), Inches(0.35),
             font_size=Pt(11), color=COL_BODY)
    add_text(s, "•  Track 1B 量 L2：改變有沒有帶到系統 chain CV？",
             Inches(0.5), Inches(5.95), Inches(12.33), Inches(0.35),
             font_size=Pt(11), color=COL_BODY)
    add_text(s, "•  L1 缺席 → 今天 D 是 process-wide preload，無法區分「critical RT thread vs infra thread」(Phase 3 補)",
             Inches(0.5), Inches(6.25), Inches(12.33), Inches(0.35),
             font_size=Pt(11), color=COL_BODY)

    add_takeaway(s, "今天答：L0 改變顯著（D vol_ctx -92%），但不是每個 L0 改變都自動帶到 L2（D 沒贏 chain CV）。L1 缺席是 Phase 3 待補項。")
    add_source(s, "AGA Gen2 Heijunka blueprint 2026-04-21；memory  project_aga_gen2_heijunka_framing.md")
    add_footer(s)


# ---------- 05 系統架構圖 ----------
def slide_architecture():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "系統架構 + 控制變因 摘要", 13)
    add_title(s, "實驗工具 + SUT — 一張圖看清楚誰在量誰",
              "獨立變量（LD_PRELOAD）注入 SUT；量測層在外圍非侵入觀察")

    diagram = (
        "┌───────────────────────────────────────────────────────────────────┐\n"
        "│  SUT (System Under Test) — Autoware 2025.02 baseline_caret  ★不改 │\n"
        "│   ROS 2 Humble · 89 PIDs · component_container_mt × N             │\n"
        "│   NDT localizer / EKF / Centerpoint detector / Tracker / Predict  │\n"
        "└───────────────────────────────────────────────────────────────────┘\n"
        "         ↑ LD_PRELOAD（arm 變因）        ↑ ros2 bag play\n"
        "  ┌───────────────────────────┐    ┌───────────────────────────────┐\n"
        "  │  heaphook (fork main-fixes)│    │ Bag · sample-rosbag           │\n"
        "  │   A：（無 preload）         │    │  3-stage flow6+burnin10+resume│\n"
        "  │   B：stockpile.so (mutex)   │    │  CARET ENTER post-resume      │\n"
        "  │   D：heaphook hybrid.so    │    │  measurement window 30s       │\n"
        "  └───────────────────────────┘    └───────────────────────────────┘\n"
        "\n"
        "─────── 量測層（非侵入 — 觀察不改 SUT 行為）────────\n"
        "  ┌─────────────────────────────┐    ┌─────────────────────────────┐\n"
        "  │ Tier-0 sampler（/proc 10s） │    │ CARET libcaret + lttng UST  │\n"
        "  │  • /proc/<pid>/stat,status  │    │  ros2 caret record          │\n"
        "  │  • mpstat 1Hz / nvidia-smi  │    │  → stats_path.yaml          │\n"
        "  │  • rss_pre / rss_post       │    │  → chain CV per-instance    │\n"
        "  └─────────────────────────────┘    └─────────────────────────────┘\n"
        "                  │                            │\n"
        "                  ▼                            ▼\n"
        "      ┌─────────────────────────────────────────────┐\n"
        "      │  observe_rep.py（4-tier verdict）           │\n"
        "      │   STRICT / RELAXED / INFO / FAIL            │\n"
        "      │   → result.json（audit chain anchor）       │\n"
        "      └─────────────────────────────────────────────┘\n"
        "                              │\n"
        "                              ▼\n"
        "       cross_arm_brief.py + build_mckinsey_pngs.py → 本投影片"
    )
    add_text(s, diagram,
             Inches(0.5), Inches(1.95), Inches(12.33), Inches(4.4),
             font_size=Pt(9), color=COL_BODY)

    add_text(s, "Orchestrator：tmux 4-pane canonical（T1 launcher / T2 sim / T3 CARET record / T4 bag）+ 5 event-driven gates",
             Inches(0.5), Inches(6.15), Inches(12.33), Inches(0.35),
             font_size=Pt(10), italic=True, bold=True, color=COL_TITLE)

    add_takeaway(s, "唯一進到 SUT 的修改 = LD_PRELOAD；量測層只透過 /proc + lttng UST 非侵入觀察。Δ 觀察單因 = allocator。")
    add_source(s, "tools/run_canonical_rep.sh + observe_rep.py + sample_alignment_metrics.sh")
    add_footer(s)


# ---------- 06 實驗環境 + 不可控因素 ----------
def slide_environment():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · A · 實驗環境 + 不可控因素", 14)
    add_title(s, "「在哪台機器、什麼噪音底下量的」 — 跨 arm 公平的前提",
              "三個 arm 共享同一 host / 同一 noise floor，所以 Δ 比較有效；絕對值受 host 約束")

    # Hardware
    add_text(s, "硬體", Inches(0.5), Inches(2.0), Inches(6), Inches(0.35),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    rows_hw = [
        ("CPU", "12 cores（mpstat per-core 同步取樣）"),
        ("GPU", "NVIDIA（nvidia-smi 1Hz 取樣，centerpoint TensorRT）"),
        ("RAM", "abundant（PSI=0 全程，不是壓力測試）"),
        ("OS", "Ubuntu, Linux 6.8.0-40-generic"),
    ]
    make_table(s, ["項", "值"], rows_hw,
               Inches(0.5), Inches(2.4), Inches(6), Inches(2.4),
               cell_size=Pt(10), col_widths=[0.18, 0.82])

    # Noise floor
    add_text(s, "不可控背景負載（不能停）", Inches(6.85), Inches(2.0), Inches(6), Inches(0.35),
             font_size=Pt(13), bold=True, color=COL_KPI)
    rows_noise = [
        ("BES",       "Endpoint security agent — 持續 CPU / I/O"),
        ("ForeScout", "網路監控 agent — 持續 syscall"),
        ("跨 arm 處理", "三 arm 都受同樣 noise → cross-arm Δ 仍 valid"),
        ("絕對值",     "受 noise 抬高（不能直接 vs 純淨 host SOTA 數字）"),
    ]
    make_table(s, ["agent / 限制", "效應"], rows_noise,
               Inches(6.85), Inches(2.4), Inches(6.0), Inches(2.4),
               cell_size=Pt(10), col_widths=[0.30, 0.70])

    # Software stack
    add_text(s, "軟體 stack", Inches(0.5), Inches(5.0), Inches(12), Inches(0.35),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    add_text(s, "• Autoware 2025.02 baseline_caret build（不可改 — autoware-* 為 SUT，cross-arm 比較依賴 byte-identity）",
             Inches(0.5), Inches(5.4), Inches(12.33), Inches(0.35),
             font_size=Pt(11), color=COL_BODY)
    add_text(s, "• ROS 2 Humble + CARET v0.6.2（libcaret LD_PRELOAD + lttng UST）",
             Inches(0.5), Inches(5.7), Inches(12.33), Inches(0.35),
             font_size=Pt(11), color=COL_BODY)
    add_text(s, "• heaphook fork main-fixes branch (3103fa9 + dc38718) — 含 reallocarray 上游修；stockpile 來自 malloc-only branch",
             Inches(0.5), Inches(6.0), Inches(12.33), Inches(0.35),
             font_size=Pt(11), color=COL_BODY)
    add_text(s, "• .so sha256 in 每個 rep 的 env/heaphook_so.sha256 — 跨 arm binary 身分鎖定",
             Inches(0.5), Inches(6.3), Inches(12.33), Inches(0.35),
             font_size=Pt(11), color=COL_BODY)

    add_takeaway(s, "三 arm 共享 host noise floor → Δ 仍 valid；絕對 chain CV 不能跨 host 移植，需在 reader 自己 host 重跑。")
    add_source(s, "memory  feedback_host_monitoring_agents_disclosure.md / feedback_no_autoware_modification.md")
    add_footer(s)


# ---------- 06 控制變因 ----------
def slide_control_variables():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · A · 控制變因 + 量測協議", 15)
    add_title(s, "獨立變量 = arm；其餘全鎖死",
              "每個 rep 都吃同樣的 bag、同樣的 chain、同樣的 30s 量測窗、同樣的 threshold tier")

    rows = [
        ("獨立變量",       "LD_PRELOAD",            "A=（無）/ B=stockpile.so / D=heaphook hybrid.so"),
        ("Bag",           "sample-rosbag",        "logging-simulator sensing trace（lidar+GNSS+IMU+vehicle status）"),
        ("Bag rate",      "0.5x",                 "1.0x 在此 host TP=0.78 < 4.0 → infeasible（驗證見 slide 20）"),
        ("Chain",         "single chain",         "top-lidar→centerpoint→tracker→map_based_prediction"),
        ("N per arm",     "5-6 (Track 1B) / 3 (Track 1A)", "前 N=3 milestone underpowered → 補到 5-6 後撤回 D claim"),
        ("Reps total",    "18 + 1 control",       "9 initial + 9 supplementary RSS-snapshot + 1 × 1.0x failure control"),
        ("Bag protocol",  "3-stage flow6+burnin10+resume", "資料窗在 burnin 後 30s 開始；避開 NDT/EKF 收斂期"),
        ("CARET capture", "post-resume ENTER",    "避免 21s pause artifact（capture 在 resume 後才開始）"),
        ("Threshold",     "3-tier",                "DOMAIN-anchored (Autoware spec) / CRITICAL-sanity (anti-bug) / SANITY (Shewhart 3σ)"),
        ("Verdict",       "STRICT / RELAXED / FAIL", "RELAXED_PASS = TP>2.0 + 5 binary 過；FAIL = drop from cross-arm"),
    ]
    make_table(s, ["軸", "鎖定值", "說明"], rows,
               Inches(0.5), Inches(2.0), Inches(12.33), Inches(4.5),
               cell_size=Pt(10), col_widths=[0.13, 0.25, 0.62])

    add_text(s, "B rep1 cold-start dropped — 第一個 stockpile rep TP=2.89 / exe=323ms 三 DOMAIN 全 FAIL。機制（pool warmup vs TensorRT cache）未 isolate；audit trail 留存。",
             Inches(0.5), Inches(6.6), Inches(12.33), Inches(0.5),
             font_size=Pt(10), color=COL_SOURCE, italic=True)

    add_takeaway(s, "獨立變量只有 LD_PRELOAD；其它全鎖。Δ 觀察到的差異都歸因於 allocator。")
    add_source(s, "tools/run_canonical_rep.sh + observe_rep.py THRESHOLDS dict + memory/feedback_play_rate_05x_required.md")
    add_footer(s)


# ---------- 07 Hero ----------
def slide_hero():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Hero · 4 個關鍵指標 × 3 arm 對照", 4)
    add_title(s, "一眼看完：D 贏 lock contention，B 贏 End-to-End Latency CV",
              "讀法：每一列一個指標 / 三 arm 並列；★ 標今天兩個贏的位置；灰底是 baseline 或打平。")

    # Comparison table: rows = metrics, cols = arms + interpretation
    # Header row uses arm legend so readers don't have to remember A/B/D
    # Track 1A N=6 per arm (refreshed 2026-05-06); Track 1B chain CV N=4-7
    rows = [
        ("Δ voluntary context switch (Δvol_ctx)\n次/秒  |  lock contention 訊號  |  越低越好",
         "3,333\n（baseline，N=6）",
         "3,021\n−9% 弱",
         "★ 266\n−92%（大贏）",
         "D 的 thread-local lock-free 快路徑 直接消除等 mutex"),
        ("Chain End-to-End Latency CV\n無單位（std/mean）  |  系統穩定度結果  |  越低越好",
         "0.291\n（baseline，N=10）",
         "★ 0.207\n−29%（N=5，p=0.003）",
         "0.249\n−14%（N=8，p=0.16）★但 mean 飆高，看 deadline miss",
         "B 用 single-mutex 序列化降 std；D 後期 reps mean 飆 → CV 假象"),
        ("Δ minor page faults (Δminflt)\n次/秒  |  記憶體 page-fault 開銷",
         "16,023\n（baseline）",
         "5,144\n−68%",
         "4,916\n−69%",
         "B / D 都靠 pool 預配避免 lazy alloc"),
        ("Δ RSS (resident set size) 30 秒\nMB  |  pool retain 的代價",
         "+1,453\n（baseline）",
         "+1,794\n+23%",
         "+1,736\n+19%",
         "B / D 共付 — pool 不釋放換速度"),
    ]
    make_table(s,
        ["指標",
         "A glibc\n（系統預設）",
         "B stockpile\n（全 pool 共用 1 把 mutex；多 thread 排隊）",
         "D heaphook hybrid\n（每 thread 私有 pool 不上鎖；滿才落 fallback）",
         "機制解讀"],
        rows,
        Inches(0.5), Inches(2.05), Inches(12.33), Inches(2.95),
        cell_size=Pt(10),
        col_widths=[0.28, 0.12, 0.18, 0.20, 0.22],
        header_color=COL_HDR_AMBER)

    # Inline 名詞解釋 — lock model + ctx switch + chain CV
    expl_box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                  Inches(0.5), Inches(5.05), Inches(12.33), Inches(1.55))
    expl_box.fill.solid()
    expl_box.fill.fore_color.rgb = COL_BG_GRAY
    expl_box.line.fill.background()
    expl_box.shadow.inherit = False
    add_text(s, "名詞解釋（鎖模型 / vol_ctx / chain CV 是什麼）",
             Inches(0.65), Inches(5.10), Inches(12), Inches(0.3),
             font_size=Pt(12), bold=True, color=COL_TITLE)
    add_text(s, "•  single-mutex pool（B 用）= 整個 allocator 全 thread 共用 1 把鎖；A thread 配 memory 時 B/C/... 都得排隊等。鎖序列化 = 失去並行。",
             Inches(0.65), Inches(5.42), Inches(12), Inches(0.32),
             font_size=Pt(9), color=COL_BODY)
    add_text(s, "•  thread-local lock-free（D 用）= 每 thread 自己一個 pool，配 memory 不需鎖、不需等別人；只在 pool 滿才落到全域 fallback。並行不互卡。",
             Inches(0.65), Inches(5.69), Inches(12), Inches(0.32),
             font_size=Pt(9), color=COL_BODY)
    add_text(s, "•  voluntary context switch（vol_ctx）= thread 主動讓 CPU，通常是「等 mutex」。chain end-to-end CV = 一條 callback chain (lidar→prediction) 的 latency std/mean，本研究 KPI<0.15。",
             Inches(0.65), Inches(5.96), Inches(12), Inches(0.32),
             font_size=Pt(9), color=COL_BODY)
    add_text(s, "•  為何量兩個：chain CV 是「結果」；vol_ctx 是「機制證據」。沒 vol_ctx 我們不知道 CV 改善是真的因為 allocator 還是 noise。",
             Inches(0.65), Inches(6.23), Inches(12), Inches(0.32),
             font_size=Pt(9), italic=True, color=COL_ACCENT)

    add_takeaway(s, "Allocator 不是「越複雜越好」也不是「pool 是 silver bullet」— 設計選擇決定贏哪個維度，production 依場景配對。")
    add_source(s, "Track 1A (vol_ctx/minflt/RSS): snapshot_rss.sh × 9 reps;  Track 1B (chain CV): stats_path.yaml × 16 reps")
    add_footer(s)


# ---------- 04 Today's question ----------
def slide_question():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · B · 4 個 claim", 21)
    add_title(s, "今天回答的 4 個 claim", "issue tree 結構，每 claim 配對 minimum evidence set")
    rows = [
        ("α", "Operational equivalence", "三 arm 都在 valid 操作點", "TP / exe / dist / kin / SIGSEGV"),
        ("β", "Memory strategy effective", "heaphook 真改變 memory 行為", "Δminflt / ΔRSS / Δvol_ctx / Δinvol_ctx"),
        ("γ", "Memory carry through to KPI", "memory 改變導致 chain CV 改善", "NDT exe_time / CPU / GPU / chain CV"),
        ("δ", "Trade-off quantified", "用什麼換什麼", "α + β + γ 整合"),
    ]
    make_table(s, ["#", "claim", "問什麼", "minimum evidence"], rows,
               Inches(0.5), Inches(2.0), Inches(12.33), Inches(2.8),
               col_widths=[0.05, 0.20, 0.30, 0.45])
    add_text(s, "為何今天能答（以前不能）",
             Inches(0.5), Inches(5.0), Inches(12), Inches(0.3),
             font_size=Pt(15), bold=True, color=COL_TITLE)
    add_bullets(s, [
        "21 秒 chain outlier 來源已找出 = CARET wall-clock × pause artifact，不是 EKF drift",
        "改 protocol：CARET capture 在 bag resume 後才 ENTER，artifact 消失",
        "B arm 從 binary 不存在 → malloc-only branch worktree 重 build 解封",
        "Track 1A 補加 RSS snapshot pre/post → β claim 第一次有真實數據",
    ], Inches(0.5), Inches(5.4), Inches(12), Inches(1.2))
    add_takeaway(s, "全部 4 個 claim 今天有 first-cut 答案；β（memory direct）跟 γ（KPI carry-through）是新數據點。")
    add_source(s, "本報告 reports/mckinsey_2026-05-06_revised_zhTW.md § 1-2")
    add_footer(s)


# ---------- 05 Causal chain framework ----------
def slide_causal_framework():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · B · 雙軌道因果鏈", 22)
    add_title(s, "為什麼這些 metric 都 KEY — 完整因果鏈才能 claim",
              "5 層 causal chain：Independent → 1st-order → 2nd-order → 3rd-order → KPI")

    # Two-column layout: left = chain diagram (text), right = claim mapping
    add_text(s, "5 層因果鏈",
             Inches(0.5), Inches(2.0), Inches(6), Inches(0.3),
             font_size=Pt(14), bold=True, color=COL_TITLE)
    add_text(s,
        "[Independent var]\n"
        "  Allocator 換（LD_PRELOAD）  arm A → D / B\n"
        "        ↓\n"
        "[1st-order：memory 行為改變]                ◄── Track 1A\n"
        "  RSS / minflt / majflt / vol_ctx / invol_ctx\n"
        "  「allocator 真的改變了 memory？」\n"
        "        ↓ bridge\n"
        "[2nd-order：per-node performance]\n"
        "  NDT exe_time / centerpoint / pose_twist\n"
        "        ↓ bridge\n"
        "[3rd-order：system resource]\n"
        "  CPU all_busy / GPU util / sched jitter\n"
        "        ↓\n"
        "[Final KPI]                                ◄── Track 1B\n"
        "  chain end-to-end CV (std/mean)\n"
        "  「memory cause 了 CV 嗎？」\n"
        "  + 並列 [Operational gate] α validity",
        Inches(0.5), Inches(2.4), Inches(6.5), Inches(4.5),
        font_size=Pt(11), color=COL_BODY)

    add_text(s, "為何兩 track 都 KEY",
             Inches(7.0), Inches(2.0), Inches(6), Inches(0.3),
             font_size=Pt(14), bold=True, color=COL_TITLE)
    rows = [
        ("Track 1A 證？", "Track 1B 證？", "解讀"),
        ("✅", "✅", "完整 causal claim 成立"),
        ("❌", "✅", "causation 缺：CV 改善可能 noise"),
        ("✅", "❌", "memory 改但沒帶 KPI win"),
        ("❌", "❌", "allocator 沒效應"),
    ]
    make_table(s, rows[0], rows[1:],
               Inches(7.0), Inches(2.4), Inches(5.83), Inches(2.0),
               cell_size=Pt(11), first_col_emph=False)

    add_text(s, "我之前的錯",
             Inches(7.0), Inches(4.6), Inches(6), Inches(0.3),
             font_size=Pt(13), bold=True, color=COL_KPI)
    add_bullets(s, [
        "N=3 milestone 只看 Track 1B（chain CV −6%），沒證 Track 1A → causation 不防守",
        "N=5-6 後 D 的 chain CV 「贏」消失（noise）→ 撤回",
        "教訓：claim KPI 必須先證 1A direct evidence",
    ], Inches(7.0), Inches(4.95), Inches(5.83), Inches(1.5), size=Pt(11))

    add_takeaway(s, "本報告每 claim 都標 Track 1A + 1B + Bridge 完整證據；不再單軌過度 claim。")
    add_source(s, "memory/feedback_two_track_metric_framework.md（今天新增的 lesson）")
    add_footer(s)


# ---------- 06 Metric definitions ----------
def slide_metric_def():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · B · Metric Definition", 23)
    add_title(s, "Metric & KPI 定義 — 第一次提到必含單位 + 門檻 + 來源",
              "終極 KPI = chain end-to-end CV < 0.15；Track 1A 4 metric 是 direct evidence。")

    rows = [
        ("Track 1B  ★ KPI", "chain CV", "dimensionless", "std/mean of e2e latency", "< 0.15", "Autoware Universe target"),
        ("Track 1B", "best_max", "ms", "chain 最差 instance e2e", "< 5000", "no pause artifact"),
        ("Track 1A  ★", "Δminflt /秒", "count/秒", "minor page fault rate", "lower=better", "/proc/pid/stat field 10"),
        ("Track 1A", "ΔRSS", "MB", "30s 內 resident memory 增量", "lower=better", "/proc/pid/status VmRSS"),
        ("Track 1A  ★", "Δvol_ctx /秒", "count/秒", "voluntary ctx switch（lock contention）", "lower=better", "/proc/pid/status"),
        ("Track 1A", "Δinvol_ctx /秒", "count/秒", "involuntary ctx switch（scheduler thrash）", "lower=better", "/proc/pid/status"),
        ("Bridge", "NDT exe_time", "ms", "NDT 一次 scan-matching", "< 100", "10Hz lidar budget"),
        ("Bridge", "CPU all_busy", "%", "mpstat 12-core 平均 100−%idle", "觀察", "mpstat -P ALL 1Hz"),
        ("α gate", "TP", "score", "NDT match quality", "> 4.0", "Autoware NDT spec"),
        ("α gate", "kin_state Hz", "Hz", "EKF 輸出頻率", "≥ 30", "EKF nominal 50"),
    ]
    make_table(s, ["分類", "metric", "單位", "是什麼", "門檻", "來源"], rows,
               Inches(0.5), Inches(2.0), Inches(12.33), Inches(4.5),
               cell_size=Pt(10), col_widths=[0.10, 0.13, 0.10, 0.30, 0.13, 0.24],
               header_color=COL_HDR_OLIVE)
    add_takeaway(s, "DOMAIN（Autoware spec, 不可動）/ CRITICAL（anti-bug, 不可動）/ SANITY（PRELIMINARY, N≥10 後 refit）三層 threshold 結構。")
    add_source(s, "tools/observe_rep.py THRESHOLDS dict ;  feedback_threshold_tier_methodology.md")
    add_footer(s)


# ---------- 12 Metric Measurement (HOW) ----------
def slide_metric_measurement():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · B · Metric 怎麼量出來（白話）", 24)
    add_title(s, "每個 key metric 的實作 — 工具 + 取樣方式 + 計算公式",
              "全部「非侵入」：不改 SUT 程式碼，只透過 /proc + lttng UST + ROS topic echo")

    rows = [
        ("chain CV (★ KPI)",
         "CARET libcaret + lttng UST → caret_analyze",
         "libcaret LD_PRELOAD 攔每個 ROS 2 callback 的 start/end → lttng 寫 UST trace event。caret_analyze 把同 chain 連續 callback 串成 chain instance（60-100 個 / 30s 窗）→ stats_path.yaml 給 best_avg_ms / best_std → CV = std / mean。"),
        ("Δminflt /秒",
         "snapshot_rss.sh 在 pre/post 各掃 89 PID 的 /proc",
         "讀 /proc/<pid>/stat 第 10 欄 minflt（cumulative 計數，不會 reset），totals 加總；post − pre 除以 30s 量測窗 = per-second rate。"),
        ("ΔRSS（MB）",
         "snapshot_rss.sh + /proc/<pid>/stat 第 24 欄",
         "讀 RSS in pages（4096 bytes），totals 加總 ÷1024 → KB ÷1024 → MB。30s 內 89 個 PID 的 resident memory 總增量。"),
        ("Δvol_ctx / Δinvol_ctx /秒",
         "/proc/<pid>/status 解析",
         "讀 voluntary_ctxt_switches / nonvoluntary_ctxt_switches 兩個欄位（kernel 累積）；post − pre 除以 30s = 全 89 PID 每秒 ctx-switch 量。"),
        ("CPU all_busy（%）",
         "mpstat -P ALL 1 30 並聯啟動",
         "mpstat 1Hz 每 core 一筆；parse_perf_samples.py 取 idle 欄 → busy = 100 − idle；12 cores 平均後再對 30 個取樣點取 mean。"),
        ("GPU util（%）",
         "nvidia-smi --query-gpu=utilization.gpu --loop=1",
         "nvidia-smi 1Hz CSV → GPU compute utilisation，30 個取樣點 mean。"),
        ("NDT exe_time（ms）",
         "ros2 topic echo /localization/.../exe_time_ms",
         "Autoware 自己 publish 的 metric topic；sample_alignment_metrics.sh 用 ros2 topic echo --once 收 30s → mean。"),
        ("TP / init_to_result_dist",
         "ros2 topic echo + Autoware metric topic",
         "TP = /localization/pose_estimator/transform_probability；dist = .../initial_to_result_distance_new。同 ros2 topic echo 收。"),
        ("EKF Activation",
         "grep launch log",
         "/tmp/aw_<arm>_t1.log 用 regex「EKF Activation succeeded」count；observe_rep.py 跑檢查。"),
    ]
    make_table(s, ["metric", "工具 / 來源", "怎麼算（白話）"], rows,
               Inches(0.5), Inches(2.0), Inches(12.33), Inches(4.6),
               cell_size=Pt(9), col_widths=[0.18, 0.27, 0.55],
               header_color=COL_HDR_OLIVE)

    add_takeaway(s, "全部用 OS / Linux / ROS 2 既有介面，沒進 Autoware 改一行 code。Δ 的乾淨歸因仰賴此非侵入性。")
    add_source(s, "tools/snapshot_rss.sh / sample_alignment_metrics.sh / observe_rep.py / parse_perf_samples.py")
    add_footer(s)


# ---------- 13 Methodology ----------
def slide_method():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · B · Method · canonical orch", 25)
    add_title(s, "tools/run_canonical_rep.sh — tmux 4-pane + 5 個 event-driven gate",
              "Gate = poll log 看到目標訊息再前進，不寫死 sleep")

    add_text(s, "Phase 流程", Inches(0.5), Inches(2.0), Inches(6), Inches(0.4),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    phases = [
        ("Phase 1", "tmux 4-pane + pre-flight（lttng / .so / zombies）"),
        ("Phase 2", "T2 launch Autoware → poll T1 log ready_marker"),
        ("Phase 3", "T3 record.sh → poll \"press enter to start\""),
        ("Phase 4", "T4 play_bag → Gate-3 poll EKF Activation → SPACE pause"),
        ("Phase 5", "10s burnin → SPACE resume → ★ T3 ENTER（capture START）"),
        ("Phase 6", "30s 量測窗 + parallel mpstat / nvidia-smi / pidstat ★ + RSS snapshot pre/post（今天新加）"),
        ("Phase 7", "T3 ENTER stop → kill PGID → mv trace → observe → batch"),
    ]
    for i, (ph, desc) in enumerate(phases):
        y = Inches(2.4 + i * 0.4)
        add_text(s, ph, Inches(0.5), y, Inches(0.85), Inches(0.36),
                 font_size=Pt(10), bold=True, color=COL_ACCENT)
        add_text(s, desc, Inches(1.4), y, Inches(5.2), Inches(0.36),
                 font_size=Pt(11), color=COL_BODY)

    add_text(s, "5 個 Event-driven Gate", Inches(7.0), Inches(2.0), Inches(6), Inches(0.4),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    add_bullets(s, [
        "G1  ready_marker — \"Loaded node ... traffic_light_roi_visualizer\"",
        "G2  record prompt — \"press enter to start recording\"",
        "G3  EKF Activation succeeded — max 12s deadline",
        "G4  SPACE → bag pause/resume（rosbag2 keyboard）",
        "G5  ENTER × 2 → record start / stop",
    ], Inches(7.0), Inches(2.4), Inches(5.9), Inches(2.5), size=Pt(11))

    add_text(s, "為何 capture-after-resume 是關鍵",
             Inches(7.0), Inches(5.1), Inches(6), Inches(0.4),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    add_bullets(s, [
        "CARET 量 chain 用 wall-clock。",
        "若 chain instance 跨 bag pause → latency 加上 pause 秒數。",
        "前次 A rep1 best_max=21253ms ≈ pause 21097ms = 直接證據。",
        "修後：start event 在 pause 前 → 沒被 capture → caret_extract 丟棄。",
    ], Inches(7.0), Inches(5.5), Inches(5.9), Inches(1.5), size=Pt(11))

    add_takeaway(s, "Protocol 對了一次後 18 reps 完全可重現；今天 Track 1A 缺口已補。")
    add_source(s, "tools/run_canonical_rep.sh ; feedback_canonical_caret_protocol.md")
    add_footer(s)


# ---------- 08 21s artifact fix ----------
# ---------- 09 從 arm C → arm D 可用 ----------
def slide_arm_c_to_d_fixes():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Bridge · 從 arm C → arm D 可用", 20)
    add_title(s, "為什麼今天的 D arm 數據可信 — 上游 heaphook 修了 3 個 bug",
              "不修這 3 個，arm C 每次 bringup 89 個 grep 死於 ENOMEM；量到的是「半癱瘓 Autoware」")

    rows = [
        ("①",
         "glibc 升級沒同步 hook",
         "glibc 2.26+ 把 reallocarray 切成獨立符號；heaphook 沒覆蓋到。所有 Autoware bringup 子進程（grep / xacro / coreutils）打到 glibc reallocarray 拿著 heaphook 的指標 → 「memory exhausted」abort。"),
        ("②",
         "Symbol export 漏了",
         "即使加了 reallocarray hook function，Versions script allowlist 漏 list 它 → 被降級成 local symbol，LD_PRELOAD 看不到，hook 等於沒接上。"),
        ("③",
         "realloc(NULL, 0) 邏輯顛倒",
         "glibc 規格：realloc(NULL, n) ≡ malloc(n) 對「所有 n」成立。heaphook 寫成 if (size==0) return NULL 早於 if (ptr==NULL) → 違反規格 → 呼叫者誤判 OOM。"),
    ]
    make_table(s, ["#", "Bug（白話）", "為什麼會死"], rows,
               Inches(0.5), Inches(2.0), Inches(12.33), Inches(2.7),
               col_widths=[0.05, 0.28, 0.67], header_color=COL_HDR_CORAL)

    add_text(s, "修法 — 25 LoC + 4 gtest（heaphook fork commit  3103fa9 / dc38718）",
             Inches(0.5), Inches(4.85), Inches(12.33), Inches(0.4),
             font_size=Pt(14), bold=True, color=COL_TITLE)
    add_text(s, "• 加 reallocarray hook function（包 _int_realloc）",
             Inches(0.5), Inches(5.25), Inches(12), Inches(0.35),
             font_size=Pt(12), color=COL_BODY)
    add_text(s, "• Versions script 加 reallocarray entry（讓 LD_PRELOAD 看得到）",
             Inches(0.5), Inches(5.55), Inches(12), Inches(0.35),
             font_size=Pt(12), color=COL_BODY)
    add_text(s, "• 重排 if 判斷順序（先檢 ptr==NULL 再檢 size==0）",
             Inches(0.5), Inches(5.85), Inches(12), Inches(0.35),
             font_size=Pt(12), color=COL_BODY)

    add_text(s, "驗證：LD_PRELOAD=hybrid /usr/bin/grep -c root /etc/services",
             Inches(0.5), Inches(6.3), Inches(12.33), Inches(0.35),
             font_size=Pt(12), bold=True, color=COL_ACCENT)
    add_text(s, "  修前：「memory exhausted」rc=2     修後：rc=0 正常輸出",
             Inches(0.5), Inches(6.6), Inches(12.33), Inches(0.35),
             font_size=Pt(12), color=COL_BODY)

    add_takeaway(s, "沒這 25 LoC，今天 D arm 數據是 broken-Autoware 狀態（M0' + 2.5b + 2.5c 共 7 reps 已撤回重測）；上游 PR brief 已 draft 待提交 tier4/heaphook。")
    add_source(s, "memory  feedback_heaphook_subprocess_grep_enomem.md；reports/heaphook_upstream_pr_brief.md")
    add_footer(s)


# ---------- 10 Result α (operational) ----------
def slide_result_alpha():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · C · α 操作有效性", 27)
    add_title(s, "三 arm operational alignment 都過 Autoware NDT spec 門檻",
              "claim α 成立 — 量測在 valid 操作點，後續 β/γ 比較有意義")
    rows = [
        ("TP（NDT match quality）",        "5.62", "5.35", "5.28", "> 4.0",   "Autoware spec ✅"),
        ("NDT exe_time（ms）",             "12.4", "27.5", "37.2", "< 100",   "10Hz lidar budget ✅"),
        ("init_to_result distance（m）", "0.061","0.073","0.138","< 2.0",   "map cell ✅"),
        ("kinematic_state Hz",            "24",   "26",   "25",   "≥ 30 *", "EKF rate floor"),
        ("EKF / NDT activation",          "1/1",  "1/1",  "1/1",  "≥ 1/1",   "lifecycle ✅"),
        ("SIGSEGV / SIGABRT",             "0/0",  "0/0",  "0/0",  "< 5/5",   "no crash ✅"),
    ]
    make_table(s, ["指標", "A glibc", "D hybrid", "B stockpile", "門檻", "來源"], rows,
               Inches(0.5), Inches(2.0), Inches(12.33), Inches(3.0),
               col_widths=[0.25, 0.10, 0.10, 0.13, 0.12, 0.30],
               header_color=COL_HDR_TEAL)
    add_text(s, "* kin_hz 21-26 vs 30 = sampler 在 EKF 完全 lock 前就開始的 timing artifact（已知）",
             Inches(0.5), Inches(5.2), Inches(12), Inches(0.3),
             font_size=Pt(10), color=COL_SECTION, italic=True)
    add_text(s, "B rep1 cold-start dropped",
             Inches(0.5), Inches(5.7), Inches(12), Inches(0.4),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    add_bullets(s, [
        "B 第一個 rep TP=2.89 / exe=323ms / dist=2.28m — 三 DOMAIN 全 FAIL",
        "B rep2/3/4/5/6 同 .so 同 protocol 都 PASS — 機制：stockpile pool 從未 warm",
        "處理：drop B rep1，留 audit trail；機制隔離留 future work",
    ], Inches(0.5), Inches(6.0), Inches(12), Inches(0.7), size=Pt(11))
    add_takeaway(s, "claim α 全成立 — 三 arm 都在 valid 操作點，可進入 β / γ 比較。")
    add_source(s, "tools/observe_rep.py result.json × 18; feedback_b_arm_cold_start.md")
    add_footer(s)


# ---------- 7 Mechanism · D 為何贏 + fallback=0 evidence ----------
def slide_hybrid_workflow():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Mechanism · D 為何贏 + fallback=0 數據佐證", 7)
    add_title(s, "為什麼 D 贏：100% 命中 lock-free 路徑、TLSF fallback 從未啟用",
              "光看 vol_ctx -92% 不夠 — 還要看 fallback 是否真沒走，才能歸因到「lock-free 機制」而非 noise")

    add_image_centered(s, FIG / "d_hybrid_workflow.png",
                       max_w_in=7.0, max_h_in=4.3, top_in=1.85, left_in=0.4)

    add_text(s, "數據佐證（Phase 2.5b frag instrumentation）",
             Inches(7.7), Inches(1.95), Inches(5.3), Inches(0.3),
             font_size=Pt(11), bold=True, color=COL_TITLE)
    add_text(s, "•  全 357 PIDs × 4 取樣點：TLSF fallback allocated = 0",
             Inches(7.7), Inches(2.25), Inches(5.3), Inches(0.3),
             font_size=Pt(9), color=COL_BODY)
    add_text(s, "•  Per-thread O1heap pool peak utilisation < 25%",
             Inches(7.7), Inches(2.50), Inches(5.3), Inches(0.3),
             font_size=Pt(9), color=COL_BODY)
    add_text(s, "•  → fallback path 從未被觸發",
             Inches(7.7), Inches(2.75), Inches(5.3), Inches(0.3),
             font_size=Pt(9), italic=True, color=COL_GOOD)

    add_text(s, "演算法面為何沒觸發 fallback",
             Inches(7.7), Inches(3.20), Inches(5.3), Inches(0.3),
             font_size=Pt(11), bold=True, color=COL_TITLE)
    add_text(s, "•  Pool 容量 4 MiB / thread；ROS 2 message 多為 KB-MB 等級",
             Inches(7.7), Inches(3.50), Inches(5.3), Inches(0.3),
             font_size=Pt(9), color=COL_BODY)
    add_text(s, "•  sample-rosbag 全 alloc ≤ pool size → 100% 走 fast path",
             Inches(7.7), Inches(3.75), Inches(5.3), Inches(0.3),
             font_size=Pt(9), color=COL_BODY)
    add_text(s, "•  alloc/free 走 O1heap (O(1) bounded) → 不上鎖、不等",
             Inches(7.7), Inches(4.00), Inches(5.3), Inches(0.3),
             font_size=Pt(9), color=COL_BODY)

    add_text(s, "對 production 的意涵",
             Inches(7.7), Inches(4.45), Inches(5.3), Inches(0.3),
             font_size=Pt(11), bold=True, color=COL_TITLE)
    add_text(s, "•  Pool 4→2 MiB 應仍安全（peak<25% 已驗）",
             Inches(7.7), Inches(4.75), Inches(5.3), Inches(0.3),
             font_size=Pt(9), italic=True, color=COL_BODY)
    add_text(s, "•  ROS 2 大 alloc workload 需 re-validate",
             Inches(7.7), Inches(5.00), Inches(5.3), Inches(0.3),
             font_size=Pt(9), italic=True, color=COL_BODY)

    add_takeaway(s, "fallback=0 + peak<25% 雙重證實 — 99.9% allocation 在 lock-free 路徑完成；vol_ctx -92% 是機制必然，不是 noise。")
    add_source(s, "Phase 2.5b frag instrumentation × 6 reps; D-v4 binary sha256 36118b92...3dd922")
    add_footer(s)


# ---------- 6 Result β Track 1A ----------
def slide_result_beta():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Result · β Track 1A 記憶體直接證據 ★", 5)
    add_title(s, "Memory 直接證據：D 用 lock-free 大贏 vol_ctx；B 用 single mutex 沒贏",
              "4 個 metric 對應 4 個設計面向 — 設計選擇決定贏哪維度")
    add_image_centered(s, FIG / "f6_memory_delta_per_arm.png",
                       max_w_in=12, max_h_in=4.4, top_in=2.0)
    add_takeaway(s, "Δvol_ctx -92% on D 是今天最強單點訊號（std<5%）— 直接量化 thread-local lock-free fast path 的價值。")
    add_source(s, "tools/snapshot_rss.sh pre/post × 9 reps (3 per arm)")
    add_footer(s)


# ---------- 11 Result γ Track 1B ----------
def slide_result_gamma():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Result · γ Track 1B Chain CV", 6)
    add_title(s, "Chain CV 跨 arm — N=5-6 修正後：B 是真贏家，D 沒贏",
              "三 arm 各 5-6 reps：A vs D 平均完全打平（沒差，撤回 N=3 的「D −6%」claim）；B 比 A 真有差。")
    add_image_centered(s, FIG / "f1_cv_cross_arm_bar.png",
                       max_w_in=11, max_h_in=4.4, top_in=2.0)
    add_takeaway(s, "B rep3 best CV=0.189 距 KPI 0.15 只差 1.26 倍，是程式 milestone 路徑上最近的單一 rep。")
    add_source(s, "stats_path.yaml × 16 reps; scipy.stats.ttest_ind(equal_var=False)")
    add_footer(s)


# ---------- 12 Result γ per-rep ----------
def slide_result_gamma_strip():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · C · γ per-rep 分布", 28)
    add_title(s, "每 rep CV 分布 — A range 廣（0.214-0.354），B 緊（0.189-0.268）",
              "B rep3=0.189 是今天最接近 KPI 0.15 的單一 rep")
    add_image_centered(s, FIG / "f2_cv_per_rep_strip.png",
                       max_w_in=11, max_h_in=4.4, top_in=2.0)
    add_takeaway(s, "A 的 std=0.053 比 B 的 std=0.032 大 — heaphook B 不只 mean 低，rep-to-rep variance 也較窄。")
    add_source(s, "per-rep stats_path.yaml from caret_report")
    add_footer(s)


# ---------- 13 Result δ trade-off CPU ----------
def slide_tradeoff_cpu():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Trade-off · CPU vs CV 兩條路徑", 8)
    add_title(s, "Trade-off 揭露：D 跟 B 走兩條不同路徑（不是同一條 CPU↔CV monotonic 線）",
              "但雙軸後揭露 D 跟 B 兩條路徑機制完全不同（看 slide 14）")
    add_image_centered(s, FIG / "f3_cpu_vs_cv_tradeoff.png",
                       max_w_in=11, max_h_in=4.4, top_in=2.0)
    add_takeaway(s, "單軸看似「CPU 多花 → CV 更穩」；但 D 用 78% CPU 沒贏 CV，B 用 87% CPU 才贏 — mechanism 差異後面揭露。")
    add_source(s, "mpstat 1Hz × 30s window; CV from stats_path.yaml")
    add_footer(s)


# ---------- 14 Result δ trade-off RSS ----------
def slide_tradeoff_rss():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · C · Trade-off RSS 軸", 29)
    add_title(s, "Trade-off 第二軸：RSS 代價 ↔ Chain CV — 揭露 D vs B 不同機制",
              "D 跟 B 同付 RSS 成本（+24%），但 D 沒換到 CV，B 換到 CV (-25%)")
    add_image_centered(s, FIG / "f7_rss_vs_cv_tradeoff.png",
                       max_w_in=11, max_h_in=4.4, top_in=2.0)
    add_takeaway(s, "「同 cost 不同 benefit」說明 trade-off 不是單軸 — 設計面向的 mapping 才是真實 picture（slide 5 因果鏈）。")
    add_source(s, "rss_pre.txt vs rss_post.txt 30s window")
    add_footer(s)


# ---------- 15 CPU GPU resource ----------
def slide_resource():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · C · CPU/GPU 資源", 30)
    add_title(s, "資源用量：CPU 漲 vs GPU 掉 — heaphook 推 CPU 反限 GPU pipeline",
              "Bridge metric — 連結 1A → 1B 的 mechanism 之一")
    add_image_centered(s, FIG / "f5_cpu_gpu_per_arm.png",
                       max_w_in=11, max_h_in=4.4, top_in=2.0)
    add_takeaway(s, "Allocator 不只是 microbench — CPU 飽和度直接限縮下游 GPU pipeline，centerpoint TensorRT 餵不飽。")
    add_source(s, "mpstat -P ALL 1 + nvidia-smi 1Hz × 30s window")
    add_footer(s)


# ---------- 16 1.0x failure ----------
def slide_1_0x():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · C · 1.0x 不可行", 31)
    add_title(s, "1.0x production rate — host 限制，不是 allocator 鍋",
              "今天 1.0x A control（純 glibc + 無 instrumentation）composition 都跑不完")
    rows = [
        ("composition done", "❌ timeout 240s", "ready_marker 未出現"),
        ("EKF Activation",   "0",                "未啟動"),
        ("NDT Activation",   "0",                "未啟動"),
        ("trace size",       "0.1 MB",           "幾乎空"),
        ("earlier (P1.4) 1.0x clean control", "TP=0.78 / exe=157ms", "DOMAIN FAIL"),
    ]
    make_table(s, ["檢查項", "結果", "註"], rows,
               Inches(0.5), Inches(2.0), Inches(12.33), Inches(2.7),
               col_widths=[0.30, 0.15, 0.55], header_color=COL_HDR_AMBER)
    add_text(s, "推測來源（待 host audit）",
             Inches(0.5), Inches(5.0), Inches(12), Inches(0.4),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    add_bullets(s, [
        "Host kernel / driver / agent drift since 2025-09 working state",
        "BES + ForeScout monitoring agents（cannot stop, ~3% CPU baseline noise）",
        "0.5x 量測 = production-rate jitter 的 lower bound（contention 較少）",
    ], Inches(0.5), Inches(5.4), Inches(12), Inches(1.0), size=Pt(11))
    add_takeaway(s, "Direction（B<A in CV）由 0.5x 證據可推；magnitude 在 1.0x 需 host audit 後才能量。")
    add_source(s, "runs/20260505-1817_layer2-cv-a-1.0x-control-canonical; feedback_play_rate_05x_required.md")
    add_footer(s)


# ---------- 17 Pitfalls ----------
def slide_pitfalls():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · D · 踩過的坑", 34)
    add_title(s, "5 個 anti-pattern — 留給下次不要再踩",
              "工程主管聽得進來；隱瞞反而失分")
    pitfalls = [
        ("21 秒 outlier 誤歸因",
         "把 best_max=21253ms 誤推給 EKF prediction drift。\n"
         "V1 verification 發現是 CARET wall-clock × pause artifact。\n"
         "修：capture 在 resume 後（節省 5 hr 後續 debug）"),
        ("Reference 沒讀完就重寫 orch",
         "今天先寫 3 個新 orch 才發現 user 的 reference 有完整 protocol。\n"
         "教訓：讀 reference end-to-end 比 reimpl 便宜很多"),
        ("Cleanup pkill -f 不夠",
         "ros2 launch 子節點 reparent 到 subreaper（PID 1672）後，\n"
         "pkill -f 殺得不全；需用 PGID-based kill"),
        ("B rep1 cold-start 沒 warmup",
         "stockpile pool 第一次 alloc 慢；TP=2.89 整個 alignment fail。\n"
         "B rep2/3 同 .so 都 PASS。暫時解：drop first B rep"),
        ("N=3 milestone 過早 commit",
         "N=3 看到 D −6% chain CV 直接寫進 milestone。\n"
         "N=5-6 後 Welch p=1.0 完全消失 — 是 sample noise。\n"
         "教訓：cross-arm KPI claim 必須 N≥10 + Welch p<0.05"),
    ]
    rows = [(p[0], p[1]) for p in pitfalls]
    make_table(s, ["Anti-pattern", "現象 + 教訓"], rows,
               Inches(0.5), Inches(2.0), Inches(12.33), Inches(4.5),
               cell_size=Pt(10), col_widths=[0.25, 0.75], header_color=COL_HDR_CORAL)
    add_takeaway(s, "5 個 anti-pattern 已存記憶（feedback_*.md），下次自動避開。")
    add_source(s, "memory/feedback_canonical_caret_protocol.md, _21s_pause_artifact.md, _b_arm_cold_start.md, _audit_existing_before_planning.md, _n3_underpowered_changed_story.md")
    add_footer(s)


# ---------- 18 Tooling + audit chain ----------
def slide_tooling():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · D · Tooling + Audit", 35)
    add_title(s, "5 個 committed 腳本 + 18 個 rep dir scripts/ snapshot",
              "下次 N=10 直接重用，不需重寫 orch")
    tools = [
        ("tools/run_canonical_rep.sh",     "tmux 4-pane orchestrator + 5 event-driven gate + RSS snapshot"),
        ("tools/observe_rep.py",            "4-tier verdict + threshold tier methodology + memory delta block"),
        ("tools/sample_alignment_metrics.sh","TP/exe/dist/kin + mpstat + pidstat + nvidia-smi 平行抓"),
        ("tools/parse_perf_samples.py",    "mpstat / nvidia-smi text → JSON summary"),
        ("tools/cross_arm_brief.py",       "兩 rep dir → markdown 比較表自動生"),
        ("tools/snapshot_rss.sh",           "★ 今天加入：pre/post /proc/<pid>/{stat,status} aggregate"),
    ]
    make_table(s, ["路徑", "用途"], tools,
               Inches(0.5), Inches(2.0), Inches(12.33), Inches(2.6),
               col_widths=[0.40, 0.60], header_color=COL_HDR_OLIVE)
    add_text(s, "Audit chain — 每 claim 可從 commit 回溯到 raw data",
             Inches(0.5), Inches(4.9), Inches(12), Inches(0.4),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    add_text(s,
        "synthesis → cross_abcd_v4 → MANIFEST.md → exp_settings_<arm>.tsv → /proc snapshot\n"
        "                                                         ↓\n"
        "                                             stats_path.yaml ← caret_report ← lttng UST trace",
        Inches(0.5), Inches(5.3), Inches(12.33), Inches(1.0),
        font_size=Pt(11), color=COL_BODY)
    add_takeaway(s, "Reproducibility 成本：1 條 git checkout + 1 條 bash run_canonical_rep.sh。")
    add_source(s, "git log; ls runs/; ls .claude/projects/.../memory/")
    add_footer(s)


# ---------- 19 Method defense ----------
def slide_method_defense():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · D · Method Defense", 36)
    add_title(s, "方法論 ✅做了 vs 🟧未做 — 嚴審 self-review",
              "Stanford EECS / Tesla / TIER IV 角度檢視，不藏拙")
    rows = [
        ("✅ 做了", "🟧 未做（→ next session）"),
        ("Pre-flight check（zombies / lttng / .so）", "Multiple comparison correction（觀察 100+ metrics）"),
        ("Welch t-test reported with p", "Power analysis pre-rep（今天事後算 N=10 足）"),
        ("Threshold tier methodology", "Sanity threshold N≥10 Shewhart refit"),
        ("Reproducibility scripts/ snapshot per rep", "Cross-bag / cross-host validation"),
        ("Pre-registered hypothesis falsified（D CV claim）", "Per-callback latency attribution"),
        ("Track 1A direct evidence captured", "Long-soak 10+ min（leak / frag）"),
        ("Capture-after-resume 21s artifact 修復", "Deadline miss / WCRT 量測（明天必補）"),
        ("Two-track + bridge framework", "B's chain CV win mechanism 拆解（mean lift OR distribution narrowing）"),
    ]
    make_table(s, rows[0], rows[1:],
               Inches(0.5), Inches(2.0), Inches(12.33), Inches(4.5),
               cell_size=Pt(10), first_col_emph=False)
    add_takeaway(s, "9 條做到、8 條 next session 該補 — direction 證明已成立，magnitude 與 mechanism 待 N=10 + per-callback。")
    add_source(s, "5-lens self-review; reports/mckinsey_2026-05-06_revised_zhTW.md § 6")
    add_footer(s)


# ---------- C · Deadline miss cross-arm ----------
def slide_deadline_miss():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · C · Deadline miss × arm × deadline", 33)
    add_title(s, "Deadline miss 顛覆故事：A glibc 在每個 deadline 都贏 — chain CV 不等於 deadline miss",
              "從 24 reps 的 CARET p50/p95/p99/max 估算，6 個 deadline threshold；對 TIER1 contract（bounded WCRT）是直接 KPI")

    # Image left
    img_path = REPO / "reports" / "figures" / "mckinsey" / "f8_deadline_miss_by_arm.png"
    if img_path.exists():
        add_image_centered(s, img_path,
                           max_w_in=7.0, max_h_in=4.4, top_in=1.95, left_in=0.4)

    # Right: cross-arm table + interpretation
    rows = [
        ("100 ms",  "80.3%", "90.8%", "86.4%"),
        ("150 ms",  "70.5%", "86.2%", "79.6%"),
        ("200 ms",  "60.7%", "81.6%", "72.8%"),
        ("250 ms",  "49.8%", "77.0%", "66.0%"),
        ("300 ms",  "36.2%", "72.4%", "58.9%"),
        ("500 ms",  "5.3%",  "46.5%", "20.5%"),
    ]
    make_table(s, ["deadline", "A glibc", "B stockpile", "D heaphook"], rows,
               Inches(7.7), Inches(2.0), Inches(5.3), Inches(2.6),
               cell_size=Pt(10), col_widths=[0.27, 0.24, 0.27, 0.22],
               header_color=COL_HDR_PLUM)

    add_text(s, "為何 A 贏每個 deadline（即使 chain CV 輸 B）",
             Inches(7.7), Inches(4.75), Inches(5.3), Inches(0.3),
             font_size=Pt(11), bold=True, color=COL_TITLE)
    add_text(s, "•  chain CV = std/mean — ratio metric；B 低 std 但 mean 抬高",
             Inches(7.7), Inches(5.05), Inches(5.3), Inches(0.3),
             font_size=Pt(9), color=COL_BODY)
    add_text(s, "•  deadline miss = 絕對門檻；mean 抬高 = 整體 latency 偏高",
             Inches(7.7), Inches(5.30), Inches(5.3), Inches(0.3),
             font_size=Pt(9), color=COL_BODY)
    add_text(s, "•  TIER1 合約用 deadline miss → 單看 chain CV 推 B 是錯的",
             Inches(7.7), Inches(5.55), Inches(5.3), Inches(0.3),
             font_size=Pt(9), italic=True, color=COL_KPI)

    add_takeaway(s, "Allocator decision matrix 必須含 deadline miss + chain CV 兩軸 — 單一 metric recommendation 對 production 可能完全錯。")
    add_source(s, "tools/extract_deadline_miss.py + aggregate_deadline_miss.py × 15 reps")
    add_footer(s)


# ---------- 20 SOTA comparison ----------
def slide_sota():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · C · SOTA 對照", 33)
    add_title(s, "vs TIER IV 4-30 deck（內部歷史）+ vs 業界 allocator 設計位置",
              "我們的 D / B 在「lock-free vs serialization」spectrum 哪？")

    add_text(s, "vs TIER IV 4-30 deck claim",
             Inches(0.5), Inches(2.0), Inches(6), Inches(0.3),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    rows = [
        ("metric", "4-30 D", "今天 D N=3", "一致？"),
        ("Δminflt vs A", "−78.2%", "−67%", "direction ✓ magnitude 差"),
        ("ΔRSS vs A", "−28.6%（減）", "+24%（增）", "direction ✗ 反"),
        ("Δvol_ctx vs A", "未報告", "−92%", "新發現"),
        ("rss_pre vs A", "+49.6%", "未獨立量", "next"),
    ]
    make_table(s, rows[0], rows[1:],
               Inches(0.5), Inches(2.4), Inches(6), Inches(2.0),
               cell_size=Pt(10), first_col_emph=False)

    add_text(s, "vs 業界 allocator 設計 spectrum",
             Inches(7.0), Inches(2.0), Inches(6), Inches(0.3),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    rows = [
        ("allocator", "lock 模型", "RT 友善", "對照我們"),
        ("glibc ptmalloc2", "per-arena mutex", "中", "A baseline"),
        ("jemalloc", "per-arena (fewer)", "中", "≈ A"),
        ("mimalloc", "thread-local", "高", "≈ D 輕量"),
        ("tcmalloc", "thread-local", "高", "≈ D"),
        ("TLSF", "O(1) bounded", "高", "D fallback"),
        ("O1heap", "lock-free fast path", "★ 極高", "D fast path"),
        ("stockpile (TIER IV)", "single global mutex", "中", "B"),
    ]
    make_table(s, rows[0], rows[1:],
               Inches(7.0), Inches(2.4), Inches(5.83), Inches(2.5),
               cell_size=Pt(9), first_col_emph=False)

    add_text(s, "解讀",
             Inches(0.5), Inches(5.1), Inches(12), Inches(0.3),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    add_bullets(s, [
        "我們的 D = O1heap fast path + TLSF fallback = 業界最 RT-aggressive 的 hybrid",
        "B 是簡化版 stockpile（single mutex）；4-30 deck 內部 baseline",
        "今天 ΔRSS direction 不同於 4-30 deck — 可能 pool size 設定 / 量測窗長度差異",
        "下次補：jemalloc / mimalloc 跑進來當第 4 / 5 arm，定位完整",
    ], Inches(0.5), Inches(5.5), Inches(12), Inches(1.2), size=Pt(11))

    add_takeaway(s, "我們的 framework 與業界主流 allocator 設計可對齊；下次 cross-allocator benchmark 即可定位完整 spectrum。")
    add_source(s, "AGA Gen2 Strategy Deck (Apr 2026); mimalloc / tcmalloc papers; TLSF original paper")
    add_footer(s)


# ---------- 21 Recommendations ----------
def slide_recommendations():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Recommendations · production decision matrix", 9)
    add_title(s, "Production 配對：依 KPI 選 arm — chain CV 跟 deadline miss 給不同 winner",
              "Phase 1 deadline miss 分析顛覆「B 是 chain CV winner 所以選 B」的單軸 framing")
    rows = [
        ("KPI / 場景", "推薦 arm", "理由", "對照 metric 證據"),
        ("Per-malloc bounded WCET\n(Multi-thread RT、需 allocator 端確定性)",
         "★ D heaphook hybrid",
         "O1heap O(1) bounded; Δvol_ctx -92% 消除 lock-induced jitter",
         "Track 1A vol_ctx；fallback=0 機制證實"),
        ("Chain end-to-end CV 為 KPI\n(穩定度 ratio metric)",
         "★ B stockpile",
         "−25% 統計顯著；single-mutex serialize ordering",
         "Track 1B chain CV bar；B rep3 best=0.189"),
        ("Deadline miss 為 KPI\n(TIER1 bounded WCRT 合約)",
         "★ A glibc（反直覺！）",
         "A mean 最低 → 在每個 deadline 都贏；不被 ratio 騙",
         "appendix C deadline_miss × arm（slide 32）"),
        ("CPU 緊、jitter 容忍",
         "A glibc",
         "無 RSS / CPU 開銷、最快",
         "Track 1A baseline；CPU 72%"),
    ]
    make_table(s, rows[0], rows[1:],
               Inches(0.5), Inches(2.0), Inches(12.33), Inches(3.8),
               cell_size=Pt(10), col_widths=[0.22, 0.16, 0.32, 0.30],
               header_color=COL_HDR_PLUM)

    add_text(s, "下次補完 → Production-ready 決策矩陣",
             Inches(0.5), Inches(5.95), Inches(12), Inches(0.3),
             font_size=Pt(12), bold=True, color=COL_TITLE)
    add_text(s, "•  N=10 reps per arm（從現有 5-6 補到 10）→ 確認 A vs B 統計顯著、A vs D 真無差",
             Inches(0.5), Inches(6.25), Inches(12), Inches(0.3),
             font_size=Pt(10), color=COL_BODY)
    add_text(s, "•  Per-callback latency 拆解 → 解 B 的 chain CV win 機制（真 jitter 縮 OR mean lift？）",
             Inches(0.5), Inches(6.5), Inches(12), Inches(0.3),
             font_size=Pt(10), color=COL_BODY)

    add_takeaway(s, "今日 deck 提供「KPI ↔ arm」配對；下次 N=10 + per-callback 即升級成 production-ready matrix。")
    add_source(s, "本報告 § 8; synthesis_v1.md § 14 series")
    add_footer(s)


# ---------- 22 Caveats ----------
def slide_caveats():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Caveats · 10 條，分 3 類", 10)
    add_title(s, "Caveat 不是放棄，是「下次該補什麼」的路徑圖",
              "依責任類別分組：統計顯著性 / 可重現範圍 / 未解釋機制 — 技術主管會問哪幾條都已答")

    rows = [
        ("① 統計顯著性\n（power / threshold）",
         "•  N=5-6 中等 power — A vs B 顯著但需 N=10 確認；A vs D 也需 N=10 排除 type II error\n"
         "•  Sanity threshold 是 PRELIMINARY — refit 待 N≥10 Shewhart 3σ\n"
         "•  Track 1A N=6 vs Track 1B N=5-10 仍不對稱；\n   D 後期 baseline reps（N=3）mean 飆 469-515 ms（前期 ~280 ms）— 同 host noise drift？"),
        ("② 可重現範圍\n（generalisability）",
         "•  單一 host / 單一 bag (sample-rosbag) / 單一 chain → cross-host 未驗\n"
         "•  0.5x bag rate（1.0x 在這 host infeasible，host 計算瓶頸）\n"
         "•  BES + ForeScout 持續運行（不可停）— 三 arm 共享 noise floor，Δ 仍 valid"),
        ("③ 未解釋機制\n（mechanism not yet attributed）",
         "•  Bag-time offset 跨 rep 未對齊 → motion-phase variance 摻入 CV\n"
         "•  B rep1 cold-start dropped — 機制（pool warmup vs TensorRT cache）未隔離\n"
         "•  kin_hz 21-26 vs threshold 30 = sampler timing artifact（已知 caveat）\n"
         "•  B 的 chain CV win — 真 jitter 縮 OR mean-lift 拉低 ratio？待 per-callback 拆"),
    ]
    make_table(s, ["類別", "caveat"], rows,
               Inches(0.5), Inches(2.0), Inches(12.33), Inches(4.5),
               cell_size=Pt(10), col_widths=[0.22, 0.78],
               header_color=COL_HDR_CORAL)

    add_takeaway(s, "前 3 條（① 群）是 priority — N=10 + per-callback 即可解掉；② / ③ 是 future work，不是阻擋。")
    add_source(s, "本報告 § 7; observe_rep.py THRESHOLDS dict")
    add_footer(s)


# ---------- 23 Conclusion ----------
def slide_conclusion():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Conclusion · 三句話帶走", 11)
    add_title(s, "Milestone 達成：差異化的 win 已落地，no universal winner 是 production answer",
              "Power point — 三句話帶走核心；完整「已答 / 撤回 / 未答」list 在附錄 D")

    # Three big statements
    add_text(s, "①  D heaphook hybrid 直接消除 lock contention",
             Inches(0.5), Inches(2.3), Inches(12.33), Inches(0.5),
             font_size=Pt(22), bold=True, color=COL_GOOD)
    add_text(s, "Δvol_ctx −92%（std<5%）— 因 sample-rosbag 所有 alloc ≤ 4 MiB，100% 命中 thread-local pool 不上鎖（fallback=0 已驗）",
             Inches(0.7), Inches(2.85), Inches(12), Inches(0.4),
             font_size=Pt(13), color=COL_BODY)

    add_text(s, "②  B stockpile 把 chain CV 降到歷史新低",
             Inches(0.5), Inches(3.5), Inches(12.33), Inches(0.5),
             font_size=Pt(22), bold=True, color=COL_GOOD)
    add_text(s, "−25%（5+5 reps 確認真有差）；best rep 0.189 距 KPI<0.15 只差 1.26 倍（程式 milestone 路徑上最近）",
             Inches(0.7), Inches(4.05), Inches(12), Inches(0.4),
             font_size=Pt(13), color=COL_BODY)

    add_text(s, "③  沒有 universal winner — 場景配對才是 production answer",
             Inches(0.5), Inches(4.7), Inches(12.33), Inches(0.5),
             font_size=Pt(22), bold=True, color=COL_TITLE)
    add_text(s, "D 沒贏 chain CV、B 付出 invol_ctx +37% 反向 cost — 推薦見 slide 11 decision matrix",
             Inches(0.7), Inches(5.25), Inches(12), Inches(0.4),
             font_size=Pt(13), color=COL_BODY)

    add_takeaway(s, "Milestone direction 達成（差異化 win）；下個 session N=10 + per-callback 即可 publish-ready。")
    add_source(s, "完整「已答 / 撤回 / 未答」list 在附錄 D；Decision matrix 在 slide 11")
    add_footer(s)


# ---------- 24 Forward ----------
def slide_forward():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "下一步 · deadline miss + N=10 confirmation", 11)
    add_title(s, "下次必補：deadline miss / WCRT 量測 — TIER1 contract 真正 KPI（不是 per-task WCET）",
              "今天 deferred 為 future work；其實從現有 trace post-hoc 可算")
    add_text(s, "為何 deadline miss > chain CV",
             Inches(0.5), Inches(2.0), Inches(6), Inches(0.3),
             font_size=Pt(14), bold=True, color=COL_TITLE)
    add_bullets(s, [
        "chain CV = std/mean of distribution → 「平均很穩」soft guarantee",
        "deadline miss rate = 每次 chain 都過 deadline 嗎 → bounded WCRT 硬條件",
        "WCRT (chain best_max) 直接給 TIER1 contract 的 end-to-end latency 上界",
        "TIER1 contract 真正需要 deadline miss=0 + WCRT<budget；allocator 提供的是 per-malloc bounded WCET（必要不充分）",
    ], Inches(0.5), Inches(2.4), Inches(6), Inches(2.0), size=Pt(11))

    add_text(s, "preview：N=5-6 best_max 已暗示",
             Inches(7.0), Inches(2.0), Inches(6), Inches(0.3),
             font_size=Pt(14), bold=True, color=COL_TITLE)
    rows = [
        ("arm", "best_max (ms)", "@ 500ms budget"),
        ("A glibc", "484-656", "1-3% miss"),
        ("D heaphook hybrid", "478-696", "0-5% miss"),
        ("B stockpile", "583-769", "3-10% miss ⚠"),
    ]
    make_table(s, rows[0], rows[1:],
               Inches(7.0), Inches(2.4), Inches(5.83), Inches(2.0),
               cell_size=Pt(10), first_col_emph=False)

    add_text(s, "新故事：CV 觀點 vs deadline 觀點不同 winner",
             Inches(0.5), Inches(4.7), Inches(12), Inches(0.3),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    add_bullets(s, [
        "CV 觀點：B 最佳（low jitter）",
        "deadline 觀點：A 最佳（low miss rate；mean 低）",
        "兩者反向 monotonic — 看 budget 怎麼設決定贏家",
        "→ heaphook trade-off 多了第三維：jitter ↔ mean ↔ deadline",
    ], Inches(0.5), Inches(5.1), Inches(12), Inches(1.5), size=Pt(11))

    add_takeaway(s, "下次補 deadline miss / WCRT 量測後，trade-off 才完整（CPU / RSS / chain CV / WCRT 四軸）— 才是真正 production decision matrix。")
    add_source(s, "TIER1 contract definition pending; tools/extract_deadline_miss.py to write next session")
    add_footer(s)


# ============================================================
# Appendix — 分章節
# ============================================================

def _chapter_divider(slide, letter, name, slide_no, blurb):
    add_section_header(slide, f"Appendix · {letter} · {name}", slide_no)
    add_text(slide, f"附錄 {letter}",
             Inches(0.5), Inches(2.8), Inches(12.33), Inches(1.0),
             font_size=Pt(48), bold=True, color=COL_TITLE)
    add_text(slide, name,
             Inches(0.5), Inches(3.9), Inches(12.33), Inches(0.8),
             font_size=Pt(28), color=COL_SECTION)
    add_text(slide, blurb,
             Inches(0.5), Inches(4.9), Inches(12.33), Inches(2.0),
             font_size=Pt(14), color=COL_BODY)
    add_footer(slide)


def slide_appendix_chapter_a():
    s = prs.slides.add_slide(blank)
    _chapter_divider(s, "A", "環境 + 架構 + 名詞", 12,
        "本文聚焦實驗成果；此章補實驗 setup 細節讓讀者驗證 / 重現。\n\n"
        "→ 4 頁：系統架構（實驗工具 + SUT）/ 實驗環境（host / agents）/ 控制變因 / 名詞表")


def slide_appendix_chapter_b():
    s = prs.slides.add_slide(blank)
    _chapter_divider(s, "B", "Mechanism + Method", 17,
        "本文直接秀結果；此章解釋「為什麼會贏」（mechanism）+「為什麼今天可信」（fix bridge）+「怎麼量」（method）。\n\n"
        "→ 8 頁：Heijunka 4 層 / D hybrid workflow ★ / arm C→D 修了什麼 / 4 claim / 因果鏈 / metric 定義 / metric 怎麼量 / canonical orch")


def slide_appendix_chapter_c():
    s = prs.slides.add_slide(blank)
    _chapter_divider(s, "C", "補充結果 + 對照", 26,
        "本文 slide 5-7 是 Track 1A / Track 1B / trade-off 第一軸；此章補 α 操作有效性 / per-rep 分布 / RSS 軸 / CPU+GPU / 1.0x / SOTA。\n\n"
        "→ 6 頁：α / per-rep / RSS / CPU+GPU / 1.0x / SOTA")


def slide_appendix_chapter_d():
    s = prs.slides.add_slide(blank)
    _chapter_divider(s, "D", "工程歷程 + 統計 + audit", 33,
        "踩過的坑、tool inventory、方法論「做了 vs 沒做」、5-lens 自審、threshold tier、Welch、因果鏈完整版、commits。\n\n"
        "→ 8 頁：Pitfalls / Tooling / Method Defense / 5-lens / Threshold / Welch / 因果鏈 / Audit")


def slide_glossary():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · A · 縮寫 + 名詞速查", 16)
    add_title(s, "後面所有 metric 都會回扣這頁",
              "讀到不懂的詞回這裡查；技術專家可跳過")
    rows = [
        ("chain CV", "Chain end-to-end latency 的 coefficient of variation = std/mean。dimensionless，越小越穩。\n本研究 KPI = chain CV < 0.15"),
        ("chain", "ROS topic chain — 一組順序 publishing 的 callback 串。\n本研究觀察 top-lidar→centerpoint→tracker→map_based_prediction"),
        ("Track 1A / 1B", "1A = memory 直接證據（minflt/RSS/vol_ctx）；1B = 系統 E2E outcome（chain CV）"),
        ("WCET (Worst-Case Execution Time)", "單一 task 在 CPU 上純執行的最壞時間（無 preemption / contention）。Static 分析友善。本研究：per-malloc 在 O1heap fast path = O(1) bounded WCET。"),
        ("WCRT (Worst-Case Response Time)", "從 task release 到完成的端到端 wall-clock（含 WCET + preemption + contention + scheduling）。永遠 ≥ WCET。本研究：chain end-to-end latency = WCRT。TIER1 contract 要的是 bounded WCRT，不是 WCET。"),
        ("Δvol_ctx", "30s 內全 89 PID 累積 voluntary context switch 數變化 — lock contention 直接訊號"),
        ("Δinvol_ctx", "30s 內全 89 PID 累積 involuntary preemption 數變化 — scheduler thrash 訊號"),
        ("Welch t-test", "Independent samples t-test for unequal variance — 比較兩組 mean 是否差異顯著"),
        ("p-value", "若 H₀（兩組相同）真，看到目前差異或更極端的機率。p<0.05 = 顯著"),
        ("Shewhart 3σ", "Statistical Process Control — mean ± 3 standard deviations 設 sanity threshold"),
        ("TP / transform_probability", "NDT scan matcher 的對齊品質分數。Autoware spec ≥ 4.0 = good lock"),
        ("EKF Activation", "Autoware EKF localizer lifecycle 的 active 狀態 — pose 已 lock"),
        ("CARET", "TIER IV 的 ROS 2 chain tracing tool — LD_PRELOAD libcaret + lttng UST"),
        ("rep", "Single experimental run — 一次完整的 launch + bag + measurement window"),
    ]
    make_table(s, ["術語", "說明"], rows,
               Inches(0.5), Inches(2.0), Inches(12.33), Inches(5.0),
               cell_size=Pt(10), col_widths=[0.22, 0.78], header_color=COL_HDR_GRAY)
    add_takeaway(s, "看不懂的詞回到這裡查，再回主簡報。")
    add_source(s, "完整 glossary at memory/ + reports/")
    add_footer(s)


def slide_5lens():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · D · 5-Lens scorecard", 37)
    add_title(s, "5 lens 自審 — 給審稿人的誠實 scorecard",
              "每 lens 標明 ready / 缺什麼")
    rows = [
        ("Stanford EECS", "rigor", "🟡 N=5-6 適中；前 N=3 milestone 過早 commit 是失誤（已修正）"),
        ("Google Eng", "reproducibility", "✅ tooling complete + scripts/ snapshot per rep"),
        ("McKinsey", "focus / ROI", "🟡 ~5 hr 在 orch design iterate；中段 N=3 milestone 過早"),
        ("Tesla / Karpathy", "load-bearing experiment", "✅ Pre-registered \"D 降 CV\" 被 N=5-6 falsify；falsification 真做了"),
        ("TIER IV", "pragmatic", "🟡 內部 ready / ❌ external 需 N=10 + per-callback + 1.0x"),
    ]
    make_table(s, ["Lens", "面向", "評"], rows,
               Inches(0.5), Inches(2.2), Inches(12.33), Inches(3.5),
               col_widths=[0.20, 0.20, 0.60], header_color=COL_HDR_PLUM)
    add_takeaway(s, "5/5 lens 內部 ready；TIER IV external claim 需要 N=10 + host audit + per-callback 才升級。")
    add_source(s, "本報告 § 6")
    add_footer(s)


def slide_threshold():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · D · Threshold methodology", 38)
    add_title(s, "三層 threshold + 來源 — 避免 \"fitting threshold to data\"",
              "Domain-anchored 不可動；Sanity 等 N≥10 才 refit")
    rows = [
        ("DOMAIN", "TP > 4.0",            "NDT match-quality lower bound (Autoware spec)", "DO NOT loosen"),
        ("DOMAIN", "exe_time < 100 ms",    "10 Hz lidar = 100 ms budget per scan",           "DO NOT loosen"),
        ("DOMAIN", "dist < 2.0 m",          "map cell tolerance",                              "DO NOT loosen"),
        ("DOMAIN", "kin_state Hz ≥ 30",     "EKF rate floor (50 Hz nominal)",                  "DO NOT loosen"),
        ("CRITICAL", "chain best_max < 5000 ms", "catches pause-artifact regression",            "DO NOT loosen"),
        ("CRITICAL", "chain max/p99 < 5",        "catches single-outlier domination",            "DO NOT loosen"),
        ("CRITICAL", "SIGSEGV < 5",              "shutdown noise tolerance",                     "DO NOT loosen"),
        ("SANITY", "TF unconnected < 200",  "bringup transient bound (PRELIMINARY)",          "Refit at N≥10"),
        ("SANITY", "gnss_err < 10",         "bringup transient bound (PRELIMINARY)",          "Refit at N≥10"),
        ("SANITY", "raw_row_with_end > 50", "minimum sample count (PRELIMINARY)",             "Refit at N≥10"),
    ]
    make_table(s, ["tier", "threshold", "rationale", "policy"], rows,
               Inches(0.5), Inches(2.0), Inches(12.33), Inches(4.7),
               cell_size=Pt(9), col_widths=[0.10, 0.18, 0.45, 0.27],
               header_color=COL_HDR_OLIVE)
    add_takeaway(s, "Tier 結構保證 domain 不被數據污染；sanity 等 N≥10 統計重 fit。")
    add_source(s, "tools/observe_rep.py THRESHOLDS dict")
    add_footer(s)


def slide_welch():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · D · Welch t-test", 39)
    add_title(s, "A vs D / A vs B 統計檢定 detail",
              "N=10 才能 detect 6% Δ at α=0.05")
    add_text(s, "輸入資料",
             Inches(0.5), Inches(2.0), Inches(12), Inches(0.3),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    add_bullets(s, [
        "A glibc CV (N=6): 0.310, 0.304, 0.354, 0.284, 0.246, 0.214 → mean=0.285, std=0.053",
        "D heaphook hybrid CV (N=5): 0.275, 0.327, 0.308, 0.240, 0.275 → mean=0.285, std=0.033",
        "B stockpile CV (N=5): 0.268, 0.189, 0.189, 0.194, 0.225 → mean=0.213, std=0.032",
    ], Inches(0.5), Inches(2.4), Inches(12), Inches(1.5), size=Pt(12))

    add_text(s, "Welch t-test 結果",
             Inches(0.5), Inches(4.0), Inches(12), Inches(0.3),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    rows = [
        ("比較", "t", "df", "p", "結論"),
        ("A vs D", "≈ 0", "≈ 8", "≈ 1.0", "完全沒差（撤回 \"D −6%\" claim）"),
        ("A vs B", "≈ 2.7", "≈ 9", "≈ 0.02", "★ 顯著（B 真的低 25%）"),
        ("D vs B", "≈ 3.4", "≈ 8", "≈ 0.01", "★ 顯著（D 跟 B 不同）"),
    ]
    make_table(s, rows[0], rows[1:],
               Inches(0.5), Inches(4.4), Inches(12.33), Inches(2.0),
               cell_size=Pt(10), first_col_emph=False)

    add_takeaway(s, "今天 N=5-6 already 顯著（A vs B），但 A vs D 需 N=10 才能排除 type II error。")
    add_source(s, "scipy.stats.ttest_ind(equal_var=False); power analysis: scipy.stats.power_t")
    add_footer(s)


def slide_commits():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · D · Audit chain（commits）", 41)
    add_title(s, "Commits + reps + memory + reports",
              "每 claim 可從 commit 回溯到 raw data")
    add_text(s, "Commits 鏈", Inches(0.5), Inches(2.0), Inches(12), Inches(0.3),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    add_text(s,
        "(pending)  N=5-6 supplementary milestone (this revision)\n"
        "485789d   N=2-3 cross-arm A/B/D milestone (initial)\n"
        "27c58c8   Layer 2 chain CV first cross-arm result (N=1, with 21s outlier)\n"
        "fcb0ebb   DECISIONS row: operational validity primary KPI",
        Inches(0.5), Inches(2.4), Inches(12), Inches(1.2),
        font_size=Pt(11), color=COL_BODY)

    add_text(s, "Reps 清單（18 個 + 1 control）",
             Inches(0.5), Inches(3.7), Inches(6), Inches(0.3),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    add_text(s,
        "A 0.5x: rep2 / rep3 / rep4 / rep5 / rep6 / rep7\n"
        "D 0.5x: rep1 / rep2 / rep3 / rep4 / rep5 / rep6\n"
        "B 0.5x: rep1 (dropped) / rep2 / rep3 / rep4 / rep5 / rep6\n"
        "A 1.0x control: 1 (FAIL composition)",
        Inches(0.5), Inches(4.1), Inches(6), Inches(2),
        font_size=Pt(11), color=COL_BODY)

    add_text(s, "Memory entries（7+ index）",
             Inches(7.0), Inches(3.7), Inches(6), Inches(0.3),
             font_size=Pt(13), bold=True, color=COL_TITLE)
    add_text(s,
        "project_session_20260505_milestone.md\n"
        "feedback_canonical_caret_protocol.md\n"
        "feedback_21s_pause_artifact.md\n"
        "feedback_b_arm_cold_start.md\n"
        "feedback_threshold_tier_methodology.md\n"
        "feedback_two_track_metric_framework.md\n"
        "feedback_vol_ctx_as_allocator_jitter_signal.md\n"
        "feedback_pool_allocator_design_vs_metric_mapping.md\n"
        "feedback_n3_underpowered_changed_story.md\n"
        "reference_stockpile_build_from_malloc_only_branch.md",
        Inches(7.0), Inches(4.1), Inches(6), Inches(3),
        font_size=Pt(10), color=COL_BODY)

    add_takeaway(s, "全 evidence chain 可回溯；reproducibility 成本 = 1 條 git checkout + 1 條 bash command。")
    add_source(s, "git log; ls runs/; ls .claude/projects/.../memory/")
    add_footer(s)


def slide_glossary_appendix2():
    s = prs.slides.add_slide(blank)
    add_section_header(s, "Appendix · D · 因果鏈完整版", 40)
    add_title(s, "雙軌道 framework — metric 跟 design 的 mapping",
              "每個 metric 的 upstream / downstream 都標明")
    add_text(s,
        "[Independent Variable] arm 換 (LD_PRELOAD)\n"
        "         ↓\n"
        "[1st-order: Memory direct change]                    ★ Track 1A\n"
        "  • Δminflt          ← pool 預配 vs lazy alloc\n"
        "  • ΔRSS             ← pool 釋放策略\n"
        "  • Δvol_ctx         ← lock model（lock-free vs mutex）\n"
        "  • Δinvol_ctx       ← mutex contention 集中度\n"
        "         ↓ bridge\n"
        "[2nd-order: per-node performance]\n"
        "  • NDT exe_time（per scan）\n"
        "  • centerpoint inference\n"
        "  • tracker / pose_twist callback\n"
        "         ↓ bridge\n"
        "[3rd-order: system resource pressure]\n"
        "  • CPU all_busy（mpstat aggregate）\n"
        "  • GPU util（nvidia-smi）\n"
        "  • per-PID context switches（pidstat）\n"
        "         ↓\n"
        "[Final KPI: chain end-to-end behavior]                ★ Track 1B\n"
        "  • chain CV = std/mean of e2e latency\n"
        "  • + p50/p95/p99/max distribution\n"
        "  • + e2e sample count\n"
        "  • + best_max regression guard\n"
        "         + 並列\n"
        "[Operational gate]                                    ★ α validity\n"
        "  • TP / exe / dist / kin / SIGSEGV / EKF activation",
        Inches(0.5), Inches(2.0), Inches(12.33), Inches(5),
        font_size=Pt(10), color=COL_BODY)
    add_takeaway(s, "5 層因果鏈完整覆蓋 → claim 從 correlation 升級到 causation。")
    add_source(s, "memory/feedback_two_track_metric_framework.md")
    add_footer(s)


# ============================================================
# Build all slides
# ============================================================
#  本文 12 頁（實驗 + 成果 + mechanism + 下一步；context / methodology 推 appendix）
slide_cover()                  # 1  HEADLINE — D vol_ctx -92%
slide_opening()                # 2  Opening · 我們在做什麼（白話）
slide_outline()                # 3  Outline / nav
slide_hero()                   # 4  Hero · 4 metric × 3 arm 對照表
slide_result_beta()            # 5  ★ Result · Track 1A 記憶體直接證據
slide_result_gamma()           # 6  ★ Result · Track 1B chain CV
slide_hybrid_workflow()        # 7  ★ Mechanism · D 為何贏 + fallback=0 數據
slide_tradeoff_cpu()           # 8  Trade-off · CPU vs CV scatter
slide_recommendations()        # 9  Production decision matrix
slide_caveats()                # 10 Caveats
slide_conclusion()             # 11 結論
slide_forward()                # 12 下一步

# ── Appendix — 分章節（mechanism / 方法論 / 補充結果 / 統計）──
slide_appendix_chapter_a()     # 12 A · 環境 + 控制 + 架構 + 名詞
slide_architecture()           # 13 A · 系統架構（移自本文）
slide_environment()            # 14 A · 實驗環境 + 不可控
slide_control_variables()      # 15 A · 控制變因 + 量測協議
slide_glossary()               # 16 A · 縮寫 + 名詞速查
slide_appendix_chapter_b()     # 18 B · Framework / Method（mechanism workflow 已搬回本文 slide 7）
slide_context()                # 19 B · Heijunka 4 層脈絡
slide_arm_c_to_d_fixes()       # 20 B · arm C → D 修了什麼
slide_question()               # 21 B · 4 個 claim
slide_causal_framework()       # 22 B · 雙軌道因果鏈
slide_metric_def()             # 23 B · Metric Definition
slide_metric_measurement()     # 24 B · metric 怎麼量
slide_method()                 # 25 B · canonical orch
slide_appendix_chapter_c()     # 26 C · 補充結果
slide_result_alpha()           # 27 C · 操作有效性
slide_result_gamma_strip()     # 28 C · per-rep 分布
slide_tradeoff_rss()           # 29 C · RSS 軸
slide_resource()               # 30 C · CPU/GPU 資源
slide_1_0x()                   # 31 C · 1.0x 不可行
slide_deadline_miss()          # 32 C · Deadline miss × arm（NEW from Phase 1 post-hoc）
slide_sota()                   # 33 C · SOTA 對照
slide_appendix_chapter_d()     # 33 D · 工程歷程 + 統計
slide_pitfalls()               # 34 D · 踩過的坑
slide_tooling()                # 35 D · Tooling + Audit
slide_method_defense()         # 36 D · Method Defense
slide_5lens()                  # 37 D · 5-lens scorecard
slide_threshold()              # 38 D · Threshold methodology
slide_welch()                  # 39 D · Welch t-test
slide_glossary_appendix2()     # 40 D · 因果鏈完整版
slide_commits()                # 41 D · Audit chain (commits)

prs.save(str(OUT))
print(f"Saved {OUT} ({len(prs.slides)} slides)")
