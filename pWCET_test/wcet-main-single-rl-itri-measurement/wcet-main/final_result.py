#!/usr/bin/env python3
from __future__ import annotations

"""
One-shot generator for final_result.xlsx.

This script embeds:
  1) HTML report parsing (extract IESTA pWCET, xi_shape, KS test, mean/CV, ...)
  2) Inequality-based pWCET from timestamp JSONs (atan/tanh)
  3) Merge + apply final_result rules + Excel styling

Default inputs:
  - report/index.html
  - sampled_execution_time/*.json

Rules (as requested):
  - pWCET column uses IESTA values (ppfXX_iesta).
  - final_result normally uses pWCET (IESTA), unless:
      Rule 1) If KStest == False AND pWCET > 30, use arctan.
      Rule 2) If xi_shape > 0.2, use arctan.
  - KStest is written as True/False.
  - Styling:
      * If KStest is False: KStest cell is red.
      * If Rule 1 switches to arctan: set font red for pWCET, arctan, final_result_source, final_result.
      * If Rule 2 switches to arctan: set font red for xi_shape, final_result_source, final_result.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup
from openpyxl.styles import Font, Alignment


SUPPORTED_PCTS = {95.0, 99.0, 99.6, 99.9, 99.99, 99.999}


def _err(msg: str, code: int = 2) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)
    raise SystemExit(code)


def _warn(msg: str) -> None:
    print(f"[WARN] {msg}", file=sys.stderr)


# -----------------------------
# Part 1: HTML report parsing
# -----------------------------
def clean_name(txt: str) -> str:
    """
    Normalize callback titles shown in the HTML report.

    The report may prefix callback names with icons (or other non-alnum glyphs).
    We strip leading non-alnum characters and whitespace.
    """
    txt = (txt or "").strip()
    txt = re.sub(r"^[^A-Za-z0-9_]+", "", txt)
    return txt.strip()


def first_data_row(header_th):
    """From a section header <th>, find the first following <tr> that contains <td>."""
    row = header_th.find_next("tr")
    while row and not row.find_all("td"):
        row = row.find_next("tr")
    return row


def extract_records_from_html(soup: BeautifulSoup, pct: float) -> List[Tuple[Any, ...]]:
    """
    Extract per-callback metrics from the HTML.

    - xi_shape: prefer 'GEV (IESTA-adjusted data)' shape if present; otherwise fallback to 'GEV (raw data)' shape.
    - ppfXX_iesta: optional. If missing, fallback to ppfXX.
    - KStest: parsed from the original <p> text:
        "Kolmogorov-Smirnov test p-value is X. ...", pass if X >= 0.05
      If the KS line is missing, we keep KStest=True (do not trigger rule 1 by accident).
    """
    ppf_col_map = {95.0: 0, 99.0: 1, 99.6: 2, 99.9: 3, 99.99: 4, 99.999: 5}
    if pct not in ppf_col_map:
        _err(f"Unsupported percentile {pct}. Supported: {sorted(SUPPORTED_PCTS)}")
    col_idx = ppf_col_map[pct]

    recs: List[Tuple[Any, ...]] = []
    for h4 in soup.select("h4[id^='cb_']"):
        cb_name = clean_name(h4.get_text(strip=True))
        status: List[str] = []

        ppf_val = ppf_iesta_val = None
        blk_avg = blk_stdev = None
        global_min = global_max = None
        mean_ms = stdev_ms = cv = None
        xi_shape = None
        xi_shape_src = None

        # KS test: default False if missing in report (so missing parsing is visible).
        ks_pass = False
        ks_found = False

        div = h4.find_parent("div")
        if not div:
            status.append("missing div")
            recs.append(
                (
                    cb_name,
                    "; ".join(status),
                    global_min,
                    global_max,
                    mean_ms,
                    stdev_ms,
                    cv,
                    xi_shape,
                    xi_shape_src,
                    ppf_val,
                    ppf_iesta_val,
                    blk_avg,
                    None,
                    ks_pass,
                )
            )
            continue        # KS test p-value parsing (robust: do not rely on Tag.string)
        for ptag in div.find_all("p"):
            txt = ptag.get_text(" ", strip=True)
            if "Kolmogorov-Smirnov" in txt and "p-value" in txt:
                ks_found = True
                m = re.search(r"p-value\s*(?:is)?\s*([0-9]*\.?[0-9]+)", txt)
                if m:
                    try:
                        ks_pass = float(m.group(1)) >= 0.05
                    except ValueError:
                        status.append("non-numeric KS p-value")
                else:
                    status.append("missing KS p-value number")
                break

        if not ks_found:
            status.append("missing KS test line")

        tbl = div.find("table")
        if not tbl:
            status.append("missing table")
            recs.append(
                (
                    cb_name,
                    "; ".join(status),
                    global_min,
                    global_max,
                    mean_ms,
                    stdev_ms,
                    cv,
                    xi_shape,
                    xi_shape_src,
                    ppf_val,
                    ppf_iesta_val,
                    blk_avg,
                    None,
                    ks_pass,
                )
            )
            continue

        # block maxima stats
        blk_hdr = tbl.find(
            lambda t: t.name == "th"
            and "statistics" in t.get_text(strip=True).lower()
            and "block maxima" in t.get_text(strip=True).lower()
        )
        if blk_hdr:
            row = first_data_row(blk_hdr)
            if row:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= 5:
                    try:
                        blk_avg = float(cells[2])
                    except ValueError:
                        status.append("non-numeric block_avg_ms")
                    try:
                        blk_stdev = float(cells[4])
                    except ValueError:
                        status.append("non-numeric block_stdev_ms")
                else:
                    status.append("incomplete block_maxima row")
            else:
                status.append("missing block_maxima data row")
        else:
            status.append("missing block_maxima section")

        # global stats
        glob_hdr = tbl.find(
            lambda t: t.name == "th"
            and "statistics" in t.get_text(strip=True).lower()
            and "block maxima" not in t.get_text(strip=True).lower()
        )
        if glob_hdr:
            row = first_data_row(glob_hdr)
            if row:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= 4:
                    try:
                        global_min = float(cells[1])
                    except ValueError:
                        status.append("non-numeric global_min_ms")
                    try:
                        global_max = float(cells[3])
                    except ValueError:
                        status.append("non-numeric global_max_ms")
                else:
                    status.append("incomplete global stats row")
            else:
                status.append("missing global stats data row")
        else:
            status.append("missing global stats section")

        # raw stats
        raw_hdr = tbl.find(
            lambda t: t.name == "th"
            and "statistics" in t.get_text(strip=True).lower()
            and "raw data" in t.get_text(strip=True).lower()
        )
        if raw_hdr:
            row = first_data_row(raw_hdr)
            if row:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= 6:
                    try:
                        mean_ms = float(cells[2])
                    except ValueError:
                        status.append("non-numeric mean_ms")
                    try:
                        stdev_ms = float(cells[4])
                    except ValueError:
                        status.append("non-numeric stdev_ms")
                    try:
                        cv = float(cells[5])
                    except ValueError:
                        status.append("non-numeric CV")
                else:
                    status.append("incomplete raw stats row")
            else:
                status.append("missing raw stats data row")
        else:
            status.append("missing raw stats section")

        # GEV (raw data) shape
        xi_shape_raw = None
        gev_raw_hdr = tbl.find(
            lambda t: t.name == "th"
            and "gev" in t.get_text(strip=True).lower()
            and "raw data" in t.get_text(strip=True).lower()
            and "iesta" not in t.get_text(strip=True).lower()
        )
        if gev_raw_hdr:
            head_row = gev_raw_hdr.find_next("tr")
            data_row = head_row.find_next("tr") if head_row else None
            if data_row:
                vals = [td.get_text(strip=True) for td in data_row.find_all("td")]
                if vals:
                    try:
                        xi_shape_raw = float(vals[0])
                    except ValueError:
                        status.append("non-numeric xi_shape_raw")
            else:
                status.append("missing GEV raw data row")
        else:
            status.append("missing GEV (raw) section")

        # GEV (IESTA-adjusted data) shape (optional)
        xi_shape_iesta = None
        gev_iesta_hdr = tbl.find(
            lambda t: t.name == "th"
            and "gev" in t.get_text(strip=True).lower()
            and "iesta" in t.get_text(strip=True).lower()
        )
        if gev_iesta_hdr:
            head_row = gev_iesta_hdr.find_next("tr")
            data_row = head_row.find_next("tr") if head_row else None
            if data_row:
                vals = [td.get_text(strip=True) for td in data_row.find_all("td")]
                if vals:
                    try:
                        xi_shape_iesta = float(vals[0])
                    except ValueError:
                        status.append("non-numeric xi_shape_iesta")

        if xi_shape_iesta is not None:
            xi_shape = xi_shape_iesta
            xi_shape_src = "iesta"
        elif xi_shape_raw is not None:
            xi_shape = xi_shape_raw
            xi_shape_src = "raw"

        # pWCET table (raw)
        pwcet_hdr = tbl.find(
            lambda t: t.name == "th"
            and "pwcet" in t.get_text(strip=True).lower()
            and "iesta" not in t.get_text(strip=True).lower()
        )
        if pwcet_hdr:
            row = first_data_row(pwcet_hdr)
            if row:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) > col_idx:
                    try:
                        ppf_val = float(cells[col_idx])
                    except ValueError:
                        status.append("non-numeric ppf value")
                else:
                    status.append("incomplete pWCET row")
            else:
                status.append("missing pWCET data row")
        else:
            status.append("missing pWCET section")

        # pWCET table (IESTA-adjusted) (optional)
        iesta_hdr = tbl.find(
            lambda t: t.name == "th"
            and "pwcet" in t.get_text(strip=True).lower()
            and "iesta" in t.get_text(strip=True).lower()
        )
        if iesta_hdr:
            row = first_data_row(iesta_hdr)
            if row:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) > col_idx:
                    try:
                        ppf_iesta_val = float(cells[col_idx])
                    except ValueError:
                        status.append("non-numeric ppf_iesta value")

        if ppf_iesta_val is None:
            ppf_iesta_val = ppf_val

        status_str = "ok" if not status else "; ".join(status)
        blk_sum = (blk_avg + blk_stdev) if (blk_avg is not None and blk_stdev is not None) else None

        recs.append(
            (
                cb_name,
                status_str,
                global_min,
                global_max,
                mean_ms,
                stdev_ms,
                cv,
                xi_shape,
                xi_shape_src,
                ppf_val,
                ppf_iesta_val,
                blk_avg,
                blk_sum,
                ks_pass,
            )
        )

    return recs


def parse_html_report(html_path: Path, percentile: float) -> pd.DataFrame:
    if not html_path.is_file():
        _err(f"Missing HTML report: {html_path}")

    pct = float(percentile)
    if pct not in SUPPORTED_PCTS:
        _err(f"Unsupported percentile {pct}. Supported: {sorted(SUPPORTED_PCTS)}")

    try:
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8", errors="ignore"), "lxml")
    except Exception:
        _warn("Failed to parse with lxml; retrying with html.parser")
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8", errors="ignore"), "html.parser")

    ppf_col = f"ppf{int(pct) if float(pct).is_integer() else pct}"
    ppf_iesta_col = f"{ppf_col}_iesta"

    rows = extract_records_from_html(soup, pct)
    if not rows:
        _err(f"No callbacks found in HTML report: {html_path}")

    df = pd.DataFrame(
        rows,
        columns=[
            "callback",
            "status",
            "global_min_ms",
            "global_max_ms",
            "mean_ms",
            "stdev_ms",
            "CV",
            "xi_shape",
            "xi_shape_src",
            ppf_col,
            ppf_iesta_col,
            "block_avg_ms",
            "block_avg_plus_stdev_ms",
            "KStest",
        ],
    )

    # Convert numeric columns
    num_cols = [
        ppf_col,
        ppf_iesta_col,
        "block_avg_ms",
        "block_avg_plus_stdev_ms",
        "global_min_ms",
        "global_max_ms",
        "mean_ms",
        "stdev_ms",
        "CV",
        "xi_shape",
    ]
    df[num_cols] = df[num_cols].apply(pd.to_numeric, errors="coerce")

    # Ensure KStest is boolean True/False
    df["KStest"] = df["KStest"].astype(bool)

    df.sort_values("callback", key=lambda s: s.astype(str).str.lower(), inplace=True)
    return df


# -----------------------------------------
# Part 2: Inequality-based pWCET (atan/tanh)
# -----------------------------------------
def build_default_grids(x: np.ndarray) -> Tuple[List[float], List[int]]:
    """Build reasonable default grids for d and k based on data scale."""
    mean = float(np.mean(x))
    q90 = float(np.quantile(x, 0.90))
    q99 = float(np.quantile(x, 0.99))

    d_candidates = [
        0.5 * mean,
        mean,
        2.0 * mean,
        0.5 * q90,
        q90,
        2.0 * q90,
        q99,
    ]
    d_grid = sorted({d for d in d_candidates if d > 0})
    k_grid = [1, 2, 3, 4]
    return d_grid, k_grid


def compute_base(x_sorted: np.ndarray, d: float, method: str) -> np.ndarray:
    """Compute base = atan(x/d) or tanh(x/d) for monotone samples."""
    z = x_sorted / d
    if method == "atan":
        base = np.arctan(z)
    elif method == "tanh":
        base = np.tanh(z)
    else:
        raise ValueError(f"Unknown method: {method}")
    return base


def ineq_pwcet_single(
    samples: np.ndarray,
    p: float,
    method: str = "atan",
    d_grid: List[float] | None = None,
    k_grid: List[int] | None = None,
) -> Dict[str, Any]:
    """
    Compute pWCET using inequality-based ATAN/TANH bound:
        P(X >= b) <= E[f(X)] / f(b)
    where f(x) = (atan(x/d))^k or (tanh(x/d))^k.
    Scan (d, k) grids and choose the smallest b such that bound <= p.
    """
    x = np.asarray(samples, dtype=float)
    x = x[np.isfinite(x)]
    x = x[x > 0.0]

    if x.size == 0:
        return {"status": "NO_SAMPLES", "pwcet_ns": None, "d": None, "k": None, "n_samples": 0}

    x_sorted = np.sort(x)

    if not (0.0 < p < 1.0):
        raise ValueError(f"Target probability p must be in (0,1), got {p}")

    if d_grid is None or len(d_grid) == 0 or any(d <= 0 for d in d_grid):
        d_grid, _k_grid = build_default_grids(x)
    else:
        _k_grid = None

    if k_grid is None or len(k_grid) == 0:
        if _k_grid is None:
            _, k_grid = build_default_grids(x)
        else:
            k_grid = _k_grid

    best_b = None
    best_d = None
    best_k = None

    for d in d_grid:
        base = compute_base(x_sorted, d, method=method)
        base = np.maximum(base, 1e-18)

        for k in k_grid:
            base_pow = np.power(base, k)
            Ef = float(base_pow.mean())
            if Ef <= 0.0:
                continue

            bounds = Ef / base_pow
            valid_idx = np.where(bounds <= p)[0]
            if valid_idx.size == 0:
                continue

            b_candidate = float(x_sorted[valid_idx[0]])
            if best_b is None or b_candidate < best_b:
                best_b = b_candidate
                best_d = d
                best_k = k

    if best_b is None:
        return {"status": "NO_B_FOUND", "pwcet_ns": float(x_sorted[-1]), "d": None, "k": None, "n_samples": int(x_sorted.size)}

    return {"status": "OK", "pwcet_ns": best_b, "d": best_d, "k": best_k, "n_samples": int(x_sorted.size)}


def load_callbacks_from_json_files(json_paths: List[Path]) -> Tuple[Dict[str, List[float]], List[str]]:
    cb_samples: Dict[str, List[float]] = {}
    units: List[str] = []

    for path in json_paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            _err(f"Failed to read JSON: {path} ({e})")

        if isinstance(data, dict) and "callbacks" in data:
            callbacks = data["callbacks"]
        elif isinstance(data, list):
            callbacks = data
        else:
            _err(f"{path}: JSON format not recognized (no 'callbacks').")

        unit = data.get("unit") if isinstance(data, dict) else None
        if unit and unit not in units:
            units.append(unit)

        for cb in callbacks:
            name = cb.get("name", "<unknown>")
            samples = cb.get("samples", [])
            if not isinstance(samples, list) or len(samples) == 0:
                continue
            dest = cb_samples.setdefault(name, [])
            dest.extend(samples)

    return cb_samples, units


def compute_ineq_from_jsons(
    json_paths: List[Path],
    prob: float,
    method: str,
    min_samples: int,
) -> pd.DataFrame:
    cb_samples, units = load_callbacks_from_json_files(json_paths)
    if not cb_samples:
        _err("No samples found in provided JSON files.")

    rows: List[Dict[str, Any]] = []
    for name, samples in sorted(cb_samples.items()):
        n = len(samples)
        if n < min_samples:
            continue

        x = np.asarray(samples, dtype=float)

        res_atan = {"status": "N/A", "pwcet_ns": None, "d": None, "k": None, "n_samples": n}
        res_tanh = {"status": "N/A", "pwcet_ns": None, "d": None, "k": None, "n_samples": n}

        if method in ("atan", "both"):
            res_atan = ineq_pwcet_single(x, prob, method="atan")
        if method in ("tanh", "both"):
            res_tanh = ineq_pwcet_single(x, prob, method="tanh")

        rows.append(
            {
                "callback_name": name,
                "n_samples": n,
                "p": prob,
                "units_seen": ",".join(units) if units else "",

                "atan_status": res_atan["status"],
                "atan_pwcet_ns": res_atan["pwcet_ns"],
                "atan_d": res_atan["d"],
                "atan_k": res_atan["k"],

                "tanh_status": res_tanh["status"],
                "tanh_pwcet_ns": res_tanh["pwcet_ns"],
                "tanh_d": res_tanh["d"],
                "tanh_k": res_tanh["k"],

                "atan_pwcet_ms": (res_atan["pwcet_ns"] / 1e6) if res_atan["pwcet_ns"] is not None else None,
                "tanh_pwcet_ms": (res_tanh["pwcet_ns"] / 1e6) if res_tanh["pwcet_ns"] is not None else None,
            }
        )

    if not rows:
        _err(f"No callbacks met min_samples={min_samples}; nothing to compute.")

    return pd.DataFrame(rows)


# -----------------------------
# Part 3: Merge + rules + Excel
# -----------------------------
def default_prob_from_percentile(percentile: float) -> float:
    return 1.0 - (float(percentile) / 100.0)


def build_final_table_and_flags(df_html: pd.DataFrame, df_ineq: pd.DataFrame, percentile: float) -> Tuple[pd.DataFrame, List[Dict[str, bool]]]:
    """
    Build final table (with requested column names) and return per-row flags:
      - ks_fail
      - rule1_applied
      - rule2_applied
    """
    pct = float(percentile)
    ppf_col = f"ppf{int(pct) if float(pct).is_integer() else pct}"
    ppf_iesta_col = f"{ppf_col}_iesta"

    df = df_html.copy()

    if ppf_iesta_col in df.columns:
        df["pWCET"] = pd.to_numeric(df[ppf_iesta_col], errors="coerce")
    elif ppf_col in df.columns:
        df["pWCET"] = pd.to_numeric(df[ppf_col], errors="coerce")
        _warn(f"HTML does not have {ppf_iesta_col}; using {ppf_col} as fallback.")
    else:
        _err(f"HTML missing pWCET columns {ppf_iesta_col}/{ppf_col}.")

    # Merge inequality (arctan)
    dfm = df.merge(
        df_ineq,
        left_on="callback",
        right_on="callback_name",
        how="left",
        suffixes=("", "_ineq"),
    )
    dfm["arctan"] = pd.to_numeric(dfm.get("atan_pwcet_ms"), errors="coerce")

    # Apply rules
    flags: List[Dict[str, bool]] = []
    final_sources: List[str] = []
    final_vals: List[float | None] = []

    for _, row in dfm.iterrows():
        ks_pass = bool(row.get("KStest", True))
        ks_fail = not ks_pass

        pwcet = row.get("pWCET")
        arctan = row.get("arctan")
        xi = row.get("xi_shape")

        pw_ok = pd.notna(pwcet)
        at_ok = pd.notna(arctan)

        rule1 = bool(ks_fail and pw_ok and float(pwcet) > 30.0)
        rule2 = bool(pd.notna(xi) and float(xi) > 0.2)

        use_arctan = False
        reasons: List[str] = []

        if rule1:
            reasons.append("rule1")
            if at_ok:
                use_arctan = True
        if rule2:
            reasons.append("rule2")
            if at_ok:
                use_arctan = True

        if use_arctan:
            final_sources.append("arctan")
            final_vals.append(float(arctan))
            rule1_applied = rule1
            rule2_applied = rule2
        else:
            # Default final_result is pWCET (IESTA).
            if pw_ok:
                final_sources.append("pWCET")
                final_vals.append(float(pwcet))
            elif at_ok:
                final_sources.append("arctan")
                final_vals.append(float(arctan))
            else:
                final_sources.append("")
                final_vals.append(None)

            rule1_applied = False
            rule2_applied = False

        flags.append({"ks_fail": ks_fail, "rule1": rule1_applied, "rule2": rule2_applied})

    dfm["final_result_source"] = final_sources
    dfm["final_result"] = final_vals

    # Keep / order columns (user-facing)
    front = [
        "callback",
        "mean_ms",
        "CV",
        "xi_shape",
        "KStest",
        "pWCET",
        "arctan",
        "final_result_source",
        "final_result",
    ]
    # Keep only the columns above (in order).
    cols = [c for c in front if c in dfm.columns]
    dfm = dfm[cols]
    dfm.sort_values("callback", key=lambda s: s.astype(str).str.lower(), inplace=True)

    # Reorder flags to match sorted dataframe order
    # We rebuild flags based on the sorted index mapping.
    flags_sorted = [flags[i] for i in dfm.index.to_list()] if isinstance(dfm.index, pd.Index) else flags
    dfm = dfm.reset_index(drop=True)

    # Display KStest as English True/False strings.
    if "KStest" in dfm.columns:
        dfm["KStest"] = dfm["KStest"].map(lambda v: "True" if bool(v) else "False")

    return dfm, flags_sorted



def _excel_display_len(s: str) -> int:
    """
    Approximate Excel display length:
      - ASCII ~ 1
      - East Asian wide chars ~ 2
    """
    n = 0
    for ch in s:
        # Rough heuristic for CJK / full-width punctuation
        if "\u1100" <= ch <= "\u11FF" or "\u2E80" <= ch <= "\uA4CF" or "\uAC00" <= ch <= "\uD7A3" or "\uF900" <= ch <= "\uFAFF" or "\uFE10" <= ch <= "\uFE6F" or "\uFF00" <= ch <= "\uFFEF":
            n += 2
        else:
            n += 1
    return n


def autosize_columns(ws, df: pd.DataFrame, max_width: int = 120, min_width: int = 10) -> None:
    """
    Auto-adjust Excel column widths based on the longest visible string in each column.
    Also disables header wrapping to avoid the "mean_m" wrapping issue.
    """
    # Disable wrap for header row (Excel may wrap when the column is slightly narrow)
    for cell in ws[1]:
        cell.alignment = Alignment(wrap_text=False, horizontal="center", vertical="center")

    for col_idx, col_name in enumerate(df.columns, start=1):
        col_values = df.iloc[:, col_idx - 1]
        max_len = _excel_display_len(str(col_name)) if col_name is not None else 0

        # Only scan a limited number of rows for speed (still enough for sizing)
        for v in col_values.astype(str).fillna("").head(2000).tolist():
            ln = _excel_display_len(v)
            if ln > max_len:
                max_len = ln

        # Provide some padding
        width = max_len + 4

        # Column-specific floors
        name = str(col_name)
        if name == "callback":
            width = max(width, 50)
        if name in ("mean_ms", "mean_m", "mean"):
            width = max(width, 12)

        width = max(min_width, min(max_width, width))
        col_letter = ws.cell(row=1, column=col_idx).column_letter
        ws.column_dimensions[col_letter].width = width


def clear_header_notes(ws) -> None:
    """Ensure header row has no comments/notes."""
    for cell in ws[1]:
        try:
            cell.comment = None
        except Exception:
            pass

def apply_excel_styles(ws, df_final: pd.DataFrame, flags: List[Dict[str, bool]]) -> None:
    """Apply red font styling as requested."""
    red = Font(color="FF0000")
    # Map header -> column number (1-based)
    header_map: Dict[str, int] = {}
    for col_idx, cell in enumerate(ws[1], start=1):
        header_map[str(cell.value)] = col_idx

    def _set_red(row_num: int, col_name: str) -> None:
        ci = header_map.get(col_name)
        if ci is None:
            return
        ws.cell(row=row_num, column=ci).font = red

    # Data rows start from 2
    for i, flg in enumerate(flags):
        excel_row = i + 2

        # KStest false => red KStest cell
        if flg.get("ks_fail", False):
            _set_red(excel_row, "KStest")

        # Rule 1 applied => pWCET, arctan, final_result_source, final_result red
        if flg.get("rule1", False):
            for c in ("pWCET", "arctan", "final_result_source", "final_result"):
                _set_red(excel_row, c)

        # Rule 2 applied => xi_shape, final_result_source, final_result red
        if flg.get("rule2", False):
            for c in ("xi_shape", "final_result_source", "final_result"):
                _set_red(excel_row, c)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate final_result.xlsx from HTML report + timestamp JSONs (single-file version)."
    )
    ap.add_argument("--index-html", default="report/index.html", help="Path to HTML report (default: report/index.html).")
    ap.add_argument("--json-glob", default="sampled_execution_time/*.json", help="Glob for timestamp JSONs (default: sampled_execution_time/*.json).")
    ap.add_argument("--percentile", type=float, default=95.0, help="Percentile (PPF) used in HTML (default: 95).")

    ap.add_argument(
        "--prob",
        type=float,
        default=None,
        help="Target exceedance probability for inequality (default: 1 - percentile/100). For 95%%, default is 0.05.",
    )
    ap.add_argument("--ineq-method", choices=["atan", "tanh", "both"], default="atan", help="Inequality method(s) (default: atan).")    
    ap.add_argument("--min-samples", type=int, default=50, help="Min samples per callback in inequality (default: 50).")
    ap.add_argument("--out", default="final_result.xlsx", help="Output Excel path (default: final_result.xlsx).")

    args = ap.parse_args()

    html_path = Path(args.index_html)
    json_paths = sorted(Path().glob(args.json_glob))

    if not html_path.is_file():
        _err(f"Missing HTML report: {html_path}")
    if not json_paths:
        _err(f"No JSON files matched: {args.json_glob}")

    prob = args.prob if args.prob is not None else default_prob_from_percentile(args.percentile)
    if not (0.0 < float(prob) < 1.0):
        _err(f"--prob must be in (0,1). Got: {prob}")

    df_html = parse_html_report(html_path, args.percentile)
    df_ineq = compute_ineq_from_jsons(json_paths, float(prob), args.ineq_method, args.min_samples)

    df_final, flags = build_final_table_and_flags(df_html, df_ineq, args.percentile)

    out_path = Path(args.out)
    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        df_final.to_excel(xw, sheet_name="final", index=False)

        # Styling (final sheet only)
        ws = xw.sheets["final"]
        ws.freeze_panes = "A2"
        clear_header_notes(ws)
        apply_excel_styles(ws, df_final, flags)
        autosize_columns(ws, df_final)

    print(f"[OK] Wrote: {out_path}")


if __name__ == "__main__":
    main()
