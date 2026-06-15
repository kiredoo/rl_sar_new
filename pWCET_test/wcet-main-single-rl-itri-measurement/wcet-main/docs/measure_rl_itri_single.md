# Single-run measurement for RL_ITRI functions

This mode is intended for measuring one ROS 2 target once, without Autoware-specific launch, rosbag, or report generation.
It starts one target command, starts `measure_ets.py` once, samples for a fixed duration, writes one raw JSON file under `sampled_execution_time/`, and then shuts everything down.

## rl_sim

```bash
source /opt/ros/humble/setup.bash
source /path/to/your/rl_ws/install/setup.bash
cd /path/to/wcet
python3 measure_single_target.py --config config/rl_itri_rl_sim_single.yaml
```

The callback/function list is:

```text
cb_names/rl_itri_rl_sim_functions.txt
```

## rl_real_go2

Edit the network interface in `config/rl_itri_rl_real_go2_single.yaml` first:

```yaml
target:
  command: ros2 run rl_ITRI rl_real_go2 eth0
```

Then run:

```bash
source /opt/ros/humble/setup.bash
source /path/to/your/rl_ws/install/setup.bash
cd /path/to/wcet
python3 measure_single_target.py --config config/rl_itri_rl_real_go2_single.yaml
```

## Attach to an already-running target

If the target must be launched manually, run it in another terminal and then attach:

```bash
python3 measure_single_target.py \
  --config config/rl_itri_rl_sim_single.yaml \
  --no-start-target \
  --duration-seconds 30
```

## Important notes

- The tool measures demangled C++ function names found in the target executable or shared libraries.
- It is not limited to ROS callbacks. Any visible C++ function symbol can be listed.
- If all functions print `Cannot find function definition`, check:
  - the target is already running when eBPF starts;
  - the executable was built with symbols, ideally Debug or RelWithDebInfo;
  - `measurement.elf_path_must_contain` matches the actual opened ELF path shown by `lsof`;
  - `.measure_ets_cache.json` is removed or `ignore_cache: true` is enabled.
- This mode writes raw samples only. It does not run EVT or generate the HTML report by default.
