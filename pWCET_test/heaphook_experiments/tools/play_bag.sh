#!/bin/bash

source $HOME/autoware-2025.02_baseline_caret/install/setup.bash

ros2 topic pub /vehicle/status/control_mode autoware_vehicle_msgs/msg/ControlModeReport "mode: 0" --once

BAG_PATH="$HOME/autoware_map/sample-rosbag"
PLAY_RATE="${1:-1}"

# Bag-replay protocol — three-stage flow→pause→burnin→resume.
#
# Why: without this protocol, the bag plays from t=0 immediately and the
# 30 s measurement window includes the NDT/EKF convergence transient
# (lidar frames flowing in, NDT iterating against the prior map, EKF
# pose covariance fluctuating). The vehicle visibly drifts in rviz, and
# allocator metrics inflate.
#
# Aligned with the established automation at
# ~/repo/20251202/caret-sdrt-model-tools/run_n_interrel_tracing_tmux/
# which uses BAG_WAIT_BEFORE_PAUSE_SEC=6 + BURNIN_PAUSE_SEC=10.
#
# Stages:
#   1. Bag plays normally for BAG_FLOW_S seconds — NDT receives lidar
#      frames and starts iterating against the prior map.
#   2. PAUSE — bag stops publishing further messages.
#   3. Burn-in pause for BAG_BURNIN_S — system processes everything
#      already in flight (callbacks complete, EKF settles).
#   4. RESUME — bag continues from the paused timestamp; system is now
#      at near-steady state when the measurement window covers it.
#
# Override BAG_FLOW_S=0 BAG_BURNIN_S=0 to skip both stages (legacy /
# pre-2026-04-30 protocol; recorded explicitly in env/exp_settings.tsv
# so the broken-protocol reps stay distinguishable in the audit trail).
BAG_FLOW_S="${BAG_FLOW_S:-6}"
BAG_BURNIN_S="${BAG_BURNIN_S:-10}"
# Active-wait for /localization/kinematic_state to publish at >= MIN_HZ
# BEFORE the pause-burn-in. Without this gate the pause fires before NDT/EKF
# have stabilised, so the resumed measurement window includes localization
# transient noise (vehicle drifting visibly in rviz, allocator metrics
# inflated). MIN_HZ=0.5 = at least one message in 2 s; max wait WAIT_LOC_MAX_S.
# Set WAIT_LOC=0 to skip (legacy timing-only protocol).
WAIT_LOC="${WAIT_LOC:-1}"
WAIT_LOC_MIN_HZ="${WAIT_LOC_MIN_HZ:-0.5}"
WAIT_LOC_MAX_S="${WAIT_LOC_MAX_S:-60}"

if [[ "$BAG_FLOW_S" -le 0 && "$BAG_BURNIN_S" -le 0 ]]; then
  # Legacy / broken protocol — pre-2026-04-30 default. Marks reps
  # explicitly so audit chains see "protocol_mode=legacy_no_settle".
  ros2 bag play "$BAG_PATH" -r "$PLAY_RATE"
else
  ros2 bag play "$BAG_PATH" -r "$PLAY_RATE" &
  PB_PID=$!
  if [[ "$BAG_FLOW_S" -gt 0 ]]; then
    sleep "$BAG_FLOW_S"
  fi
  if [[ "$WAIT_LOC" -gt 0 ]]; then
    # Step 1 — call /api/localization/initialize so NDT has an initial pose
    # estimate. With method=AUTO (default 0) and pose_with_covariance=[],
    # Autoware uses GNSS data from the bag for initial pose. Without this
    # call, /initialpose is never published in headless runs (no rviz click)
    # → NDT never converges → base_link↔map TF tree breaks → centerpoint
    # skips all detect calls → chain end events = 0 → e2e CV unmeasurable.
    echo "[play_bag] calling /api/localization/initialize (auto-init from GNSS)"
    timeout 10 ros2 service call /api/localization/initialize \
      autoware_adapi_v1_msgs/srv/InitializeLocalization \
      '{}' 2>&1 | head -3 || echo "[play_bag] initialize service call failed/timed out"

    # Step 2 — active-wait for EKF to publish kinematic_state at MIN_HZ.
    echo "[play_bag] waiting for /localization/kinematic_state >= ${WAIT_LOC_MIN_HZ} Hz (max ${WAIT_LOC_MAX_S}s)"
    deadline=$((SECONDS + WAIT_LOC_MAX_S))
    locked=0
    while (( SECONDS < deadline )); do
      hz=$(timeout 3 ros2 topic hz /localization/kinematic_state 2>/dev/null \
           | tr -d '\r' | grep -oE 'average rate: [0-9.]+' | tail -1 | awk '{print $3}')
      if [[ -n "$hz" ]] && awk -v h="$hz" -v t="$WAIT_LOC_MIN_HZ" 'BEGIN{exit !(h+0 >= t+0)}'; then
        echo "[play_bag] kinematic_state Hz=$hz — EKF locked, proceeding to pause"
        locked=1
        break
      fi
      echo "[play_bag] not yet (Hz=${hz:-—}); waiting..."
      sleep 2
    done
    if [[ $locked -eq 0 ]]; then
      echo "[play_bag] WARN: kinematic_state did not stabilise within ${WAIT_LOC_MAX_S}s; proceeding anyway"
    fi
  fi
  if [[ "$BAG_BURNIN_S" -gt 0 ]]; then
    ros2 service call /rosbag2_player/pause rosbag2_interfaces/srv/Pause "{}" >/dev/null
    sleep "$BAG_BURNIN_S"
    ros2 service call /rosbag2_player/resume rosbag2_interfaces/srv/Resume "{}" >/dev/null
  fi
  wait "$PB_PID"
fi
