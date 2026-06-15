#!/bin/bash
# Minimal D-arm health check — NO CARET RECORDING.
# Just confirms: does heaphook hybrid run a stable 89-PID Autoware + bag at 0.5x?
#
# If yes -> heaphook hybrid is fine, CARET wrapper is the bug to fix later.
# If no  -> heaphook hybrid has a real bug under bringup load.
#
# Usage: run_no_caret_rep.sh <arm> <run_dir>

set -uo pipefail

arm="${1:?usage: $0 <arm> <run_dir>}"
run_dir="${2:?usage: $0 <arm> <run_dir>}"

case "$arm" in
  A) launcher="sim_play_bag_mp_baseline.sh" ;;
  B) launcher="sim_play_bag_mp_v2.sh" ;;
  D) launcher="sim_play_bag_mp_hybrid_fixed.sh" ;;
  *) echo "[ERR] arm A/B/D" >&2; exit 2 ;;
esac

RAW="$run_dir/raw/$arm"
mkdir -p "$RAW"

echo "[nc $arm $(date +%H:%M:%S)] starting NO-CARET health check"

# Cleanup ros2 launch parent first (avoid orphan respawn)
( set +e
  pkill -9 -f "ros2 launch"
  sleep 2
  pkill -9 -f autoware-2025
  pkill -9 -f rviz2
  pkill -9 -f topic_tools/relay
  pkill -9 -f topic_state_monitor
  pkill -9 -f web_server.py
  pkill -9 -f libheaphook_sampler
  pkill -9 -f rosbag2_player
  pkill -9 -f "ros2 caret record"
  sleep 4
)

# Launch Autoware WITHOUT CARET wrapper, NO sampler
T1_LOG="$RAW/aw_${arm}_t1.log"
echo "[nc $arm] launching Autoware (no CARET record, no sampler)"
LD_PRELOAD="" \
bash "$run_dir/scripts/$launcher" > "$T1_LOG" 2>&1 &
T1_PID=$!
echo "$T1_PID" > "$RAW/aw_${arm}_t1.pid"
echo "[nc $arm] T1_PID=$T1_PID"

# Poll for composition done
echo "[nc $arm] poll composition done"
deadline=$(($(date +%s) + 240))
comp_ready=0
while [ $(date +%s) -lt $deadline ]; do
  if grep -qE 'Loaded node.*traffic_light_roi_visualizer' "$T1_LOG" 2>/dev/null; then
    echo "[nc $arm] composition DONE at $(date +%H:%M:%S)"
    comp_ready=1
    break
  fi
  sleep 2
done

if [ "$comp_ready" = "0" ]; then
  echo "[nc $arm] composition TIMEOUT"
  echo "{\"verdict\":\"composition_timeout\"}" > "$RAW/result.json"
  ( set +e; kill -INT "$T1_PID"; sleep 5; pkill -9 -f "ros2 launch" )
  exit 3
fi

sleep 5  # settle

# Play bag at 0.5x in background
echo "[nc $arm] starting bag at 0.5x"
T2_LOG="$RAW/aw_${arm}_t2.log"
( set +u
  source $HOME/autoware-2025.02_baseline_caret/install/setup.bash
  ros2 bag play $HOME/autoware_map/sample-rosbag -r 0.5
) > "$T2_LOG" 2>&1 &
BAG_PID=$!
echo "$BAG_PID" > "$RAW/aw_${arm}_bag.pid"

# Poll for EKF Activation
echo "[nc $arm] poll EKF Activation succeeded"
deadline=$(($(date +%s) + 180))
ekf_ready=0
while [ $(date +%s) -lt $deadline ]; do
  if grep -q 'EKF Activation succeeded' "$T1_LOG" 2>/dev/null && \
     grep -q 'NDT Activation succeeded' "$T1_LOG" 2>/dev/null; then
    echo "[nc $arm] EKF+NDT activated at $(date +%H:%M:%S)"
    ekf_ready=1
    break
  fi
  sleep 2
done

if [ "$ekf_ready" = "0" ]; then
  echo "[nc $arm] EKF TIMEOUT"
fi

