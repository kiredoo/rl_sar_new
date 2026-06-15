#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
summarize_exec_by_cb_topic.py
---------------------------------
從 out_matched.csv（含 dur_us 欄位）彙整「執行時間」統計：
- 依 (callback_name, topic_name) 分組：min/mean/median/p90/p95/p99/max/stdev/CV、n、obs_s、rate_hz
- 也會列出「觸發延遲」的相同統計（delta_us）供對照

用法：
  python3 summarize_exec_by_cb_topic.py --matched out_matched.csv --out stats_exec
"""
import argparse, pandas as pd, numpy as np

def pct(x, q): return np.percentile(x, q) if len(x) else float('nan')

def dur_and_rate(df):
    if "cb_time_ns" in df.columns and df["cb_time_ns"].notna().any():
        span = (df["cb_time_ns"].max() - df["cb_time_ns"].min())/1e9
    else:
        span = np.nan
    hz = len(df)/span if span and span>0 else np.nan
    return span, hz

def do_stats(df, col_ms):
    if df.empty: return {k: float('nan') for k in ("n","min","mean","median","p90","p95","p99","max","stdev","CV","obs_s","rate_hz")}
    x = df[col_ms].dropna().values
    obs_s, rate = dur_and_rate(df)
    return dict(
        n = int(len(x)),
        min = float(np.min(x)) if len(x) else float('nan'),
        mean = float(np.mean(x)) if len(x) else float('nan'),
        median = float(np.percentile(x,50)) if len(x) else float('nan'),
        p90 = float(np.percentile(x,90)) if len(x) else float('nan'),
        p95 = float(np.percentile(x,95)) if len(x) else float('nan'),
        p99 = float(np.percentile(x,99)) if len(x) else float('nan'),
        max = float(np.max(x)) if len(x) else float('nan'),
        stdev = float(np.std(x, ddof=1)) if len(x)>1 else 0.0,
        CV = (float(np.std(x, ddof=1))/float(np.mean(x))) if len(x)>1 and np.mean(x)!=0 else float('nan'),
        obs_s = float(obs_s) if obs_s==obs_s else float('nan'),
        rate_hz = float(hz) if (hz:=rate)==rate else float('nan'),
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matched", required=True)
    ap.add_argument("--out", default="stats_exec")
    args = ap.parse_args()

    df = pd.read_csv(args.matched)
    for c in ("dur_us","delta_us","cb_time_ns"):
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce")
    df["dur_ms"] = df["dur_us"]/1000.0
    df["lat_ms"] = df["delta_us"]/1000.0

    rows = []
    for (cb, tp), g in df.groupby(["callback_name","topic_name"]):
        # 執行時間
        s_exec = do_stats(g, "dur_ms")
        # 觸發延遲（供對照）
        s_lat  = do_stats(g, "lat_ms")
        rows.append(dict(callback_name=cb, topic_name=tp,
                         n=s_exec["n"],
                         exec_min_ms=s_exec["min"], exec_mean_ms=s_exec["mean"], exec_median_ms=s_exec["median"],
                         exec_p90_ms=s_exec["p90"], exec_p95_ms=s_exec["p95"], exec_p99_ms=s_exec["p99"], exec_max_ms=s_exec["max"],
                         exec_stdev_ms=s_exec["stdev"], exec_CV=s_exec["CV"],
                         latency_mean_ms=s_lat["mean"], latency_p95_ms=s_lat["p95"],
                         obs_s=s_exec["obs_s"], rate_hz=s_exec["rate_hz"]))
    out = pd.DataFrame(rows).sort_values(["callback_name","topic_name"])
    out.to_csv(f"{args.out}_cb-topic_exec.csv", index=False)
    print(f"[OK] 寫入 {args.out}_cb-topic_exec.csv（{len(out)} rows）")
    if not out.empty:
        print(out.head(10).to_string(index=False))

if __name__ == "__main__":
    main()
