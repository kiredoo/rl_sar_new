#!/bin/bash
# Authoritative copy — used by new_run.sh to seed each new run's scripts/.
# Orchestrates one arm of an A/B experiment: waits for an already-running
# Autoware launch to settle, snapshots pre-bag, plays the rosbag, snapshots
# post-bag, then SIGINTs the launch.
#
# Usage:  run_ab_phase.sh <tag> [run_dir]
#   tag      short label written into output filenames (A, B, C, D, ...)
#   run_dir  where to drop outputs (default /tmp; passed through by new_run.sh
#            so artefacts land directly in runs/<id>/raw/<tag>/)
#
# Outputs written to $run_dir:
#   aw_<tag>_pre.txt    counter snapshot immediately before bag play
#   aw_<tag>_post.txt   counter snapshot immediately after bag play
#   aw_<tag>_t2.log     bag player stdout/stderr
#   aw_<tag>_phase.log  this orchestrator's own log (if caller redirects)
#   aw_<tag>_done       empty flag file on successful completion
#
# Assumes: snapshot_rss.sh and play_bag.sh are on PATH or live next to this
# script. The launch itself must already be started by the caller and have
# its stdout/stderr at $run_dir/aw_<tag>_t1.log.
set -u

tag="${1:-}"
run_dir="${2:-/tmp}"
if [[ -z "$tag" ]]; then
  echo "usage: $0 <tag> [run_dir]" >&2
  exit 1
fi
mkdir -p "$run_dir"

here="$(cd "$(dirname "$0")" && pwd)"
snap="$here/snapshot_rss.sh"
[[ -x "$snap" ]] || snap="$(dirname "$here")/snapshot_rss.sh"
sampler="$here/sample_rss.sh"
[[ -x "$sampler" ]] || sampler="$(dirname "$here")/sample_rss.sh"
tier0="$here/tier0_sampler.sh"
[[ -x "$tier0" ]] || tier0="$(dirname "$here")/tier0_sampler.sh"

log_t1="$run_dir/aw_${tag}_t1.log"
log_t2="$run_dir/aw_${tag}_t2.log"
pre="$run_dir/aw_${tag}_pre.txt"
post="$run_dir/aw_${tag}_post.txt"
timeseries="$run_dir/aw_${tag}_timeseries.tsv"

# Evidence-chain — record every protocol / sampler / CARET / binary knob
# active for this phase to a TSV in env/. compute_summary.sh later picks
# this up and surfaces it as a `## Experiment settings` section in
# MANIFEST.md so reports have a one-step path back to the recipe.
exp_settings_dir="$(dirname "$run_dir")/../env"
mkdir -p "$exp_settings_dir"
exp_settings_tsv="$exp_settings_dir/exp_settings_${tag}.tsv"

# Resolve heaphook .so identity if any (LD_PRELOAD may include it).
heaphook_so_path="$(echo "${LD_PRELOAD:-}" | tr ':' '\n' | grep -E 'heaphook|stockpile|preloaded_' | head -1 || true)"
heaphook_so_sha256=""
heaphook_so_size_bytes=""
if [[ -n "$heaphook_so_path" && -r "$heaphook_so_path" ]]; then
  heaphook_so_sha256="$(sha256sum "$heaphook_so_path" 2>/dev/null | awk '{print $1}')"
  heaphook_so_size_bytes="$(stat -c %s "$heaphook_so_path" 2>/dev/null)"
fi

# Resolve play_bag.sh protocol — note: BAG_FLOW_S/BAG_BURNIN_S are read by
# play_bag.sh from env at phase 4 below. If both 0 -> legacy_no_settle.
bag_flow_s="${BAG_FLOW_S:-6}"
bag_burnin_s="${BAG_BURNIN_S:-10}"
protocol_mode="3stage_flow${bag_flow_s}_burnin${bag_burnin_s}"
if [[ "$bag_flow_s" -le 0 && "$bag_burnin_s" -le 0 ]]; then
  protocol_mode="legacy_no_settle"
fi

# CARET state: ON only if libcaret in LD_PRELOAD AND a record session is
# expected to be running (caller responsibility). Detect best-effort.
caret_libcaret_loaded="off"
if echo "${LD_PRELOAD:-}" | grep -q libcaret; then
  caret_libcaret_loaded="on"
fi
caret_record_active="${CARET_RECORD_ACTIVE:-unknown}"   # caller (run_caret_trace.sh) sets this
if [[ "$caret_record_active" == "unknown" && "$caret_libcaret_loaded" == "off" ]]; then
  caret_record_active="off"   # libcaret not loaded -> definitely no recording
fi

