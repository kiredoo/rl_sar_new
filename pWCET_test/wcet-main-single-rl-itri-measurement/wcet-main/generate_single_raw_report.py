#!/usr/bin/env python3
import argparse
import html
import json
import math
import statistics
from pathlib import Path


def percentile(sorted_vals, pct):
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pct = max(0.0, min(100.0, float(pct)))
    k = (len(sorted_vals) - 1) * pct / 100.0
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_vals[int(k)])
    return float(sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f))


def fmt_ns(v):
    if v is None:
        return "-"
    v = float(v)
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:.3f} ms"
    if abs(v) >= 1_000:
        return f"{v / 1_000:.3f} µs"
    return f"{v:.0f} ns"


def summarize(samples):
    vals = [float(x) for x in samples if x is not None]
    if not vals:
        return {
            "count": 0,
            "min": None,
            "median": None,
            "mean": None,
            "p95": None,
            "p99": None,
            "p999": None,
            "max": None,
            "stdev": None,
            "sorted": [],
        }

    vals_sorted = sorted(vals)
    return {
        "count": len(vals_sorted),
        "min": vals_sorted[0],
        "median": percentile(vals_sorted, 50),
        "mean": statistics.fmean(vals_sorted),
        "p95": percentile(vals_sorted, 95),
        "p99": percentile(vals_sorted, 99),
        "p999": percentile(vals_sorted, 99.9),
        "max": vals_sorted[-1],
        "stdev": statistics.stdev(vals_sorted) if len(vals_sorted) >= 2 else 0.0,
        "sorted": vals_sorted,
    }


def make_histogram(vals, bins=30):
    if not vals:
        return []
    lo, hi = min(vals), max(vals)
    if lo == hi:
        return [(lo, hi, len(vals))]

    width = (hi - lo) / bins
    counts = [0] * bins

    for v in vals:
        idx = int((v - lo) / width)
        if idx >= bins:
            idx = bins - 1
        counts[idx] += 1

    return [(lo + i * width, lo + (i + 1) * width, c) for i, c in enumerate(counts)]


