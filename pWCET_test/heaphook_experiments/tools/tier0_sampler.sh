#!/bin/bash
# Tier 0 sampler — L0 Evidence Plane saturation pillar (pillar 3 of arm D).
#
# Captures three sources during a measurement window, all schema=1
# headers per N3 / Q4.3 discipline:
#   - /proc/pressure/memory     (1 Hz time-series; system-wide PSI)
#   - /proc/<pid>/smaps_rollup  (0.1 Hz time-series; per-PID PSS/USS/AnonHuge)
#   - /sys/fs/cgroup/<path>/memory.stat  (one snapshot pre + one post)
#
# Plumbing-validation use (Phase P0 of evidence_plane_gap_analysis.md §D):
#   tools/tier0_sampler.sh /tmp/tier0_smoke 30
#   # in another terminal: induce memory pressure (python alloc-and-touch)
#   # check /tmp/tier0_smoke/tier0_psi_memory.tsv has rows with non-zero
#   # avg10 or rising total_us — confirms PSI plumbing works end-to-end.
#
# Production use (each new run):
#   tools/tier0_sampler.sh runs/<id>/raw/<arm>/tier0 30 < $RUN/raw/<arm>/aw_<arm>_pids.txt
#   # PIDs file: one Autoware PID per line (from snapshot_rss-style pgrep).
#
# Usage:  tier0_sampler.sh <out_dir> [duration_seconds] [pids_file]
#   out_dir         where to drop TSVs (created if absent)
#   duration_seconds  default 30 (one bag-replay window)
#   pids_file       optional; one PID per line for smaps_rollup. Default = $$
set -u

out_dir="${1:?usage: tier0_sampler.sh <out_dir> [duration_s] [pids_file]}"
duration="${2:-30}"
pids_file="${3:-}"

# Top-K by VmRSS for the smaps_rollup pass (commit f___ — Session 7
# perturbation fix). On hybrid arms a full 90-PID smaps_rollup pass per
# 0.1-Hz round perturbed Δminflt by +26 %, well outside the ±10 % gate
# C2 budget. Top-K-by-VmRSS focuses the heavy parse on the procs that
# carry the working set (Pareto: top 20 ≈ 80 % of sum RSS) while keeping
# PSI 1 Hz and cgroup pre/post snapshots unchanged.
#
# SMAPS_TOP_K env var: integer, default 20. Set 0 for "all PIDs" (the
# pre-Session-7 behaviour, retained for plumbing-validation reproducibility).
top_k="${SMAPS_TOP_K:-20}"

# SMAPS_PERIOD_MS env var: integer, default 10000 (= 0.1 Hz). Drop to
# longer (e.g. 20000) for further cost reduction on hybrid arms where
# top-K alone may not be enough.
smaps_period_ms="${SMAPS_PERIOD_MS:-10000}"

mkdir -p "$out_dir"

# Default PIDs file = the sampler itself (validates plumbing without an
# Autoware run). Production callers pass a real PIDs list.
if [[ -z "$pids_file" ]]; then
  pids_file="$out_dir/pids.txt"
  echo $$ > "$pids_file"
fi

# Resolve cgroup memory controller path for this process. Hybrid v1+v2
# hosts: prefer v1 (line "13:memory:..." in /proc/$$/cgroup, mounted at
# /sys/fs/cgroup/memory<path>); fall back to v2 unified at /sys/fs/cgroup<path>.
cgroup_v1_path=$(awk -F: '/^[0-9]+:memory:/ {print $3; exit}' /proc/$$/cgroup)
cgroup_v2_path=$(awk -F: '/^0::/ {print $3; exit}' /proc/$$/cgroup)
if [[ -n "$cgroup_v1_path" && -d "/sys/fs/cgroup/memory${cgroup_v1_path}" ]]; then
  cgroup_dir="/sys/fs/cgroup/memory${cgroup_v1_path}"
elif [[ -n "$cgroup_v2_path" && -d "/sys/fs/cgroup${cgroup_v2_path}" ]]; then
  cgroup_dir="/sys/fs/cgroup${cgroup_v2_path}"
else
  cgroup_dir=""
  echo "[tier0_sampler] WARN: no cgroup memory.stat path resolved" >&2
fi

# ---------------- output files (schema=1 + named header rows) -----------------

psi_tsv="$out_dir/tier0_psi_memory.tsv"
{
  echo "# schema=1"
  echo "# source: /proc/pressure/memory"
  printf "epoch_ms\tline_kind\tavg10\tavg60\tavg300\ttotal_us\n"
} > "$psi_tsv"

smaps_tsv="$out_dir/tier0_smaps_rollup.tsv"
{
  echo "# schema=1"
  echo "# source: /proc/<pid>/smaps_rollup"
  printf "epoch_ms\tpid\tRss_kB\tPss_kB\tPss_Anon_kB\tAnonHugePages_kB\tShared_Clean_kB\tShared_Dirty_kB\tPrivate_Clean_kB\tPrivate_Dirty_kB\tSwap_kB\tSwapPss_kB\n"
} > "$smaps_tsv"

cgroup_tsv="$out_dir/tier0_cgroup_memory_stat.tsv"
{
  echo "# schema=1"
  echo "# source: ${cgroup_dir:-<unresolved>}/memory.stat (one row per key per phase)"
  printf "phase\tkey\tvalue_bytes\n"
} > "$cgroup_tsv"