{
  echo "# schema=1"
  echo "# source: tools/run_ab_phase.sh; one row per knob; key/value tabs separated"
  printf "key\tvalue\n"
  printf "arm\t%s\n" "$tag"
  printf "phase_started_at\t%s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf "host\t%s\n" "$(hostname)"
  printf "kernel\t%s\n" "$(uname -r)"
  printf "ros_distro\t%s\n" "${ROS_DISTRO:-unknown}"
  printf "rmw_implementation\t%s\n" "${RMW_IMPLEMENTATION:-unknown}"
  printf "ros_domain_id\t%s\n" "${ROS_DOMAIN_ID:-0}"
  printf "play_rate\t%s\n" "${PLAY_RATE:-1}"
  printf "bag_path\t%s\n" "${BAG_PATH:-$HOME/autoware_map/sample-rosbag}"
  printf "protocol_mode\t%s\n" "$protocol_mode"
  printf "bag_flow_s\t%s\n" "$bag_flow_s"
  printf "bag_burnin_s\t%s\n" "$bag_burnin_s"
  printf "smaps_top_k\t%s\n" "${SMAPS_TOP_K:-20}"
  printf "smaps_period_ms\t%s\n" "${SMAPS_PERIOD_MS:-10000}"
  printf "tier0_sampler\t%s\n" "$([[ -x "$tier0" ]] && echo "on" || echo "off")"
  printf "caret_libcaret_loaded\t%s\n" "$caret_libcaret_loaded"
  printf "caret_record_active\t%s\n" "$caret_record_active"
  printf "heaphook_so_path\t%s\n" "${heaphook_so_path:-(none)}"
  printf "heaphook_so_sha256\t%s\n" "${heaphook_so_sha256:-(n/a)}"
  printf "heaphook_so_size_bytes\t%s\n" "${heaphook_so_size_bytes:-(n/a)}"
  printf "thread_local_pool_size\t%s\n" "${THREAD_LOCAL_POOL_SIZE:-default}"
  printf "heaphook_frag_provider\t%s\n" "${HEAPHOOK_FRAG_PROVIDER:-(unset)}"
} > "$exp_settings_tsv"
echo "[phase $tag] exp_settings -> $exp_settings_tsv" >&2

echo "[phase $tag] waiting 75s for bringup..." >&2
sleep 75

# Wait until the launch log is idle for >=10s, cap extra wait at 45s.
elapsed=0
while [[ $elapsed -lt 45 ]]; do
  sleep 5
  elapsed=$((elapsed+5))
  m=$(stat -c %Y "$log_t1" 2>/dev/null || echo 0)
  now=$(date +%s)
  idle=$((now - m))
  if [[ $idle -ge 10 ]]; then
    echo "[phase $tag] log idle ${idle}s, proceeding" >&2
    break
  fi
done

echo "[phase $tag] pre-bag snapshot -> $pre" >&2
bash "$snap" "$pre"

# Capture the Autoware PID set used by the snapshot, so the Tier 0
# sampler watches exactly the procs the pre/post snapshots cover. Same
# pgrep filter as snapshot_rss.sh §18 — keep them in lock-step.
pids_file="$run_dir/aw_${tag}_pids.txt"
pgrep -f "ros-args|rviz2|ros2 launch autoware|robot_state_publisher|web_server\.py|logging_simulator" > "$pids_file" || true

# Start 1Hz time-series sampler spanning bag play. Failure to start is
# logged but does not abort the phase — pre/post snapshots remain the
# authoritative numbers; time series is additive evidence.
if [[ -x "$sampler" ]]; then
  if bash "$sampler" start "$timeseries" 2>>"$run_dir/aw_${tag}_phase.log"; then
    echo "[phase $tag] sampler started -> $timeseries" >&2
  else
    echo "[phase $tag] sampler start failed (continuing without time series)" >&2
  fi
else
  echo "[phase $tag] sampler not found at $sampler (skipping time series)" >&2
fi

# Tier 0 saturation/working-set sampler (PSI memory + smaps_rollup +
# cgroup memory.stat). Runs for ~50s to bracket the 30s bag-replay window
# plus pre/post settle. Self-cost validated at 89-PID scale (< 5 % over
# 10 s) per cross_abcd_v4_gate's perturbation budget. Backgrounded;
# auto-exits at duration so no explicit stop call needed.
tier0_dir="$run_dir/tier0"
tier0_log="$run_dir/aw_${tag}_tier0.log"
if [[ -x "$tier0" ]]; then
  mkdir -p "$tier0_dir"
  # SMAPS_TOP_K=20 keeps smaps_rollup parsing within ±10 % perturbation
  # budget on hybrid arms (Session 7 fix; full-PID mode hit +26 % on
  # D-v4 per cross_abcd_v4_pss_v1.md §3). Override via env when running
  # this script directly for plumbing-validation against the full set.
  ( nice -n 19 env SMAPS_TOP_K="${SMAPS_TOP_K:-20}" \
    bash "$tier0" "$tier0_dir" 50 "$pids_file" >"$tier0_log" 2>&1 ) &
  tier0_pid=$!
  echo "[phase $tag] tier0 sampler started pid=$tier0_pid (SMAPS_TOP_K=${SMAPS_TOP_K:-20}) -> $tier0_dir" >&2
