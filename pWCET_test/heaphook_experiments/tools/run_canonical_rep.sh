#!/bin/bash
# Canonical CARET rep, adapted from run_n_interrel_tracing_tmux.sh reference.
#
# Phases:
#   0  pre-flight (lttng/zombies/.so check)
#   1  tmux session
#   2  T2 launch Autoware (pane); poll for ready_marker
#   3  T3 start record.sh (pane); poll for "press enter to start"
#   4  T4 play_bag (pane)
#      sleep 2s + Gate-3 poll EKF Activation; SPACE pause
#   5  sleep 10s burnin
#   6  T4 SPACE resume; T3 ENTER (start capture)
#   7  alignment sampler 25s (parallel with measurement window)
#   8  sleep 30s measurement window
#   9  T3 ENTER (stop); T2 Ctrl-C
#  10  cleanup + mv trace + observe_rep.py
#
# Usage: run_canonical_rep.sh <arm> <run_dir> [play_rate]

set -uo pipefail

arm="${1:?arm}"
run_dir="${2:?run_dir}"
play_rate="${3:-0.5}"
# PROBE=1 → LD_PRELOAD libheaphook_sampler.so (fragmentation probe)
PROBE="${PROBE:-0}"
SAMPLER_SO=/home/aga_pc1a/repo/claude_ws4/heaphook_ws/build/heaphook/libheaphook_sampler.so

case "$arm" in
  A) launcher_name="sim_play_bag_mp_baseline.sh" ;;
  B) launcher_name="sim_play_bag_mp_v2.sh" ;;
  D) launcher_name="sim_play_bag_mp_hybrid_fixed.sh" ;;
  *) echo "[ERR] arm A/B/D" >&2; exit 2 ;;
esac

REPO=/home/aga_pc1a/repo/claude_ws4/heaphook_experiments
RAW="$run_dir/raw/$arm"
mkdir -p "$RAW/caret"
DRIVER_LOG="$run_dir/driver.log"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$DRIVER_LOG"; }

# ============================================================
# Phase 0: pre-flight
# ============================================================
log "[ev $arm] === Phase 0: pre-flight ==="

# Verify .so for D arm
if [ "$arm" = "D" ]; then
  HSO=/home/aga_pc1a/repo/claude_ws4/heaphook_ws/build/heaphook/libpreloaded_hybrid_o1heap_tlsf.so
  if [ ! -f "$HSO" ]; then
    log "[ERR] heaphook hybrid .so missing: $HSO"
    exit 3
  fi
fi

# Kill residue (PGID and name based)
( set +e
  pkill -9 -f "ros2 launch"
  pkill -9 -f "ros2 caret record"
  sleep 2
  pkill -9 -f autoware-2025
  pkill -9 -f rviz2
  pkill -9 -f topic_state_monitor
  pkill -9 -f topic_tools/relay
  pkill -9 -f web_server.py
  pkill -9 -f libheaphook_sampler
  pkill -9 -f rosbag2_player
  pkill -9 -f rclcpp_component_container
  pkill -9 -f duplicated_node_checker
  pkill -9 -f processing_time_checker
  pkill -9 -f service_log_checker
  pkill -9 -f map_hash_generator
  pkill -9 -f hazard_status_converter
  sleep 4
)

# lttng cleanup
( set +u; source $HOME/caret-v0.6.2/setenv_caret.bash >/dev/null 2>&1
  lttng destroy --all 2>&1 | head -2
) >> "$DRIVER_LOG" 2>&1

# Sanity
N_AUTOWARE=$(pgrep -cf 'autoware-2025/install' 2>/dev/null; true)
N_AUTOWARE=${N_AUTOWARE:-0}
N_LAUNCH=$(pgrep -cf 'ros2 launch' 2>/dev/null; true)
N_LAUNCH=${N_LAUNCH:-0}
log "[ev $arm] post-cleanup: autoware=$N_AUTOWARE launch=$N_LAUNCH (each '1' may be self bash match)"

# ============================================================
# Phase 1: tmux session
# ============================================================
SESSION="canonical_${arm}_$(date +%Y%m%d_%H%M%S)"
log "[ev $arm] === Phase 1: tmux session=$SESSION ==="
tmux kill-session -t "$SESSION" 2>/dev/null
tmux new-session -d -s "$SESSION" -n main

