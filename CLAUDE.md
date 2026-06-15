# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`rl_sar` is a C++17 framework for simulation verification and physical deployment of robot reinforcement learning (RL) locomotion policies. It supports quadruped, wheeled, and humanoid robots. The ITRI fork extends the upstream project with ITRI-specific robots (idog, idogc, leo) and real-time timing analysis.

## Build Commands

```bash
# ROS build (requires sourced ROS environment)
./build.sh                      # Build all ROS packages
./build.sh rl_ITRI              # Build specific package
./build.sh -c                   # Clean all artifacts and symlinks

# CMake build (hardware deployment only, no ROS)
./build.sh -m                   # cmake_build/bin/ and cmake_build/lib/
./build.sh -mj                  # With MuJoCo simulator support

# ROS version-specific activation
source devel/setup.bash         # ROS1 Noetic
source install/setup.bash       # ROS2 Foxy/Humble
```

**Important:** The build system manages `package.xml` symlinks automatically — `package.ros1.xml` or `package.ros2.xml` is symlinked based on `$ROS_DISTRO`. Don't edit `package.xml` directly.

## Running

```bash
# Simulation (Gazebo) — runs both Gazebo and rl_sim in one tmux-like flow
./run.sh -r <ROBOT> -w <WORLD>          # ROS2 default
./run.sh -r idog -w stairs -gui         # With GUI

# Manual Gazebo + rl_sim (ROS2)
source install/setup.bash
ros2 launch rl_ITRI gazebo.launch.py rname:=go2
ros2 run rl_ITRI rl_sim

# MuJoCo simulation (CMake build required)
./cmake_build/bin/rl_sim_mujoco <ROBOT> <SCENE>

# Real robot (example)
ros2 run rl_ITRI rl_real_go2 <NETWORK_INTERFACE>
./cmake_build/bin/rl_real_go2 <NETWORK_INTERFACE>   # No ROS
```

Keyboard controls: `0` = stand up, `9` = sit down, `1` = start RL, `w/a/s/d` = move, `q/e` = rotate, `Space` = reset commands.

## Architecture

### Package Structure

```
src/
  rl_ITRI/           — Main package (executables + core library)
  rl_ITRI_zoo/       — Robot URDF/xacro descriptions (<ROBOT>_description/)
  robot_msgs/        — Custom ROS message types
  robot_joint_controller/  — Gazebo joint controller plugin
  motor_msg/         — Motor-level ROS messages
policy/
  <ROBOT>/base.yaml          — Physical joint order, kp/kd, default_dof_pos
  <ROBOT>/<CONFIG>/config.yaml  — RL-specific params (obs size, scaling, clipping)
  <ROBOT>/<CONFIG>/<POLICY>.pt  — Libtorch JIT model
  <ROBOT>/<CONFIG>/<POLICY>.onnx — ONNX model (alternative)
```

### Core Library (`src/rl_ITRI/library/core/`)

| Module | Role |
|--------|------|
| `rl_sdk` | Base `RL` class — reads YAML config, runs `Forward()`, `StateController()`, motor output computation |
| `fsm` | Generic FSM engine — `FSMState` (Enter/Run/Exit/CheckChange) + `FSM` manager |
| `inference_runtime` | Abstraction over libtorch / onnxruntime; selected at compile time via `USE_TORCH`/`USE_ONNX` |
| `loop` | `LoopFunc` — real-time periodic thread with CPU pinning and phase offset |
| `observation_buffer` | Sliding history window for proprioceptive observations |
| `motion_loader` | Loads pre-defined motion sequences for dance/skill states |
| `logger` | Colored console logger |

### Robot-Specific Layer

**FSM states** (`src/rl_ITRI/fsm_robot/fsm_<ROBOT>.hpp`): Each robot defines its state machine in a dedicated header using `RLFSMState` (subclass of `FSMState`). Common states: `Passive → GetUp → Running(RL)`. `fsm_all.hpp` aggregates all robot headers.

**Robot executable** (`src/rl_ITRI/src/rl_real_<ROBOT>.cpp` / `rl_sim.cpp`): Subclasses `RL`, implements `GetState()` (read hardware/sim state → `RobotState`) and `SetCommand()` (write `RobotCommand` → hardware/sim). Override `Forward()` when custom obs processing is needed.

**Compile-time ROS switching**: Source files use `#ifdef USE_ROS1 / USE_ROS2 / USE_CMAKE` blocks for topic types and node APIs.

### Data Flow (each control cycle)

```
Hardware/Sim → GetState() → RobotState → StateController() → FSM.Run()
  → Forward() [RL inference] → ComputeOutput() → RobotCommand → SetCommand() → Hardware/Sim
```

`LoopFunc` drives the cycle at a fixed period (typically 2 ms / 500 Hz).

## Adding a New Robot

Create the following files (use `go2` or `idog` as reference):

```
policy/<ROBOT>/base.yaml                         # joint order, limits, default_dof_pos
policy/<ROBOT>/<CONFIG>/config.yaml              # RL hyperparams, obs definition
src/rl_ITRI_zoo/<ROBOT>_description/             # URDF/xacro + CMakeLists + package.ros{1,2}.xml
src/rl_ITRI/fsm_robot/fsm_<ROBOT>.hpp           # FSM state definitions
src/rl_ITRI/fsm_robot/fsm_all.hpp               # Add #include "fsm_<ROBOT>.hpp"
src/rl_ITRI/src/rl_real_<ROBOT>.cpp             # Real robot implementation
src/rl_ITRI/include/rl_real_<ROBOT>.hpp
```

The `joint_mapping` field in `config.yaml` remaps policy output indices to physical joint order when sim-to-real joint ordering differs.

## Config Files

`base.yaml` controls physical robot parameters (joint names must match URDF, order determines motor command indexing).  
`config.yaml` controls RL policy parameters — `observations` list order must match the training environment.

Enabling CSV logging for actuator network training: uncomment `#define CSV_LOGGER` near the top of the relevant `.hpp` file.

## Enabling `#define PLOT` / `#define CSV_LOGGER`

Both are commented out by default in the `.hpp` headers. `PLOT` uses `matplotlibcpp` for live visualization; `CSV_LOGGER` writes motor data to `policy/<ROBOT>/motor.csv`.
