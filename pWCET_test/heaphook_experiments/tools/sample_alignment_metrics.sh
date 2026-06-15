#!/bin/bash
# Sample alignment metrics in parallel for given duration.
# Output: 4 files in $1
#
# Usage: sample_alignment_metrics.sh <output_dir> <duration_sec>

set +u
OUT="${1:?output dir}"
DUR="${2:?duration sec}"
mkdir -p "$OUT"

source /opt/ros/humble/setup.bash 2>/dev/null
source $HOME/autoware-2025.02_baseline_caret/install/setup.bash 2>/dev/null
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-4}"

timeout "$DUR" ros2 topic echo --field data /localization/pose_estimator/transform_probability \
  > "$OUT/sample_tp.txt" 2>&1 &
P1=$!
timeout "$DUR" ros2 topic echo --field data /localization/pose_estimator/initial_to_result_distance_new \
  > "$OUT/sample_dist.txt" 2>&1 &
P2=$!
timeout "$DUR" ros2 topic echo --field data /localization/pose_estimator/exe_time_ms \
  > "$OUT/sample_exe.txt" 2>&1 &
P3=$!
timeout "$DUR" ros2 topic hz /localization/kinematic_state \
  > "$OUT/sample_kin_hz.txt" 2>&1 &
P4=$!
# Per-core CPU usage via mpstat (1Hz)
if command -v mpstat >/dev/null 2>&1; then
  timeout "$DUR" mpstat -P ALL 1 > "$OUT/sample_mpstat.txt" 2>&1 &
  P5=$!
fi
# Per-PID context switches + cpu via pidstat (1Hz, all autoware procs)
if command -v pidstat >/dev/null 2>&1; then
  timeout "$DUR" pidstat -p ALL -u -w 1 > "$OUT/sample_pidstat.txt" 2>&1 &
  P6=$!
fi
# GPU utilization + memory (1Hz)
if command -v nvidia-smi >/dev/null 2>&1; then
  ( for i in $(seq "$DUR"); do
      nvidia-smi --query-gpu=timestamp,utilization.gpu,utilization.memory,memory.used,memory.free,temperature.gpu,power.draw \
        --format=csv,noheader,nounits 2>/dev/null
      sleep 1
    done
  ) > "$OUT/sample_nvidia.txt" 2>&1 &
  P7=$!
  # GPU per-process compute (TensorRT etc)
  ( for i in $(seq "$DUR"); do
      nvidia-smi --query-compute-apps=timestamp,pid,process_name,used_memory \
        --format=csv,noheader 2>/dev/null
      sleep 1
    done
  ) > "$OUT/sample_nvidia_procs.txt" 2>&1 &
  P8=$!
fi
wait $P1 $P2 $P3 $P4 ${P5:-} ${P6:-} ${P7:-} ${P8:-} 2>/dev/null
echo "[align_sample] done at $(date +%H:%M:%S) duration=${DUR}s" >&2