else
  tier0_pid=""
  echo "[phase $tag] tier0 sampler not found at $tier0 (skipping)" >&2
fi

echo "[phase $tag] bag play start (PLAY_RATE=${PLAY_RATE:-1.0})" >&2
bash "$(dirname "$snap")/play_bag.sh" "${PLAY_RATE:-1.0}" > "$log_t2" 2>&1
echo "[phase $tag] bag play finished" >&2

sleep 3    # settle

if [[ -x "$sampler" && -f "${timeseries}.pid" ]]; then
  bash "$sampler" stop "$timeseries" 2>>"$run_dir/aw_${tag}_phase.log" || true
  echo "[phase $tag] sampler stopped" >&2
fi

# Tier 0 sampler self-exits at duration; if still alive, give it a
# graceful tail then SIGTERM to avoid sloppy log truncation.
if [[ -n "$tier0_pid" ]] && kill -0 "$tier0_pid" 2>/dev/null; then
  for i in 1 2 3 4 5; do
    kill -0 "$tier0_pid" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$tier0_pid" 2>/dev/null; then
    kill -TERM "$tier0_pid" 2>/dev/null || true
    echo "[phase $tag] tier0 sampler SIGTERM (overran duration)" >&2
  else
    echo "[phase $tag] tier0 sampler exited cleanly" >&2
  fi
fi

echo "[phase $tag] post-bag snapshot -> $post" >&2
bash "$snap" "$post"

launch_pid=$(pgrep -f "ros2 launch autoware_launch logging_simulator" | head -1)
if [[ -n "$launch_pid" ]]; then
  # Root-cause fix 2026-05-04 (post-Phase-2.5c-session-1):
  # `kill -INT $launch_pid` alone caused Autoware nodes to be re-parented to
  # systemd-user when ros2 launch died, NOT to receive SIGINT themselves —
  # they kept running and polluted the next rep's nprocs (267 vs 89).
  # Fix: send SIGINT to the entire process group, then escalate to SIGTERM
  # on any descendants still alive, so all nodes get the shutdown signal at
  # once instead of leaking to systemd.
  pgid=$(ps -o pgid= -p "$launch_pid" 2>/dev/null | tr -d ' ')
  echo "[phase $tag] SIGINT launch pid $launch_pid pgid $pgid" >&2
  if [[ -n "$pgid" ]]; then
    kill -INT -- "-$pgid" 2>/dev/null || kill -INT "$launch_pid"
  else
    kill -INT "$launch_pid"
  fi
fi

# Wait up to 60 s for graceful shutdown; if Autoware nodes still alive,
# escalate to SIGTERM to the descendant tree.
launch_gone=0
for i in $(seq 1 12); do
  sleep 5
  if ! pgrep -f "ros2 launch autoware_launch logging_simulator" > /dev/null; then
    echo "[phase $tag] launch exited" >&2
    launch_gone=1
    break
  fi
done

# Even if launch_pid is gone, descendant Autoware nodes may have been
# re-parented to systemd-user. Send SIGTERM to any survivors matching
# the launch's expected node patterns.
descendants_alive() { pgrep -caf "ros-args" 2>/dev/null; }
nleft=$(descendants_alive)
if (( nleft > 4 )); then  # 4 = baseline ros2 daemons (ros-args false-positives)
  echo "[phase $tag] $nleft descendant procs alive after launch exit; SIGTERM" >&2
  for pat in 'logging_simulator' 'rviz2' 'ros-args'; do
    pids=$(pgrep -f "$pat" 2>/dev/null | tr '\n' ' ')
    [[ -n "${pids// }" ]] && kill -TERM $pids 2>/dev/null || true
  done
  sleep 3
  nleft=$(descendants_alive)
  if (( nleft > 4 )); then
    echo "[phase $tag] $nleft still alive after SIGTERM; SIGKILL" >&2
    for pat in 'logging_simulator' 'rviz2' 'ros-args'; do
      pids=$(pgrep -f "$pat" 2>/dev/null | tr '\n' ' ')
      [[ -n "${pids// }" ]] && kill -KILL $pids 2>/dev/null || true
    done
  fi
fi

touch "$run_dir/aw_${tag}_done"
echo "[phase $tag] DONE" >&2