def hist_html(vals):
    rows = make_histogram(vals)
    if not rows:
        return '<div class="muted">No samples</div>'

    max_count = max(c for _, _, c in rows) or 1
    parts = ['<div class="hist">']

    for lo, hi, c in rows:
        w = max(1.0, c / max_count * 100.0) if c else 0.0
        label = f"{fmt_ns(lo)} – {fmt_ns(hi)}"
        parts.append(
            '<div class="hist-row">'
            f'<div class="hist-label">{html.escape(label)}</div>'
            '<div class="hist-bar-wrap">'
            f'<div class="hist-bar" style="width:{w:.1f}%"></div>'
            '</div>'
            f'<div class="hist-count">{c}</div>'
            '</div>'
        )

    parts.append("</div>")
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser(
        description="Generate a single-run raw timing HTML report from WCET JSON."
    )
    ap.add_argument(
        "json_file",
        help="Input JSON, e.g. sampled_execution_time/20260505110751.json",
    )
    ap.add_argument(
        "-o",
        "--output",
        default="report/single_raw_report.html",
        help="Output HTML path",
    )
    ap.add_argument(
        "--top",
        type=int,
        default=30,
        help="How many callbacks/functions to show in top summary table",
    )
    args = ap.parse_args()

    json_path = Path(args.json_file)
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    callbacks = data.get("callbacks", [])
    unit = data.get("unit", "unknown")
    hostname = data.get("hostname", "unknown")
    sampling_time = data.get("sampling_time", "unknown")

    summaries = []
    for cb in callbacks:
        name = cb.get("name", "<unnamed>")
        samples = cb.get("samples", []) or []
        s = summarize(samples)
        summaries.append((name, samples, s))

    nonempty = [(name, samples, s) for name, samples, s in summaries if s["count"] > 0]
    empty = [(name, samples, s) for name, samples, s in summaries if s["count"] == 0]
    top_by_max = sorted(nonempty, key=lambda x: x[2]["max"], reverse=True)

    css = """
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      margin: 24px;
      color: #222;
    }
    h1 { margin-bottom: 0.2rem; }
    h2 {
      margin-top: 2rem;
      border-bottom: 1px solid #ddd;
      padding-bottom: 0.3rem;
    }
    .muted { color: #777; }
    .meta {
      background: #f7f7f7;
      padding: 12px 16px;
      border-radius: 8px;
      margin: 16px 0;
    }
    table {
      border-collapse: collapse;
      width: 100%;
      margin: 12px 0;
      font-size: 14px;
    }
    th, td {
      border: 1px solid #ddd;
      padding: 6px 8px;
      text-align: right;
    }
    th:first-child, td:first-child { text-align: left; }
    th { background: #f2f2f2; }
    .warn { color: #9a5b00; font-weight: 600; }
    .ok { color: #0a6b2b; font-weight: 600; }
    details {
      border: 1px solid #ddd;
      border-radius: 8px;
      padding: 8px 12px;
      margin: 10px 0;
    }
    summary { cursor: pointer; font-weight: 700; }
    .hist { margin: 10px 0; }
    .hist-row {
      display: grid;
      grid-template-columns: 180px 1fr 60px;
      gap: 8px;
      align-items: center;
      margin: 3px 0;
      font-size: 12px;
    }
    .hist-label { color: #555; text-align: right; }
    .hist-bar-wrap {
      background: #eee;
      height: 14px;
      border-radius: 4px;
      overflow: hidden;
    }
    .hist-bar { background: #5d7fa3; height: 100%; }
    .hist-count { text-align: right; color: #555; }
    code {
      background: #f4f4f4;
      padding: 1px 4px;
      border-radius: 3px;
    }
    """

    def stat_row(name, s):
        return (
            "<tr>"
            f"<td>{html.escape(name)}</td>"
            f"<td>{s['count']}</td>"
            f"<td>{fmt_ns(s['min'])}</td>"
            f"<td>{fmt_ns(s['median'])}</td>"
            f"<td>{fmt_ns(s['mean'])}</td>"
            f"<td>{fmt_ns(s['p95'])}</td>"
            f"<td>{fmt_ns(s['p99'])}</td>"
            f"<td>{fmt_ns(s['p999'])}</td>"
            f"<td>{fmt_ns(s['max'])}</td>"
            f"<td>{fmt_ns(s['stdev'])}</td>"
            "</tr>"
        )

    top_rows = "\n".join(stat_row(name, s) for name, samples, s in top_by_max[: args.top])
    empty_rows = "\n".join(f"<li><code>{html.escape(name)}</code></li>" for name, _, _ in empty)

    details_parts = []
    for name, samples, s in top_by_max:
        details_parts.append(
            f"<details>"
            f"<summary>{html.escape(name)} — {s['count']} samples, max {fmt_ns(s['max'])}</summary>"
            "<table>"
            "<tr>"
            "<th>count</th><th>min</th><th>median</th><th>mean</th>"
            "<th>p95</th><th>p99</th><th>p99.9</th><th>max</th><th>stdev</th>"
            "</tr>"
            f"<tr>"
            f"<td>{s['count']}</td>"
            f"<td>{fmt_ns(s['min'])}</td>"
            f"<td>{fmt_ns(s['median'])}</td>"
            f"<td>{fmt_ns(s['mean'])}</td>"
            f"<td>{fmt_ns(s['p95'])}</td>"
            f"<td>{fmt_ns(s['p99'])}</td>"
            f"<td>{fmt_ns(s['p999'])}</td>"
            f"<td>{fmt_ns(s['max'])}</td>"
            f"<td>{fmt_ns(s['stdev'])}</td>"
            f"</tr>"
            "</table>"
            f"{hist_html(s['sorted'])}"
            "</details>"
        )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Single-run raw timing report</title>
<style>{css}</style>
</head>
<body>
<h1>Single-run raw timing report</h1>

<div class="meta">
  <div><b>Input:</b> <code>{html.escape(str(json_path))}</code></div>
  <div><b>Hostname:</b> {html.escape(str(hostname))}</div>
  <div><b>Sampling time:</b> {html.escape(str(sampling_time))}</div>
  <div><b>Unit:</b> {html.escape(str(unit))}</div>
  <div><b>Callbacks/functions:</b> {len(callbacks)} total,
    <span class="ok">{len(nonempty)} with samples</span>,
    <span class="warn">{len(empty)} empty</span>
  </div>
</div>

<p class="muted">
This report is for single-run raw observation only.
It does not perform EVT / GEV / IESTA pWCET fitting.
Use the original wcet_utils.py report only after installing the statistical dependencies
and collecting enough repeated runs.
</p>

<h2>Top callbacks/functions by observed max</h2>
<table>
<tr>
  <th>name</th>
  <th>count</th>
  <th>min</th>
  <th>median</th>
  <th>mean</th>
  <th>p95</th>
  <th>p99</th>
  <th>p99.9</th>
  <th>max</th>
  <th>stdev</th>
</tr>
{top_rows}
</table>

<h2>Empty callbacks/functions</h2>
<ul>{empty_rows if empty_rows else '<li>None</li>'}</ul>

<h2>Detailed histograms</h2>
{''.join(details_parts)}

</body>
</html>
"""

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_doc, encoding="utf-8")
    print(f"Generated: {out}")


if __name__ == "__main__":
    main()
