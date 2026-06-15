#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ebpf_perf_callback_nine_one_shot_et_prio.py
==================================================
單檔一鍵（ET 版，保留 priority-by-input）：
- eBPF 追蹤 callback **進入**與**返回**（uretprobe），計算 **ET = RT − Σ(syscall)**
- 優先使用 tracepoints: raw_syscalls:sys_enter/sys_exit；若不可用，自動 fallback 到 kprobe/kretprobe（常見 __x64_sys_* / __arm64_sys_*）
- ROS 2 同時訂閱多個 topic 記錄到達時間
- 依「topic→callback」配對（支援 priority-by-input / pairwise-offset / exclusive）
- 將 ET（dur_us / dur_ms）JOIN 回配對結果（以 entry_ts + pid + tid 對齊）

輸出（以 --out-prefix 為前綴）：
  <prefix>_cb.csv       : ts_ktime_ns, callback_name, pid, tid
  <prefix>_cb_dur.csv   : ts_entry_ns, dur_us(=ET), callback_name, pid, tid
  <prefix>_topic.csv    : t_wall_ns, topic_name, header_stamp_ns
  <prefix>_matched.csv  : cb_time_ns, callback_name, topic_name, topic_time_ns, delta_us, confidence, pid, tid, header_stamp_ns, dur_us(=ET), dur_ms

建議：
  sudo -E python3 ebpf_perf_callback_nine_one_shot_et_prio.py \
    --callback-list-file callbacks.txt \
    --proc-filter autoware \
    --topic-spec /sensing/lidar/top/rectified/pointcloud_ex:sensor_msgs/msg/PointCloud2 \
    --topic-spec /sensing/lidar/left/rectified/pointcloud_ex:sensor_msgs/msg/PointCloud2 \
    --topic-spec /sensing/lidar/right/rectified/pointcloud_ex:sensor_msgs/msg/PointCloud2 \
    --priority-by-input --prefer earlier --threshold-ms 5 --pairwise-offset \
    --out-prefix run_et

可選：
  --mapping mapping.json        # 限制 callback_name → 允許的 topics（白名單）
  --pid <PID>                   # 只跟蹤特定進程
  --pairwise-offset             # 以 (callback, topic) 各自估 offset 對齊
