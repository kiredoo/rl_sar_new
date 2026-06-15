"""Common matplotlib defaults for cross_abcd_v4 figures (M3 viz P0).

Why this exists: today's auto-figures across reports/figures/ and per-run
figures/ use ad-hoc colour + DPI choices, and the y-axis is in raw kB
which makes "1.3e+07" eye-noise. SOTA paper-grade figures need:

  - a fixed 4-arm palette (A / B / C / D-v4) consistent across reports
  - an MiB y-axis formatter (rss_kb in /proc is KiB; chart label MUST
    convert), per memory `feedback_units_kb_to_mb.md`
  - three DPI presets (paper 300 / slide 150 / report 100) selectable
    by the caller

Used by: tools/make_v4_headline_figures.py, tools/plot_tier0.py,
tools/plot_timeseries.py, tools/plot_ecdf_ccdf.py (M3). Caller imports
this BEFORE creating the figure.

Public API:

    from tools import figstyle
    figstyle.apply()                   # default report DPI
    figstyle.apply(preset="paper")     # 300 DPI
    color = figstyle.ARM_COLORS["A"]   # palette lookup
    figstyle.format_axis_mib(ax)       # MiB y-axis formatter

Keep this file dependency-free except matplotlib.
"""
from __future__ import annotations

from typing import Dict, Literal

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter


# 4-arm palette. Paul Tol "muted" qualitative — colour-blind safe + grayscale-distinguishable.
# Order: A (glibc baseline, blue) → B (stockpile, green) → C (hybrid-unfixed, red) → D-v4 (hybrid-fixed, orange).
ARM_COLORS: Dict[str, str] = {
    "A":     "#4477AA",   # blue
    "B":     "#228833",   # green
    "C":     "#CC3311",   # red
    "D-v3":  "#EE7733",   # orange (lighter)
    "D-v4":  "#EE3377",   # magenta (D-v4 distinct from D-v3)
}

# Preset DPI by use case.
DPI_PRESETS: Dict[str, int] = {
    "paper":  300,   # archival, manuscript
    "slide":  150,   # presentation
    "report": 100,   # default; renders fast; readable inline
}

Preset = Literal["paper", "slide", "report"]


def apply(preset: Preset = "report") -> None:
    """Apply project-standard rcParams. Call before plt.subplots()."""
    if preset not in DPI_PRESETS:
        raise ValueError(f"unknown preset {preset!r}; choose from {list(DPI_PRESETS)}")
    dpi = DPI_PRESETS[preset]
    matplotlib.rcParams.update({
        "savefig.dpi": dpi,
        "figure.dpi": dpi,
        "figure.autolayout": True,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 10,
        "axes.titlesize": 11,
        "legend.frameon": False,
        "legend.fontsize": 9,
        "lines.linewidth": 1.5,
    })


def format_axis_mib(ax, axis: Literal["y", "x"] = "y") -> None:
    """Replace the axis tick labels to express raw KiB values as MiB.

    /proc/<pid>/status reports VmRSS in KiB; matplotlib labels by default
    show "1.3e+07" which is unreadable. This applies a FuncFormatter
    that divides by 1024 and labels MiB.
    """
    fmt = FuncFormatter(lambda x, _pos: f"{x / 1024:.0f} MiB")
    if axis == "y":
        ax.yaxis.set_major_formatter(fmt)
    else:
        ax.xaxis.set_major_formatter(fmt)


def format_axis_gib(ax, axis: Literal["y", "x"] = "y") -> None:
    """Same as format_axis_mib but for GiB (raw KiB → /1048576).

    Use when y-axis ranges into >2048 MiB; otherwise use format_axis_mib.
    """
    fmt = FuncFormatter(lambda x, _pos: f"{x / 1048576:.1f} GiB")
    if axis == "y":
        ax.yaxis.set_major_formatter(fmt)
    else:
        ax.xaxis.set_major_formatter(fmt)


def arm_color(arm: str) -> str:
    """Look up an arm's palette colour with a graceful fallback."""
    return ARM_COLORS.get(arm, "#888888")


__all__ = [
    "ARM_COLORS",
    "DPI_PRESETS",
    "apply",
    "format_axis_mib",
    "format_axis_gib",
    "arm_color",
]
