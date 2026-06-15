#!/bin/bash
# Event-driven Layer 2 chain CV rep.
#
# Replaces fragile sleep-based orchestration with poll-for-event approach:
#   1. start CARET record
#   2. launch Autoware
#   3. poll T1 log for composition-done marker (Loaded node...traffic_light_roi_visualizer)
#   4. start bag play (continuous, no 3-stage protocol)
#   5. poll T1 log for EKF Activation succeeded (real localization ready)
#   6. measure 30s post-EKF window
#   7. stop CARET trace
#   8. kill launcher tree
#
# Usage: run_event_driven_rep.sh <arm> <run_dir> <play_rate> [skip_probe]
#   arm        A | B | D
#   run_dir    abs path to runs/<id>
#   play_rate  0.5 | 1.0
#   skip_probe 0|1 (1 = no libheaphook_sampler.so LD_PRELOAD = "light")
#
# Output: $run_dir/raw/$arm/{caret/heaphook-<arm>-<ts>/ust/, aw_<arm>_t1.log, aw_<arm>_t2.log, result.json}

set -uo pipefail

arm="${1:?usage: $0 <arm> <run_dir> <play_rate> [skip_probe]}"
run_dir="${2:?usage: $0 <arm> <run_dir> <play_rate> [skip_probe]}"
play_rate="${3:?usage: $0 <arm> <run_dir> <play_rate> [skip_probe]}"
skip_probe="${4:-1}"

case "$arm" in
  A) launcher="sim_play_bag_mp_baseline.sh" ;;
  B) launcher="sim_play_bag_mp_v2.sh" ;;
  D) launcher="sim_play_bag_mp_hybrid_fixed.sh" ;;
  *) echo "[ERR] arm must be A/B/D" >&2; exit 2 ;;
esac

REPO=/home/aga_pc1a/repo/claude_ws4/heaphook_experiments
SAMPLER=/home/aga_pc1a/repo/claude_ws4/heaphook_ws/build/heaphook/libheaphook_sampler.so
RAW="$run_dir/raw/$arm"
mkdir -p "$RAW/caret"

echo "[ev $arm $(date +%H:%M:%S)] starting event-driven rep play_rate=$play_rate skip_probe=$skip_probe"

# Cleanup — kill `ros2 launch` PARENT first (it respawns children otherwise)
( set +e
  pkill -9 -f "ros2 launch"           # parent — must die first
  sleep 2
  pkill -9 -f autoware-2025
  pkill -9 -f web_server.py
  pkill -9 -f topic_tools/relay
  pkill -9 -f rviz2
  pkill -9 -f topic_state_monitor
  pkill -9 -f libheaphook_sampler
  pkill -9 -f rosbag2_player
  pkill -9 -f run_caret_trace
  sleep 4
)

# Stale lttng session
( set +u
  source "$HOME/caret-v0.6.2/setenv_caret.bash" >/dev/null 2>&1
  lttng destroy --all 2>&1 | head -2
) >/dev/null 2>&1

# Phase 1: start CARET record in background
echo "[ev $arm] starting CARET trace wrapper"
bash "$REPO/tools/run_caret_trace.sh" "$arm" "$RAW" \
  > "$RAW/caret_trace_wrapper.log" 2>&1 &
TRACE_PID=$!
echo "$TRACE_PID" > "$RAW/caret_trace_wrapper.pid"

# Wait for CARET ready
ready=0
for i in {1..40}; do
  sleep 1
  if grep -qE 'All process started recording|press ctrl-c to stop' "$RAW/caret/record.log" 2>/dev/null; then
    ready=1
    echo "[ev $arm] CARET READY ${i}s"
    break
  fi
done
if (( ready == 0 )); then
  echo "[ev $arm] CARET timeout"
  kill -INT $TRACE_PID 2>/dev/null
  exit 3
fi

sleep 5  # Let lttng channels flow

# Phase 2: launch Autoware
echo "[ev $arm] launching Autoware (probe=$([[ $skip_probe == 1 ]] && echo OFF || echo ON))"
T1_LOG="$RAW/aw_${arm}_t1.log"
if [ "$skip_probe" = "1" ]; then
  LD_PRELOAD="" CARET_RECORD_ACTIVE=on \
  bash "$run_dir/scripts/$launcher" > "$T1_LOG" 2>&1 &
else
  LD_PRELOAD="$SAMPLER" CARET_RECORD_ACTIVE=on \
  bash "$run_dir/scripts/$launcher" > "$T1_LOG" 2>&1 &
fi
T1_PID=$!
echo "$T1_PID" > "$RAW/aw_${arm}_t1.pid"
echo "[ev $arm] T1_PID=$T1_PID"

# Phase 3: poll for composition done
echo "[ev $arm] waiting for composition done (Loaded node ... traffic_light_roi_visualizer)"
deadline=$(($(date +%s) + 240))
comp_ready=0
while [ $(date +%s) -lt $deadline ]; do
  comp=$(grep -cE 'Loaded node.*traffic_light_roi_visualizer' "$T1_LOG" 2>/dev/null; true)
  comp=${comp:-0}
  if [ "$comp" -ge 1 ]; then
    elapsed=$(( deadline - $(date +%s) ))
    echo "[ev $arm] composition DONE at $(date +%H:%M:%S) (used $((240-elapsed))s)"
    comp_ready=1
    break
  fi
  sleep 2
