# GXF Replay Tools Starter

These tools prepare the `rl_sim` rosbag for a no-touch GXF replay experiment.
They do **not** require GXF yet. They only require ROS 2 and the `rl_ITRI` workspace to be sourced.

## 1. Source ROS 2 and your workspace

```bash
source /opt/ros/humble/setup.bash
source ~/rl_sar_new/rl_sar/install/setup.bash
```

## 2. Convert rosbag to JSONL

```bash
python3 bag_to_jsonl.py \
  --bag ~/rl_sar_new/rl_sar/pWCET_test/rlsim_gxf_logs/baseline_idogc_earth_cmd_vel \
  --out ~/rl_sar_new/rl_sar/pWCET_test/rlsim_gxf_replay_jsonl
```

Expected outputs:

```text
imu.jsonl
cmd_vel.jsonl
robot_joint_controller__state.jsonl
robot_joint_controller__command.jsonl
```

## 3. Summarize topic timing

```bash
python3 summarize_jsonl.py \
  --dir ~/rl_sar_new/rl_sar/pWCET_test/rlsim_gxf_replay_jsonl \
  --out ~/rl_sar_new/rl_sar/pWCET_test/rlsim_gxf_replay_jsonl/summary.json
```

## 4. Create aligned replay frames

```bash
python3 make_replay_frames.py \
  --jsonl-dir ~/rl_sar_new/rl_sar/pWCET_test/rlsim_gxf_replay_jsonl \
  --out ~/rl_sar_new/rl_sar/pWCET_test/rlsim_gxf_replay_jsonl/replay_frames.jsonl
```

`replay_frames.jsonl` is the file the first `ReplayInputCodelet` / Holoscan Operator should read.
Each frame is driven by one `/robot_joint_controller/command` timestamp and contains the latest state, imu, and cmd_vel available before that timestamp.