# memory.events captures kernel-level OOM / pressure events as cumulative
# counters (cgroup v2 only): low / high / max / oom / oom_kill / oom_group_kill.
# Pre + post delta is the only honest summary; per-second time-series adds
# nothing because the file is updated only on event boundaries. Source
# of record for cross_abcd_v4 § R-v2.7 cgroup memory.events row.
cgroup_events_tsv="$out_dir/tier0_cgroup_memory_events.tsv"
{
  echo "# schema=1"
  echo "# source: ${cgroup_dir:-<unresolved>}/memory.events (cumulative counters per phase)"
  printf "phase\tkey\tvalue_count\n"
} > "$cgroup_events_tsv"

# ---------------- helpers --------------------------------------------------

snapshot_cgroup() {
  local phase="$1"
  if [[ -n "$cgroup_dir" && -r "$cgroup_dir/memory.stat" ]]; then
    awk -v p="$phase" '{print p "\t" $1 "\t" $2}' "$cgroup_dir/memory.stat" >> "$cgroup_tsv"
  fi
  # cgroup v2 only: memory.events is a separate kernel-counter file.
  # Best-effort read; absent on cgroup v1 (file does not exist there).
  if [[ -n "$cgroup_dir" && -r "$cgroup_dir/memory.events" ]]; then
    awk -v p="$phase" '{print p "\t" $1 "\t" $2}' "$cgroup_dir/memory.events" >> "$cgroup_events_tsv"
  fi
}

snapshot_psi() {
  local ts_ms="$1"
  awk -v ts="$ts_ms" '
    function strip(s, k) { sub(k "=", "", s); return s }
    /^some/ {
      printf "%s\t%s\t%s\t%s\t%s\t%s\n",
        ts, "some",
        strip($2,"avg10"), strip($3,"avg60"), strip($4,"avg300"), strip($5,"total")
    }
    /^full/ {
      printf "%s\t%s\t%s\t%s\t%s\t%s\n",
        ts, "full",
        strip($2,"avg10"), strip($3,"avg60"), strip($4,"avg300"), strip($5,"total")
    }
  ' /proc/pressure/memory >> "$psi_tsv"
}

snapshot_smaps_pid() {
  local pid="$1"
  local ts_ms="$2"
  [[ -r /proc/$pid/smaps_rollup ]] || return 0
  awk -v ts="$ts_ms" -v pid="$pid" '
    /^Rss:/             { rss=$2 }
    /^Pss:/             { pss=$2 }
    /^Pss_Anon:/        { pa=$2 }
    /^AnonHugePages:/   { ahp=$2 }
    /^Shared_Clean:/    { sc=$2 }
    /^Shared_Dirty:/    { sd=$2 }
    /^Private_Clean:/   { pc=$2 }
    /^Private_Dirty:/   { pd=$2 }
    /^Swap:/            { sw=$2 }
    /^SwapPss:/         { spss=$2 }
    END {
      printf "%s\t%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\n",
        ts, pid, rss+0, pss+0, pa+0, ahp+0, sc+0, sd+0, pc+0, pd+0, sw+0, spss+0
    }
  ' /proc/$pid/smaps_rollup >> "$smaps_tsv"
}

# Resolve the top-K PIDs by current VmRSS for this round. Cheap pass:
# read /proc/<pid>/status (VmRSS line only) for each candidate, sort
# descending. If top_k <= 0 OR top_k >= candidate count, return all.
resolve_top_k_pids() {
  local k="$1"
  shift
  if [[ "$k" -le 0 ]]; then
    printf '%s\n' "$@"
    return 0
  fi
  for pid in "$@"; do
    [[ -z "$pid" ]] && continue
    local rss
    rss=$(awk '/^VmRSS:/ {print $2; exit}' /proc/$pid/status 2>/dev/null)
    [[ -z "$rss" ]] && continue
    printf '%d\t%s\n' "$rss" "$pid"
  done | sort -rn -k1,1 | head -n "$k" | cut -f2
}

# ---------------- main loop ------------------------------------------------

snapshot_cgroup pre

# Capture-on-exit: even if the orchestrator SIGTERMs us before the
# duration is up (sampler running longer than phase + settle), make
# sure the post cgroup snapshot lands. Idempotent if both fire.
post_done=0
on_exit() {
  if [[ "$post_done" -eq 0 ]]; then
    snapshot_cgroup post
    post_done=1
  fi
}
trap on_exit EXIT TERM INT

end_time_s=$(($(date +%s) + duration))
psi_next_ms=$(date +%s%3N)
smaps_next_ms=$psi_next_ms

while [[ $(date +%s) -lt $end_time_s ]]; do
  now_ms=$(date +%s%3N)
  if [[ "$now_ms" -ge "$psi_next_ms" ]]; then
    snapshot_psi "$now_ms"
    psi_next_ms=$((now_ms + 1000))         # 1 Hz
  fi
  if [[ "$now_ms" -ge "$smaps_next_ms" ]]; then
    # Re-rank PIDs by current VmRSS each round so the top-K window
    # follows where the working set actually moves during a rep.
    mapfile -t _all_pids < "$pids_file"
    while IFS= read -r pid; do
      [[ -z "$pid" ]] && continue
      snapshot_smaps_pid "$pid" "$now_ms"
    done < <(resolve_top_k_pids "$top_k" "${_all_pids[@]}")
    smaps_next_ms=$((now_ms + smaps_period_ms))
  fi
  sleep 0.1
done

# Natural exit path (no SIGTERM); EXIT trap will fire, capturing post.

echo "[tier0_sampler] done in ${duration}s; output in $out_dir" >&2
echo "[tier0_sampler] PSI rows: $(($(wc -l < "$psi_tsv") - 3))" >&2
echo "[tier0_sampler] smaps rows: $(($(wc -l < "$smaps_tsv") - 3))" >&2
echo "[tier0_sampler] cgroup keys per phase: $(awk -F'\t' '$1=="pre"' "$cgroup_tsv" | wc -l)" >&2