done
if (( comp_ready == 0 )); then
  echo "[ev $arm] composition TIMEOUT"
  goto_cleanup=1
fi

# Phase 4: start bag in background (continuous, no 3-stage)
sleep 5  # extra settle margin
echo "[ev $arm] starting bag at ${play_rate}x (continuous, no 3-stage)"
T2_LOG="$RAW/aw_${arm}_t2.log"
( set +u
  source $HOME/autoware-2025.02_baseline_caret/install/setup.bash
  ros2 bag play $HOME/autoware_map/sample-rosbag -r "$play_rate"
) > "$T2_LOG" 2>&1 &
BAG_PID=$!
echo "$BAG_PID" > "$RAW/aw_${arm}_bag.pid"
echo "[ev $arm] BAG_PID=$BAG_PID"

# Phase 5: poll for EKF Activation (the real signal)
echo "[ev $arm] waiting for EKF Activation succeeded"
deadline=$(($(date +%s) + 180))
ekf_ready=0
while [ $(date +%s) -lt $deadline ]; do
  ekf=$(grep -c 'EKF Activation succeeded' "$T1_LOG" 2>/dev/null; true)
  ndt=$(grep -c 'NDT Activation succeeded' "$T1_LOG" 2>/dev/null; true)
  ekf=${ekf:-0}; ndt=${ndt:-0}
  if [ "$ekf" -ge 1 ] && [ "$ndt" -ge 1 ]; then
    echo "[ev $arm] EKF+NDT activated at $(date +%H:%M:%S) (ekf=$ekf ndt=$ndt)"
    ekf_ready=1
    break
  fi
  sleep 2
done
if (( ekf_ready == 0 )); then
  echo "[ev $arm] EKF/NDT TIMEOUT"
fi

# Phase 6: 30s steady-state measurement window
echo "[ev $arm] measurement window 30s starting $(date +%H:%M:%S)"
sleep 30
echo "[ev $arm] measurement window done $(date +%H:%M:%S)"

# Phase 7: stop CARET trace
echo "[ev $arm] stopping CARET trace"
SESSION="$(cat "$RAW/caret/trace_session_name.txt" 2>/dev/null || echo)"
kill -INT $TRACE_PID 2>/dev/null
sleep 3
( set +u
  source "$HOME/caret-v0.6.2/setenv_caret.bash" >/dev/null 2>&1
  lttng stop "$SESSION" 2>&1 | head -2
  lttng destroy "$SESSION" 2>&1 | head -2
) >> "$RAW/caret/record.log" 2>&1
if [[ -d "$HOME/.ros/tracing/$SESSION" ]]; then
  mv "$HOME/.ros/tracing/$SESSION" "$RAW/caret/" 2>/dev/null \
    || cp -r "$HOME/.ros/tracing/$SESSION" "$RAW/caret/"
fi

# Phase 8: cleanup
echo "[ev $arm] killing bag + launcher"
kill -INT $BAG_PID 2>/dev/null
sleep 2
kill -9 $BAG_PID 2>/dev/null
kill -INT $T1_PID 2>/dev/null
sleep 5
( set +e
  pkill -9 -f autoware-2025
  pkill -9 -f rviz2
  pkill -9 -f topic_tools/relay
  pkill -9 -f topic_state_monitor
  pkill -9 -f web_server.py
  pkill -9 -f libheaphook_sampler
)
sleep 3

# Result summary
echo "[ev $arm] DONE at $(date +%H:%M:%S)"
ekf_act=$(grep -c 'EKF Activation succeeded' "$T1_LOG" 2>/dev/null; true); ekf_act=${ekf_act:-0}
ndt_act=$(grep -c 'NDT Activation succeeded' "$T1_LOG" 2>/dev/null; true); ndt_act=${ndt_act:-0}
align_ok=$(grep -c 'align server succeeded' "$T1_LOG" 2>/dev/null; true); align_ok=${align_ok:-0}
deact=$(grep -c 'Deactivation succeeded' "$T1_LOG" 2>/dev/null; true); deact=${deact:-0}
tferr=$(grep -c 'two or more unconnected trees' "$T1_LOG" 2>/dev/null; true); tferr=${tferr:-0}
gnss_err=$(grep -c 'GNSS pose has not arrived' "$T1_LOG" 2>/dev/null; true); gnss_err=${gnss_err:-0}
trace_dir=$(find "$RAW/caret" -maxdepth 1 -type d -name 'heaphook-*' | head -1)
trace_size=$(du -sb "$trace_dir" 2>/dev/null | awk '{print $1}')

cat > "$RAW/result.json" <<EOF
{
  "arm": "$arm",
  "play_rate": $play_rate,
  "skip_probe": $skip_probe,
  "ekf_activation_count": $ekf_act,
  "ndt_activation_count": $ndt_act,
  "align_count": $align_ok,
  "deactivation_count": $deact,
  "tf_unconnected_errors": $tferr,
  "gnss_pose_not_arrived_errors": $gnss_err,
  "trace_dir": "$trace_dir",
  "trace_size_bytes": ${trace_size:-0},
  "verdict": "$([ $ekf_act -ge 1 ] && [ $tferr -lt 50 ] && echo healthy || echo broken)"
}
EOF
cat "$RAW/result.json"