# 3 panes: T2 (sim) T3 (record) T4 (bag)
P_T2=$(tmux split-window -h -t "$SESSION:main" -P -F "#{pane_id}")
P_T3=$(tmux split-window -v -t "$SESSION:main.0" -P -F "#{pane_id}")
P_T4=$(tmux split-window -v -t "$P_T2" -P -F "#{pane_id}")
tmux select-layout -t "$SESSION:main" tiled

# Pipe pane output to log
tmux pipe-pane -o -t "$SESSION:main.0" "cat >> '$run_dir/pane_main.log'"
tmux pipe-pane -o -t "$P_T2" "cat >> '$run_dir/pane_t2.log'"
tmux pipe-pane -o -t "$P_T3" "cat >> '$run_dir/pane_t3.log'"
tmux pipe-pane -o -t "$P_T4" "cat >> '$run_dir/pane_t4.log'"

log "[ev $arm] panes: T2=$P_T2 T3=$P_T3 T4=$P_T4"
echo "$SESSION" > "$run_dir/tmux_session.txt"

# ============================================================
# Phase 2: T2 launch Autoware
# ============================================================
log "[ev $arm] === Phase 2: T2 launch ==="
T1_LOG="$RAW/aw_${arm}_t1.log"
LAUNCHER="$run_dir/scripts/$launcher_name"
if [ "$PROBE" = "1" ] && [ -f "$SAMPLER_SO" ]; then
  log "[ev $arm] PROBE=1 → LD_PRELOAD libheaphook_sampler.so"
  PRELOAD_CMD="LD_PRELOAD=$SAMPLER_SO "
else
  PRELOAD_CMD=""
fi
tmux send-keys -t "$P_T2" "${PRELOAD_CMD}stdbuf -oL -eL bash $LAUNCHER 2>&1 | tee $T1_LOG" Enter

# Poll for composition done
log "[ev $arm] waiting ready_marker (Loaded node ... traffic_light_roi_visualizer)"
deadline=$(($(date +%s) + 240))
ready=0
while [ $(date +%s) -lt $deadline ]; do
  if grep -qE "Loaded node.*traffic_light_roi_visualizer" "$T1_LOG" 2>/dev/null; then
    log "[ev $arm] ready_marker matched at $(date +%H:%M:%S)"
    ready=1
    break
  fi
  sleep 2
done
if [ $ready -eq 0 ]; then
  log "[ev $arm] ready_marker TIMEOUT 240s"
  goto_cleanup=1
fi

# ============================================================
# Phase 3: T3 start record.sh
# ============================================================
log "[ev $arm] === Phase 3: T3 record ==="
RECORD_BOOT="$RAW/caret/record_boot.log"
RECORD_SH=$HOME/repo/claude_ws4/autoware-2025.02_baseline_caret/scripts/record.sh
SAFE_RECORD=$HOME/repo/20251202/caret-sdrt-model-tools/run_n_interrel_tracing_tmux/helpers/safe_record.sh
tmux send-keys -t "$P_T3" "bash $SAFE_RECORD $RECORD_SH $RECORD_BOOT" Enter

# Poll for record prompt
log "[ev $arm] waiting record.sh prompt 'press enter to start'"
deadline=$(($(date +%s) + 60))
record_ready=0
while [ $(date +%s) -lt $deadline ]; do
  if grep -qE "press enter to start|recordable processes found" "$RECORD_BOOT" 2>/dev/null; then
    log "[ev $arm] record.sh ready"
    record_ready=1
    break
  fi
  sleep 2
done
if [ $record_ready -eq 0 ]; then
  log "[ev $arm] record.sh ready TIMEOUT — abort"
  goto_cleanup=1
fi

# ============================================================
# Phase 4: T4 play_bag + Gate-3 EKF poll + pause
# ============================================================
log "[ev $arm] === Phase 4: T4 bag + pause ==="
T2_LOG="$RAW/aw_${arm}_t2.log"
PLAY_BAG="$run_dir/scripts/play_bag.sh"
# Override env — we want NO 3-stage from play_bag.sh; we drive it externally
tmux send-keys -t "$P_T4" "BAG_FLOW_S=0 BAG_BURNIN_S=0 WAIT_LOC=0 stdbuf -oL -eL bash $PLAY_BAG $play_rate 2>&1 | tee $T2_LOG" Enter

# Wait for bag to actually publish first message
sleep 2