# Sample alignment metrics for 20s
sleep 5
echo "[nc $arm] sampling alignment metrics 20s"
export ROS_DOMAIN_ID=4
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
( set +u; source /opt/ros/humble/setup.bash )
TP=$RAW/sample_tp.txt
DI=$RAW/sample_dist.txt
EX=$RAW/sample_exe.txt
KH=$RAW/sample_kin_hz.txt

timeout 20 ros2 topic echo --field data /localization/pose_estimator/transform_probability > $TP 2>&1 &
P1=$!
timeout 20 ros2 topic echo --field data /localization/pose_estimator/initial_to_result_distance_new > $DI 2>&1 &
P2=$!
timeout 20 ros2 topic echo --field data /localization/pose_estimator/exe_time_ms > $EX 2>&1 &
P3=$!
timeout 20 ros2 topic hz /localization/kinematic_state > $KH 2>&1 &
P4=$!
wait $P1 $P2 $P3 $P4 2>/dev/null

echo "[nc $arm] sample done at $(date +%H:%M:%S)"

# Reduce results
python3 - "$TP" "$DI" "$EX" "$KH" "$T1_LOG" <<'PY' > "$RAW/result.json"
import sys, json, statistics, re
tp_f, dist_f, exe_f, kin_f, t1_f = sys.argv[1:6]
def floats(p):
    out=[]
    try:
        with open(p) as f:
            for l in f:
                l=l.strip()
                if not l: continue
                try: out.append(float(l))
                except: pass
    except FileNotFoundError: pass
    return out
def stat(arr):
    if not arr: return {"n": 0}
    return {"n": len(arr), "min": round(min(arr),3), "max": round(max(arr),3), "mean": round(statistics.mean(arr),3), "median": round(statistics.median(arr),3)}
tp = floats(tp_f); dist = floats(dist_f); exe = floats(exe_f)
kin_hz = None
try:
    with open(kin_f) as f:
        for l in f:
            m = re.search(r'average rate:\s*([\d.]+)', l)
            if m: kin_hz = float(m.group(1))
except FileNotFoundError: pass

# Count crashes
ekf_act=0; ndt_act=0; deact=0; sigsegv=0; sigabrt=0; gnss_err=0; tferr=0
try:
    with open(t1_f) as f:
        for l in f:
            if 'EKF Activation succeeded' in l: ekf_act+=1
            elif 'NDT Activation succeeded' in l: ndt_act+=1
            elif 'Deactivation succeeded' in l: deact+=1
            elif 'exit code -11' in l: sigsegv+=1
            elif 'exit code -6' in l: sigabrt+=1
            elif 'GNSS pose has not arrived' in l: gnss_err+=1
            elif 'two or more unconnected trees' in l: tferr+=1
except FileNotFoundError: pass

result = {
    "transform_probability": stat(tp),
    "init_to_result_distance_m": stat(dist),
    "exe_time_ms": stat(exe),
    "kinematic_state_avg_hz": kin_hz,
    "ekf_activation_count": ekf_act,
    "ndt_activation_count": ndt_act,
    "deactivation_count": deact,
    "sigsegv_count": sigsegv,
    "sigabrt_count": sigabrt,
    "gnss_pose_not_arrived": gnss_err,
    "tf_unconnected_tree_errors": tferr,
}
tp_ok = result["transform_probability"].get("mean", 0) >= 4.0
dist_ok = result["init_to_result_distance_m"].get("mean", 99) < 2.0
exe_ok = result["exe_time_ms"].get("mean", 9999) < 100.0
result["pass_strict"] = tp_ok and dist_ok and exe_ok and ekf_act>=1 and sigsegv<5
result["per_metric"] = {"tp": tp_ok, "dist": dist_ok, "exe": exe_ok}
result["heaphook_verdict"] = "healthy" if (ekf_act>=1 and sigsegv<5 and tp_ok) else ("broken" if sigsegv>5 else "borderline")
print(json.dumps(result, indent=2))
PY

cat $RAW/result.json

# Cleanup
echo "[nc $arm] cleanup"
( set +e
  kill -INT $BAG_PID
  sleep 2
  kill -9 $BAG_PID
  pkill -9 -f "ros2 launch"
  sleep 4
  pkill -9 -f autoware-2025
  pkill -9 -f rviz2
)
echo "[nc $arm] DONE at $(date +%H:%M:%S)"