"""

import argparse
import csv
import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from bcc import BPF

# ROS 2
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from rosidl_runtime_py.utilities import get_message

# ---------------- CLI ----------------
def build_arg_parser():
    p = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--callback-list-file", "--callback_names_txt", "--callbacks_txt",
                   dest="callback_list_file", required=True)
    p.add_argument("--proc-filter", default="autoware")
    p.add_argument("--pid", type=int, default=-1)

    g_topics = p.add_mutually_exclusive_group(required=True)
    g_topics.add_argument("--topic-spec", action="append",
                          help="可多次指定：<topic>:<msg_type>")
    g_topics.add_argument("--topics-json")

    p.add_argument("--duration", type=int, default=0, help="擷取秒數（0=直到 Ctrl-C）")
    p.add_argument("--threshold-ms", type=float, default=30.0, help="配對時間窗（毫秒）")
    p.add_argument("--prefer", choices=["earlier","nearest"], default="nearest")
    p.add_argument("--mapping", help="JSON：callback_name → [topic,...]")
    p.add_argument("--out-prefix", default="out")
    p.add_argument("--pairwise-offset", action="store_true",
                   help="以 (callback, topic) 各自估 offset 再配對，降低系統性偏移")
    # 注意：原設計用 --exclusive/--no-exclusive，比較正確；此處保持相容，預設 True
    p.add_argument("--exclusive", action="store_true", default=True,
                   help="啟用一對一（消耗式）配對：同一個 (topic_name, topic_time_ns) 只配一次")

    p.add_argument("--priority-by-input", action="store_true",
                   help="依 --topic-spec / --topics-json 的 topic 輸入順序進行『先輸入先配對』的主題優先配對")
    return p

# ---------------- Utils ----------------
def now_wall_ns() -> int:
    return time.perf_counter_ns()

def ensure_parent_dir(path: str):
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

# ---------------- eBPF helpers ----------------
def find_so_files_with_lsof(grep_key: str) -> List[str]:
    try:
        out = subprocess.check_output(f"sudo lsof | grep {grep_key}", shell=True, text=True, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return []
    so_files = set()
    pat = re.compile(r"\s(/[^ \n]+)")
    for line in out.splitlines():
        m = pat.search(line)
        if not m:
            continue
        path = m.group(1)
        if os.path.splitext(path)[1].startswith(".so") and os.path.exists(path):
            so_files.add(path)
    return sorted(so_files)

def nm_symbols(paths: List[str]) -> Dict[str, str]:
    out = {}
    for pth in paths:
        try:
            nm = subprocess.check_output(f"nm --defined-only {pth}", shell=True, text=True)
        except subprocess.CalledProcessError:
            continue
        out[pth] = nm
    return out

def resolve_callbacks(callback_names: List[str], nm_map: Dict[str, str]):
    found = []
    for cb in callback_names:
        parts = cb.split("::")
        if len(parts) < 2:
            print(f"[WARN] 無法解析 callback 名稱：{cb}")
            continue
        cls, fn = parts[-2], parts[-1]
        pat = re.compile(rf"\b([0-9a-fA-F]+)\s+T\s+(_?Z[^\s]*{re.escape(cls)}[^\s]*{re.escape(fn)}[^\s]*)\b")
        hit = None
        for so_path, nm_out in nm_map.items():
            m = pat.search(nm_out)
            if m:
                hit = (so_path, cb, m.group(2)); break
        if hit: print(f"[OK] {cb} => {hit[2]} @ {hit[0]}"); found.append(hit)
        else:   print(f"[MISS] 找不到符號：{cb}")
    return found


def build_bpf(num_callbacks: int) -> BPF:
    # 注意：不是 f-string，避免 C 程式中的 { } 觸發 Python 格式化
    prog = """
    #include <uapi/linux/ptrace.h>
    #include <linux/sched.h>

    struct key_t { u32 tid; int cbid; };

    // event (etype: 0=entry, 1=exit with dur_ns=ET)
    struct evt_t {
        u32 pid;
        u32 tid;
        u64 ts_ns;
        int cbid;
        u64 dur_ns;
        u8  etype;
    };

    // per-thread/per-callback start ts
    BPF_HASH(start_ns, struct key_t, u64);

    // thread currently inside a callback (key: pid_tgid)
    BPF_HASH(cb_active, u64, u64);

    // syscall accounting (key: pid_tgid)
    BPF_HASH(sys_start, u64, u64);   // last syscall start
    BPF_HASH(sys_accum, u64, u64);   // accumulated syscall time within current callback

    BPF_PERF_OUTPUT(events);

    static __always_inline int submit_entry(struct pt_regs *ctx, int cbid) {
        u64 ts = bpf_ktime_get_ns();
        u64 pid_tgid = bpf_get_current_pid_tgid();

        // mark inside-callback and reset syscall accounting
        cb_active.update(&pid_tgid, &ts);
        u64 zero = 0;
        sys_accum.update(&pid_tgid, &zero);
        sys_start.delete(&pid_tgid);

        struct key_t k = { .tid=(u32)pid_tgid, .cbid=cbid };
        start_ns.update(&k, &ts);

        struct evt_t e = {};
        e.pid = pid_tgid >> 32;
        e.tid = (u32)pid_tgid;
        e.ts_ns = ts;
        e.cbid = cbid;
        e.dur_ns = 0;
        e.etype = 0;
        events.perf_submit(ctx, &e, sizeof(e));
        return 0;
    }

    static __always_inline int submit_exit(struct pt_regs *ctx, int cbid) {
        u64 ts1 = bpf_ktime_get_ns();
        u64 pid_tgid = bpf_get_current_pid_tgid();

        struct key_t k = { .tid=(u32)pid_tgid, .cbid=cbid };
        u64 *ts0p = start_ns.lookup(&k);
        if (!ts0p) return 0;

        u64 resp = ts1 - *ts0p;
        u64 *accp = sys_accum.lookup(&pid_tgid);
        u64 acc = accp ? *accp : 0;
        u64 et = resp > acc ? (resp - acc) : 0;  // ET = response - sum(syscalls)

        // clear state
        start_ns.delete(&k);
        cb_active.delete(&pid_tgid);
        sys_start.delete(&pid_tgid);
        sys_accum.delete(&pid_tgid);

        struct evt_t e = {};
        e.pid = pid_tgid >> 32;
        e.tid = (u32)pid_tgid;
        e.ts_ns = *ts0p;
        e.cbid = cbid;
        e.dur_ns = et;
        e.etype = 1;
        events.perf_submit(ctx, &e, sizeof(e));
        return 0;
    }

    // ---------- Preferred: tracepoints raw_syscalls:* ----------
    TRACEPOINT_PROBE(raw_syscalls, sys_enter) {
        u64 pid_tgid = bpf_get_current_pid_tgid();
        u64 *act = cb_active.lookup(&pid_tgid);
        if (!act) return 0;  // only when inside a callback
        u64 now = bpf_ktime_get_ns();
        sys_start.update(&pid_tgid, &now);
        return 0;
    }

    TRACEPOINT_PROBE(raw_syscalls, sys_exit) {
        u64 pid_tgid = bpf_get_current_pid_tgid();
        u64 *act = cb_active.lookup(&pid_tgid);
        if (!act) return 0;
        u64 *ps = sys_start.lookup(&pid_tgid);
        if (!ps) return 0;
        u64 now = bpf_ktime_get_ns();
        u64 dur = now - *ps;
        u64 *acc = sys_accum.lookup(&pid_tgid);
        if (acc) {
            u64 new_acc = *acc + dur;
            sys_accum.update(&pid_tgid, &new_acc);
        } else {
            sys_accum.update(&pid_tgid, &dur);
        }
        return 0;
    }

    // ---------- Fallback: kprobe/kretprobe on common syscalls ----------
    int kp_sys_enter(struct pt_regs *ctx) {
        u64 pid_tgid = bpf_get_current_pid_tgid();
        u64 *act = cb_active.lookup(&pid_tgid);
        if (!act) return 0;
        u64 now = bpf_ktime_get_ns();
        sys_start.update(&pid_tgid, &now);
        return 0;
    }

    int kr_sys_exit(struct pt_regs *ctx) {
        u64 pid_tgid = bpf_get_current_pid_tgid();
        u64 *act = cb_active.lookup(&pid_tgid);
        if (!act) return 0;
        u64 *ps = sys_start.lookup(&pid_tgid);
        if (!ps) return 0;
        u64 now = bpf_ktime_get_ns();
        u64 dur = now - *ps;
        u64 *acc = sys_accum.lookup(&pid_tgid);
        if (acc) {
            u64 new_acc = *acc + dur;
            sys_accum.update(&pid_tgid, &new_acc);
        } else {
            sys_accum.update(&pid_tgid, &dur);
        }
        return 0;
    }
    """
    for i in range(num_callbacks):
        prog += f"int cb_in_{i}(struct pt_regs *ctx) {{ return submit_entry(ctx, {i}); }}\n"
        prog += f"int cb_out_{i}(struct pt_regs *ctx) {{ return submit_exit(ctx, {i}); }}\n"
    return BPF(text=prog)


# ---------------- ROS 2 multi-subscriber ----------------
@dataclass
class TopicSpec:
    name: str
    type_str: str

class MultiTopicLogger(Node):
    def __init__(self, specs: List[TopicSpec], out_path: str):
        super().__init__('multi_topic_logger_dur')
        self.out_path = out_path
        ensure_parent_dir(out_path)
        self.fp = open(out_path, "w", newline="")
        self.csv = csv.writer(self.fp)
        self.csv.writerow(["t_wall_ns", "topic_name", "header_stamp_ns"])

        qos = QoSProfile(depth=200)
        qos.reliability = ReliabilityPolicy.BEST_EFFORT
        qos.history = HistoryPolicy.KEEP_LAST

        self.subs = []
        for s in specs:
            Msg = get_message(s.type_str)
            self.subs.append(self.create_subscription(Msg, s.name, self._make_cb(s.name), qos))
        self.get_logger().info(f"Topic logging → {os.path.abspath(out_path)} ({len(self.subs)} subs)")

    def _make_cb(self, topic):
        count = {"n": 0}
        def _cb(msg):
            t = now_wall_ns()
            stamp_ns = ""
            try:
                stamp_ns = int(msg.header.stamp.sec) * 1_000_000_000 + int(msg.header.stamp.nanosec)
            except Exception:
                pass
            self.csv.writerow([t, topic, stamp_ns])
            count["n"] += 1
            if count["n"] % 100 == 0:
                self.fp.flush()
        return _cb

    def close(self):
        try:
            if not self.fp.closed:
                self.fp.flush(); self.fp.close()
        finally:
            pass

# ---------------- Matching & Analysis ----------------
def estimate_offset_ns(cb_ts: np.ndarray, topic_ts: np.ndarray) -> int:
    if len(cb_ts) == 0 or len(topic_ts) == 0:
        return 0
    topic_sorted = np.sort(topic_ts)
    diffs = []
    step = max(1, len(cb_ts)//2000)
    for t in cb_ts[::step]:
        idx = np.searchsorted(topic_sorted, t)
        cands = []
        if idx > 0: cands.append(topic_sorted[idx-1])
        if idx < len(topic_sorted): cands.append(topic_sorted[idx])
        if cands:
            closest = min(cands, key=lambda x: abs(t-x))
            diffs.append(int(t-closest))
    return int(np.median(diffs)) if diffs else 0

def confidence(abs_delta_ns: int, thr_ns: int) -> str:
    if abs_delta_ns <= thr_ns // 4: return "high"
    if abs_delta_ns <= thr_ns // 2: return "medium"
    return "low"

def match_groups(cb_df: pd.DataFrame, topics_df: pd.DataFrame, thr_ns: int, prefer: str,
                 mapping: Dict[str, List[str]], pairwise_offset: bool,
                 exclusive: bool, used_keys: Optional[set]) -> pd.DataFrame:
    out_rows = []
    for cb_name, cb_g in cb_df.groupby("callback_name"):
        if cb_g.empty: continue

        # 候選 topic（白名單）
        if mapping and cb_name in mapping:
            t_all = topics_df[topics_df["topic_name"].isin(mapping[cb_name])][["t_wall_ns","topic_name","header_stamp_ns"]].copy()
        else:
            t_all = topics_df[["t_wall_ns","topic_name","header_stamp_ns"]].copy()
        if t_all.empty: continue

        # 逐 topic 子群（pairwise offset：對每組 (cb, topic) 各自估 offset）
        topic_groups = [("**ALL**", t_all)] if not pairwise_offset else list(t_all.groupby("topic_name"))
        for _, t_df in topic_groups:
            if t_df.empty: continue
            # 對齊（全域 or 局部）
            off = estimate_offset_ns(cb_g["ts_ktime_ns"].to_numpy(dtype=np.int64),
                                     t_df["t_wall_ns"].to_numpy(dtype=np.int64))
            t_df = t_df.copy()
            t_df["t_wall_ns"] = t_df["t_wall_ns"].astype(np.int64) + int(off)
            t_df = t_df.sort_values("t_wall_ns").reset_index(drop=True)
            topic_times = t_df["t_wall_ns"].to_numpy(dtype=np.int64)

            for _, r in cb_g.sort_values("ts_ktime_ns").iterrows():
                t_cb_ns = int(r["ts_ktime_ns"])
                idx = int(np.searchsorted(topic_times, t_cb_ns, side="left"))
                cands = []

                if prefer == "earlier":
                    j = idx-1
                    if j >= 0:
                        dt = t_cb_ns - int(topic_times[j])
                        if 0 <= dt <= thr_ns:
                            cands.append(j)
                else:  # nearest
                    left = idx-1
                    if left >= 0:
                        dt = t_cb_ns - int(topic_times[left])
                        if 0 <= dt <= thr_ns: cands.append(left)
                    right = idx
                    if right < len(topic_times):
                        dt2 = int(topic_times[right]) - t_cb_ns
                        if 0 <= dt2 <= thr_ns: cands.append(right)

                if not cands:
                    continue
                # 選 |Δ| 最小，且（若 exclusive）該 topic 事件尚未被使用
                best = None
                best_abs = None
                best_delta = None
                best_row = None
                for j in cands:
                    t_topic_j = int(topic_times[j])
                    key = (str(t_df.iloc[j]["topic_name"]), t_topic_j)
                    if exclusive and used_keys is not None and key in used_keys:
                        continue
                    d = t_cb_ns - t_topic_j
                    ad = abs(d)
                    if (best is None) or (ad < best_abs):
                        best = j; best_abs = ad; best_delta = d; best_row = t_df.iloc[j]
                if best is None:
                    continue
                # 標記本 topic 事件已使用（exclusive 模式）
                if exclusive and used_keys is not None:
                    used_keys.add((str(best_row["topic_name"]), int(topic_times[best])))
                delta = best_delta
                tt = best_row
                out_rows.append({
                    "cb_time_ns": t_cb_ns,
                    "callback_name": cb_name,
                    "topic_name": tt["topic_name"],
                    "topic_time_ns": int(tt["t_wall_ns"]),
                    "delta_us": float(delta/1000.0),
                    "confidence": confidence(abs(int(delta)), thr_ns),
                    "pid": int(r.get("pid", -1)),
                    "tid": int(r.get("tid", -1)),
                    "header_stamp_ns": int(tt["header_stamp_ns"]) if str(tt["header_stamp_ns"]).strip() != "" else ""
                })
    return pd.DataFrame(out_rows)


def match_groups_priority(cb_df: pd.DataFrame,
                          topics_df: pd.DataFrame,
                          thr_ns: int,
                          prefer: str,
                          mapping: Dict[str, List[str]],
                          pairwise_offset: bool,
                          exclusive: bool,
                          used_keys: Optional[set],
                          priority_topics: List[str]) -> pd.DataFrame:
    """
    Topic-first greedy matching by priority order.
    Earlier topics in `priority_topics` claim eligible callbacks first.
    """
    if cb_df.empty or topics_df.empty or not priority_topics:
        return pd.DataFrame(columns=[
            "cb_time_ns","callback_name","topic_name","topic_time_ns",
            "delta_us","confidence","pid","tid","header_stamp_ns"
        ])

    cb_df = cb_df.sort_values("ts_ktime_ns").reset_index(drop=True).copy()
    cb_df["__used__"] = False
    cb_groups = {name: g.copy() for name, g in cb_df.groupby("callback_name")}

    topics_df = topics_df.copy()
    topics_df["t_wall_ns"] = topics_df["t_wall_ns"].astype("int64")
    topics_by_name = {t: df.copy().sort_values("t_wall_ns").reset_index(drop=True)
                      for t, df in topics_df.groupby("topic_name")}

    offsets = {}
    if pairwise_offset:
        for tname, tdf in topics_by_name.items():
            t_arr = tdf["t_wall_ns"].to_numpy(dtype=np.int64)
            for cb_name, cg in cb_groups.items():
                if mapping and (cb_name in mapping) and (tname not in set(mapping[cb_name])):
                    continue
                c_arr = cg["ts_ktime_ns"].to_numpy(dtype=np.int64)
                off = estimate_offset_ns(c_arr, t_arr)
                offsets[(cb_name, tname)] = int(off)

    out_rows = []
    for pri_t in priority_topics:
        if pri_t not in topics_by_name:
            continue
        tdf = topics_by_name[pri_t]
        if tdf.empty:
            continue
        for _, trow in tdf.iterrows():
            t_ns = int(trow["t_wall_ns"])
            best_idx = None
            best_abs = None
            best_delta = None
            best_cb_row = None
            best_cb_name = None

            for cb_name, cg in cb_groups.items():
                if mapping and (cb_name in mapping) and (pri_t not in set(mapping[cb_name])):
                    continue

                times = cg["ts_ktime_ns"].to_numpy(dtype=np.int64)
                off = offsets.get((cb_name, pri_t), 0) if pairwise_offset else 0
                t_adj = t_ns + off
                idx = int(np.searchsorted(times, t_adj, side="left"))

                candidates = []
                if prefer == "earlier":
                    j = idx
                    if j < len(times):
                        dt = int(times[j] - t_adj)
                        if 0 <= dt <= thr_ns:
                            gi = cg.index[j]
                            if not bool(cb_df.loc[gi, "__used__"]):
                                candidates.append((j, dt, gi))
                else:
                    left = idx - 1
                    if left >= 0:
                        dt = int(t_adj - times[left])
                        if 0 <= dt <= thr_ns:
                            gi = cg.index[left]
                            if not bool(cb_df.loc[gi, "__used__"]):
                                candidates.append((left, -dt, gi))
                    right = idx
                    if right < len(times):
                        dt2 = int(times[right] - t_adj)
                        if 0 <= dt2 <= thr_ns:
                            gi = cg.index[right]
                            if not bool(cb_df.loc[gi, "__used__"]):
                                candidates.append((right, dt2, gi))

                if not candidates:
                    continue

                for j, d, gi in candidates:
                    ad = abs(d)
                    if (best_idx is None) or (ad < best_abs) or (ad == best_abs and d < (best_delta or 1<<62)):
                        best_idx = gi
                        best_abs = ad
                        best_delta = d
                        best_cb_row = cb_df.loc[gi]
                        best_cb_name = cb_name

            if best_idx is None:
                continue

            cb_df.loc[best_idx, "__used__"] = True
            if exclusive and used_keys is not None:
                used_keys.add((str(pri_t), t_ns))
            raw_delta = int(best_cb_row["ts_ktime_ns"]) - t_ns
            out_rows.append({
                "cb_time_ns": int(best_cb_row["ts_ktime_ns"]),
                "callback_name": str(best_cb_name),
                "topic_name": str(pri_t),
                "topic_time_ns": t_ns,
                "delta_us": float(raw_delta/1000.0),
                "confidence": confidence(abs(raw_delta), thr_ns),
                "pid": int(best_cb_row.get("pid", -1)),
                "tid": int(best_cb_row.get("tid", -1)),
                "header_stamp_ns": int(trow["header_stamp_ns"]) if str(trow["header_stamp_ns"]).strip() != "" else ""
            })

    if not out_rows:
        return pd.DataFrame(columns=[
            "cb_time_ns","callback_name","topic_name","topic_time_ns",
            "delta_us","confidence","pid","tid","header_stamp_ns"
        ])
    return pd.DataFrame(out_rows)


# ---------------- main ----------------
def main():
    parser = build_arg_parser()
    args, _ = parser.parse_known_args()

    thr_ns = int(args.threshold_ms * 1_000_000)

    # callbacks
    callbacks = [line.strip() for line in open(args.callback_list_file, "r", encoding="utf-8") if line.strip()]
    if not callbacks:
        print("[ERR] callbacks.txt 為空"); return 2

    # topics
    specs: List[TopicSpec] = []
    if args.topic_spec:
        for s in args.topic_spec:
            if ":" not in s:
                print(f"[ERR] topic-spec 格式錯誤：{s}"); return 3
            t, ty = s.split(":", 1); specs.append(TopicSpec(t, ty))
    else:
        with open(args.topics_json, "r", encoding="utf-8") as f:
            mp = json.load(f)
        for k, v in mp.items():
            specs.append(TopicSpec(k, v))

    # resolve callbacks
    so_paths = find_so_files_with_lsof(args.proc_filter)
    if not so_paths:
        print(f"[ERR] lsof 找不到含「{args.proc_filter}」的動態庫；請確認目標程式正在執行。"); return 5
    nm_map = nm_symbols(so_paths)
    cb_resolved = resolve_callbacks(callbacks, nm_map)
    if not cb_resolved:
        print("[ERR] 沒有任何 callback 被解析成功。"); return 6

    # bpf & attach (entry + return)
    b = build_bpf(len(cb_resolved))
    name_map = {i: pretty for i, (_, pretty, _) in enumerate(cb_resolved)}
    for cbid, (so_path, pretty, mangled) in enumerate(cb_resolved):
        try:
            b.attach_uprobe(name=so_path, sym=mangled, fn_name=f"cb_in_{cbid}", pid=args.pid)
            b.attach_uretprobe(name=so_path, sym=mangled, fn_name=f"cb_out_{cbid}", pid=args.pid)
        except Exception as e:
            print(f"[ERR] attach uprobe/uretprobe 失敗：{pretty} @ {so_path} ({e})")

    # attach syscall accounting: prefer tracepoints, fallback to kprobes
    try:
        b.attach_tracepoint(tp="raw_syscalls:sys_enter", fn_name="tracepoint__raw_syscalls__sys_enter")
        b.attach_tracepoint(tp="raw_syscalls:sys_exit",  fn_name="tracepoint__raw_syscalls__sys_exit")
        print("[BPF] Syscall accounting via raw_syscalls tracepoints")
    except Exception as e:
        print(f"[WARN] raw_syscalls tracepoints unavailable: {e}. Falling back to kprobes.")
        arch = platform.machine().lower()
        if 'x86_64' in arch or 'amd64' in arch:
            SYSCALLS = [
                "__x64_sys_read","__x64_sys_write","__x64_sys_pread64","__x64_sys_pwrite64",
                "__x64_sys_recvfrom","__x64_sys_recvmsg","__x64_sys_sendto","__x64_sys_sendmsg",
                "__x64_sys_poll","__x64_sys_ppoll","__x64_sys_select","__x64_sys_pselect6",
                "__x64_sys_epoll_wait","__x64_sys_epoll_pwait",
                "__x64_sys_nanosleep","__x64_sys_clock_nanosleep",
                "__x64_sys_ioctl","__x64_sys_futex",
                "__x64_sys_open","__x64_sys_openat","__x64_sys_close"
            ]
        else:
            SYSCALLS = [
                "__arm64_sys_read","__arm64_sys_write","__arm64_sys_pread64","__arm64_sys_pwrite64",
                "__arm64_sys_recvfrom","__arm64_sys_recvmsg","__arm64_sys_sendto","__arm64_sys_sendmsg",
                "__arm64_sys_poll","__arm64_sys_ppoll","__arm64_sys_select","__arm64_sys_pselect6",
                "__arm64_sys_epoll_wait","__arm64_sys_epoll_pwait",
                "__arm64_sys_nanosleep","__arm64_sys_clock_nanosleep",
                "__arm64_sys_ioctl","__arm64_sys_futex",
                "__arm64_sys_openat","__arm64_sys_close"
            ]
        ok = 0
        for sym in SYSCALLS:
            try:
                b.attach_kprobe(event=sym, fn_name="kp_sys_enter")
                b.attach_kretprobe(event=sym, fn_name="kr_sys_exit")
                ok += 1
            except Exception:
                pass
        print(f"[BPF] kprobe fallback attached on {ok} syscall symbols")

    # outputs
    cb_csv = f"{args.out_prefix}_cb.csv"
    cb_dur_csv = f"{args.out_prefix}_cb_dur.csv"
    topic_csv = f"{args.out_prefix}_topic.csv"
    matched_csv = f"{args.out_prefix}_matched.csv"
    for pth in (cb_csv, cb_dur_csv, topic_csv, matched_csv): ensure_parent_dir(pth)

    cb_fp = open(cb_csv, "w", newline=""); cb_writer = csv.writer(cb_fp)
    cb_writer.writerow(["ts_ktime_ns", "callback_name", "pid", "tid"])

    cbd_fp = open(cb_dur_csv, "w", newline=""); cbd_writer = csv.writer(cbd_fp)
    cbd_writer.writerow(["ts_entry_ns", "dur_us", "callback_name", "pid", "tid"])

    # perf buffer
    stop_evt = threading.Event()
    def on_event(cpu, data, size):
        evt = b["events"].event(data)
        if evt.etype == 0:  # entry
            cb_writer.writerow([int(evt.ts_ns), name_map.get(evt.cbid, f"cb#{evt.cbid}"), int(evt.pid), int(evt.tid)])
            cb_fp.flush()
        else:  # exit with dur (ET)
            cbd_writer.writerow([int(evt.ts_ns), float(evt.dur_ns/1000.0), name_map.get(evt.cbid, f"cb#{evt.cbid}"), int(evt.pid), int(evt.tid)])
            cbd_fp.flush()

    b["events"].open_perf_buffer(on_event, page_cnt=64)  # 大 buffer

    def perf_loop():
        while not stop_evt.is_set():
            try: b.perf_buffer_poll(timeout=50)  # 勤快輪詢
            except KeyboardInterrupt: break
    t_perf = threading.Thread(target=perf_loop, daemon=True); t_perf.start()

    # ROS2 node thread
    rclpy.init(args=None)
    node = MultiTopicLogger(specs, topic_csv)
    def spin_node():
        try: rclpy.spin(node)
        except KeyboardInterrupt: pass
    t_ros = threading.Thread(target=spin_node, daemon=True); t_ros.start()

    # wait duration or Ctrl-C
    print("[RUN] 量測中… Ctrl-C 可結束")
    end_ts = 0 if args.duration <= 0 else (datetime.now().timestamp() + args.duration)
    try:
        while True:
            time.sleep(0.25)
            if end_ts and datetime.now().timestamp() >= end_ts:
                break
    except KeyboardInterrupt:
        pass

    # cleanup
    stop_evt.set(); time.sleep(0.6)
    try: node.close(); node.destroy_node()
    except Exception: pass
    try: rclpy.shutdown()
    except Exception: pass
    cb_fp.close(); cbd_fp.close()

    print(f"[SAVE] callbacks(entry) → {os.path.abspath(cb_csv)}")
    print(f"[SAVE] callbacks(dur)   → {os.path.abspath(cb_dur_csv)}")
    print(f"[SAVE] topics           → {os.path.abspath(topic_csv)}")

    # post-processing: match + join ET
    cb = pd.read_csv(cb_csv)
    topics = pd.read_csv(topic_csv)
    cbd = pd.read_csv(cb_dur_csv)

    if cb.empty or topics.empty or cbd.empty:
        print("[WARN] 缺資料，略過配對"); open(matched_csv, "w").close(); return 0

    # 正規欄位
    cb.rename(columns={"ts_ktime_ns":"ts_ktime_ns"}, inplace=True)
    topics.rename(columns={"t_wall_ns":"t_wall_ns","topic":"topic_name","header_stamp_ns":"header_stamp_ns"}, inplace=True)

    # mapping（如有）
    mapping: Dict[str, List[str]] = {}
    if args.mapping:
        try:
            with open(args.mapping, "r", encoding="utf-8") as f:
                mapping = json.load(f)
        except Exception as e:
            print(f"[WARN] 讀 mapping 失敗：{e}")
    used_keys = set() if args.exclusive else None

    # priority topics: use input order if requested
    prio_topics: List[str] = []
    if args.priority_by_input:
        prio_topics = [s.name for s in specs]
        try:
            present = set(topics["topic_name"].astype(str).unique().tolist())
            prio_topics = [t for t in prio_topics if t in present]
        except Exception:
            pass

    # do the matching
    if args.priority_by_input and prio_topics:
        matched = match_groups_priority(
            cb, topics,
            thr_ns=int(args.threshold_ms*1_000_000),
            prefer=str(args.prefer),
            mapping=mapping,
            pairwise_offset=bool(args.pairwise_offset),
            exclusive=bool(args.exclusive),
            used_keys=used_keys,
            priority_topics=prio_topics
        )
    else:
        matched = match_groups(
            cb, topics,
            thr_ns=int(args.threshold_ms*1_000_000),
            prefer=str(args.prefer),
            mapping=mapping,
            pairwise_offset=bool(args.pairwise_offset),
            exclusive=bool(args.exclusive),
            used_keys=used_keys
        )

    if matched.empty:
        matched.to_csv(matched_csv, index=False); print(f"[DONE] 配對結果 → {os.path.abspath(matched_csv)}  共 0 筆"); return 0

    # 把 ET JOIN 進來（以 entry ts + pid + tid 做嚴格對應）
    cbd["ts_entry_ns"] = pd.to_numeric(cbd["ts_entry_ns"], errors="coerce").astype("Int64")
    cbd["pid"] = pd.to_numeric(cbd["pid"], errors="coerce").astype("Int64")
    cbd["tid"] = pd.to_numeric(cbd["tid"], errors="coerce").astype("Int64")

    matched["cb_time_ns"] = pd.to_numeric(matched["cb_time_ns"], errors="coerce").astype("Int64")
    matched["pid"] = pd.to_numeric(matched["pid"], errors="coerce").astype("Int64")
    matched["tid"] = pd.to_numeric(matched["tid"], errors="coerce").astype("Int64")

    out = matched.merge(cbd, left_on=["cb_time_ns","pid","tid","callback_name"],
                        right_on=["ts_entry_ns","pid","tid","callback_name"],
                        how="left")
    out["dur_ms"] = out["dur_us"]/1000.0

    out.sort_values("cb_time_ns", inplace=True)
    out.to_csv(matched_csv, index=False)
    print(f"[DONE] 配對結果 → {os.path.abspath(matched_csv)}  共 {len(out)} 筆（含 dur_us/dur_ms=ET）")

    return 0

if __name__ == "__main__":
    sys.exit(main())