# Gate-3: poll for EKF Activation succeeded (max 12s)
log "[ev $arm] Gate-3: waiting EKF Activation succeeded (max 12s)"
deadline=$(($(date +%s) + 12))
ekf_ready=0
while [ $(date +%s) -lt $deadline ]; do
  if grep -q "EKF Activation succeeded" "$T1_LOG" 2>/dev/null; then
    elapsed=$((12 - (deadline - $(date +%s))))
    log "[ev $arm] EKF activated at $(date +%H:%M:%S) (after ${elapsed}s)"
    ekf_ready=1
    break
  fi
  sleep 1
done
if [ $ekf_ready -eq 0 ]; then
  log "[ev $arm] Gate-3 TIMEOUT — pausing anyway (reference behavior)"
fi

# SPACE pause via T4 (rosbag2_player keyboard shortcut)
log "[ev $arm] T4 SPACE → pause"
tmux send-keys -t "$P_T4" " "

# ============================================================
# Phase 5: burnin 10s
# ============================================================
log "[ev $arm] === Phase 5: burnin 10s ==="
sleep 10

# ============================================================
# Phase 6: resume + record ENTER
# ============================================================
log "[ev $arm] === Phase 6: resume + record ENTER ==="
tmux send-keys -t "$P_T4" " "    # resume
sleep 1
tmux send-keys -t "$P_T3" Enter  # start capture

# ============================================================
# Phase 7+8: alignment sampler 25s (parallel) + 30s measurement window
# ============================================================
log "[ev $arm] === Phase 7+8: alignment sample 25s + measurement 30s ==="

# Track 1A — RSS snapshot pre (memory baseline at measurement window start)
bash $REPO/tools/snapshot_rss.sh "$RAW/rss_pre.txt" 2>>"$DRIVER_LOG"
log "[ev $arm] RSS snapshot pre (Track 1A)"

bash $REPO/tools/sample_alignment_metrics.sh "$RAW" 25 \
  > "$RAW/align_sample.log" 2>&1 &
SAMP_PID=$!

sleep 30  # measurement window

# Track 1A — RSS snapshot post (memory state at end-of-measurement)
bash $REPO/tools/snapshot_rss.sh "$RAW/rss_post.txt" 2>>"$DRIVER_LOG"
log "[ev $arm] RSS snapshot post (Track 1A)"

# ============================================================
# Phase 9: stop record + sim
# ============================================================
log "[ev $arm] === Phase 9: stop record + sim ==="
tmux send-keys -t "$P_T3" Enter   # stop record
sleep 5  # let trace finalize
wait $SAMP_PID 2>/dev/null || true

tmux send-keys -t "$P_T2" C-c   # stop sim
sleep 10

# ============================================================
# Phase 10: cleanup + mv trace
# ============================================================
log "[ev $arm] === Phase 10: cleanup ==="

# Find new trace dir
TRACING_ROOT=$HOME/.ros/tracing
LATEST=$(ls -1dt "$TRACING_ROOT"/heaphook-* "$TRACING_ROOT"/session-* 2>/dev/null | head -1)
if [ -n "$LATEST" ] && [ -d "$LATEST" ]; then
  mv "$LATEST" "$RAW/caret/" 2>/dev/null || cp -r "$LATEST" "$RAW/caret/"
  log "[ev $arm] trace moved: $(basename $LATEST)"
fi

# kill remaining
( set +e
  pkill -9 -f "ros2 launch"
  pkill -9 -f "ros2 caret record"
  sleep 2
  pkill -9 -f autoware-2025
  pkill -9 -f rviz2
  pkill -9 -f topic_state_monitor
  pkill -9 -f rclcpp_component_container
  sleep 3
)
( set +u; source $HOME/caret-v0.6.2/setenv_caret.bash >/dev/null 2>&1
  lttng destroy --all 2>&1 | head -2
) >> "$DRIVER_LOG" 2>&1

tmux kill-session -t "$SESSION" 2>/dev/null

log "[ev $arm] === DONE ==="

# ============================================================
# Phase 11: observe rep
# ============================================================
log "[ev $arm] === Phase 11: observe ==="
python3 $REPO/tools/observe_rep.py "$run_dir" "$arm" 2>&1 | tee -a "$DRIVER_LOG"

echo
echo "Result: $RAW/result.json"
exit 0
