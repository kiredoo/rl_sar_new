#!/bin/bash
# wait_autoware_ready.sh — block until Autoware logging_simulator launch log
# shows the COMPLETE ready sequence:
#   1. traffic_light_roi_visualizer Loaded   (composition done — ~100s typical)
#   2. align server succeeded                 (NDT got initial alignment)
#   3. EKF Activation succeeded               (EKF turned on)
#   4. NDT Activation succeeded               (NDT turned on)
#   AND no subsequent Deactivation after the Activation events
#   = vehicle pointcloud STABLE in rviz, perception+chain can flow
#
# Usage: wait_autoware_ready.sh <launch_log_path> [timeout_sec]
#
# Exits 0 if all conditions met within timeout, 1 if timeout, 2 on usage error.
# Default timeout 240s (composition ~100s + alignment ~40s + margin).
set -u
log_path="${1:?usage: $0 <launch_log_path> [timeout_sec=240]}"
timeout="${2:-240}"
echo "[wait_ready] log=$log_path timeout=${timeout}s"
echo "[wait_ready] checking for 4-stage ready sequence:"
echo "             1. traffic_light_roi_visualizer Loaded"
echo "             2. align server succeeded"
echo "             3. EKF Activation succeeded"
echo "             4. NDT Activation succeeded (and stable: no later Deactivation)"
deadline=$((SECONDS + timeout))
start_t=$SECONDS
while (( SECONDS < deadline )); do
  [[ -f "$log_path" ]] || { sleep 1; continue; }
  composition=$(grep -c 'traffic_light_roi_visualizer.*Loaded' "$log_path")
  align=$(grep -c 'align server succeeded' "$log_path")
  ekf_act=$(grep -c 'EKF Activation succeeded' "$log_path")
  ndt_act=$(grep -c 'NDT Activation succeeded' "$log_path")
  # stable_check: last EKF event must be Activation (not Deactivation)
  last_ekf_event=$(grep -E 'EKF (Activation|Deactivation) succeeded' "$log_path" | tail -1)
  if (( composition >= 1 && align >= 1 && ekf_act >= 1 && ndt_act >= 1 )) \
     && [[ "$last_ekf_event" == *"Activation succeeded" ]]; then
    elapsed=$((SECONDS - start_t))
    echo "[wait_ready] STABLE at $(date +%H:%M:%S) (after ${elapsed}s)"
    echo "             composition=$composition align=$align EKF_act=$ekf_act NDT_act=$ndt_act"
    echo "             last EKF event: ${last_ekf_event:0:120}..."
    exit 0
  fi
  if (( SECONDS - start_t > 0 && (SECONDS - start_t) % 15 == 0 )); then
    echo "[wait_ready] $((SECONDS - start_t))s waiting: comp=$composition align=$align EKF=$ekf_act NDT=$ndt_act"
  fi
  sleep 1
done
elapsed=$((SECONDS - start_t))
echo "[wait_ready] TIMEOUT ${timeout}s — final state: comp=$composition align=$align EKF=$ekf_act NDT=$ndt_act last_ekf=$last_ekf_event" >&2
exit 1
