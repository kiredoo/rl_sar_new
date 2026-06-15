This directory provides code for measuring the probalistic Worst-Case Execution Time (pWCET) of autoware callback functions, consisting of two main steps:

1. Measuring the execution time (ET) of the function.
2. Applying Extreme Value Theory (EVT) to estimate pWCET.

It contains several eBPF scripts, each with a specific task.

# Prerequisite

```
sudo apt-get install python3-bpfcc python3-jinja2 python3-statsmodels python3-scipy python3-numpy
```

To simplify the installation and management of eBPF applications, consider granting sudo permissions without requiring a password entry. This can be achieved by adding the following line to the `/etc/sudoers` file:
```
your_user_name ALL=(ALL:ALL) NOPASSWD: ALL
```
which enables root-level access without prompting for authentication.

### Lock CPU frequency

To make measurement more reliable, it's recommended to lock CPU frequencies.
We can do this by unifying `scaling_min_freq` and `scaling_max_freq`, in which frequency is represented by KHz.
To lock all frequencies, we can run

```
echo 3200000 | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_min_freq
echo 3200000 | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_max_freq
```
to lock them at 3.2GHz.

The command `cpupower frequency-info` can help pick up an appropriate Hz in our system.

# Measure ET of one callback function

The following image shows the execution time we want to measure. It also shows how we insert uprobes/kprobes.

![insert_probe.png](image/insert_probe.png)

Suppose we want to measure ET of the callback `NDTScanMatcher::callback_sensor_points`.
First, open a terminal and launch autoware.
Then open the second terminal and run the following command:

```
sudo python3 measure_et.py -i NDTScanMatcher::callback_sensor_points
...
WARNING:root:Attach uprobes for NDTScanMatcher::callback_sensor_points, mangled_name: _ZN14NDTScanMatcher22callback_sensor_pointsESt10shared_ptrIKN11sensor_msgs3msg12PointCloud2_ISaIvEEEE, elf: /home/chtseng18/repo/autoware/build/ndt_scan_matcher/ndt_scan_matcher
Collection process stops when hitting Ctrl+C or |samples| == 3000
```

Now, open the third terminal and play a rosbag. When rosbag stops playing,
turn to the second terminal, where you interrupt the process with Ctrl+C.
You will see the following message:

```
Collect 228 samples
...
resp_time_ns: 7864644, syscall_time_ns: 4359
resp_time_ns: 6651753, syscall_time_ns: 0
NDTScanMatcher::callback_sensor_points -- min: 35,674 ns, max: 14,829,650 ns, avg: 7,972,399 ns, stdev: 2,956,774
```
The above message shows the response time (that is, the time since the invocation of the function until it returns) and the time spent in the kernel (syscalls).
The execution time is resp_time_ns - syscall_time_ns.
We collect 228 samples of execution time, and the last line indicates their statistics.

# Measure ET for multiple callback functions

Since we know both the mangled and demangled function names after scanning
an opened ELF file, we can leverage this information to generate eBPF code
dynamically using a Jinja template, by inserting corresponding uprobe and
uretprobe for each callback function.

When we want to measure callback's ET, we can put all callbacks to be measured into a text file named `callbacks.txt`. Then launch autoware in one terminal, run the command
```
sudo python3 measure_ets.py -i callbacks.txt
```
in a second terminal.
Once `measure_ets.py` is ready, play the rosbag in a third terminal. When
playback is complete, return to the second terminal and press Ctrl+C. You
will see the results.

```
...
WARNING:root:vehicle_cmd_gate::VehicleCmdGate::onMrmState -- min: 2,579 ns, max: 128,064 ns, avg: 5,987 ns, stdev: 9,076, #samples: 298
WARNING:root:vehicle_cmd_gate::VehicleCmdGate::onTimer -- No statistics data, #samples: 0
WARNING:root:vehicle_cmd_gate::VehicleCmdGate::publishStatus -- min: 41,577 ns, max: 1,372,609 ns, avg: 91,659 ns, stdev: 144,068, #samples: 299
...
```
The results are also saved in `sampled_execution_time/*.json`,
which follows the format defined in the design document.

# Measure pWCET for autoware

The script `measure_aw_wcet.py` estimates pWCET for multiple autoware callback functions.
It is an automation script that do the following job:

![measure_aw_wcet_diagram.png](image/measure_aw_wcet_diagram.png)

The following bash script is what I did in practice:
```bash
for sn in `seq 1 5`; do
  if [[ -f .measure_ets_cache.json ]]; then
      sudo rm .measure_ets_cache.json
  fi
  python3 measure_aw_wcet.py -i 100 --callback-names-txt cb_names/callbacks_all_202502_part${sn}.txt --cool-down-seconds 10
done
```
where 100 is the number of loops in the above diagram.

Since collecting a sufficient number of block maxima is time-consuming, please reserve several hours for the script to complete. Collecting one block maximum takes approximately 3–5 minutes.

Alternatively, you can run:
```
python3 measure_aw_wcet.py -i 100 --callback-names-txt callbacks.txt
```
to measure only the callback functions listed in callbacks.txt.

If you only want to generate the report, you must first have at least a JSON file with a timestamp-style name (e.g. 20251202170443.json) in the sampled_execution_time folder, and then run:
```
python3 measure_aw_wcet.py -i 0
```

### Sampling config YAML

The Autoware launch/package paths, rosbag path, map path, vehicle model, sensor model, and sampling timing parameters are no longer hard-coded in `sampling_manager.py`.
They are loaded from `config/default_sampling.yaml` by default.

Example:
```bash
python3 measure_aw_wcet.py --config config/default_sampling.yaml -i 100 \
  --callback-names-txt cb_names/callbacks.txt
```

You can still override individual fields from the command line, for example:
```bash
python3 measure_aw_wcet.py --config config/default_sampling.yaml \
  --rosbag-path ~/autoware_map/another-bag \
  --map-path ~/autoware_map/another-map \
  --vehicle-model my_vehicle \
  --sensor-model my_sensor_kit
```

To view the full report, open `report/index.html` in your browser.

Here is an [example report](https://drive.google.com/file/d/156ms2yutUd3OrQrPPxRr-XUqUkMmN2hY/view?usp=sharing) generate on AGX Orin.

### Run measure_aw_wcet.py with heaphook

Sometimes we may want to replace built-in malloc/free with customized ones like
[heaphook](https://github.com/tier4/heaphook).
In situations like this, just add `--ld-preload` option. For example:

```
python3 measure_aw_wcet.py -i 100 --callback-names-txt callbacks.txt --ld-preload /path/to/libpreloaded_tlsf.so
```

Then the python script will set up the `LD_PRELOAD` variable before forking a process.

To confirm that it actually takes into effect, look for the pid of a forked process, and run `cat /proc/<pid>/maps` to see if /path/to/libpreloaded_tlsf.so exists in the output.

# pWCET GUI Launcher

In addition to running measure_aw_wcet.py from the command line, you can also use a simple GUI launcher:

```
python3 wcet_gui.py
```

The GUI allows you to:

Select the setup.bash to be sourced before running (ROS/Autoware environment)

Select the measure_aw_wcet.py script (if needed)

Select the sampling config YAML (optional; defaults to `config/default_sampling.yaml`)

Select one or more callbacks.txt files to run sequentially

Optionally select an LD_PRELOAD .so

Set num_sampling (-i), cool-down-seconds (optional), and extra CLI arguments

Each selected callbacks file will be run in sequence, and the log output will be shown in the GUI window.

# Running Autoware.Universe with CIE Applied

If you want to run **Autoware.Universe with CIE applied**, follow these steps:

1. Edit `sampling_manager_CIE.py`:
   - Update the paths of `rt_all_symlink.sh` and the CIE YAML file in  sampling_manager_CIE.py,
     so that they point to the correct locations on your machine.

2. Replace the original sampling manager:
   - Rename `sampling_manager_CIE.py` to `sampling_manager.py`.
   - Use this renamed file to **replace** the original `sampling_manager.py`.

3. Run as usual:
   - After this replacement, execute your normal measurement / launch workflow.
   - Autoware.Universe will then run **with CIE enabled**.

# Measuring Callback Functions in the Planning Simulator

If you want to measure **callback functions in the planning simulator**, you must use:

```
sudo python3 measure_ets.py -i callbacks.txt
```
The planning simulator requires you to manually input paths during execution, so it cannot be fully automated.

Because of this limitation:

There will be no pWCET calculation for the planning simulator.

You will only obtain metrics for that specific run, such as max, min, avg, etc.

In this context, we use the max value from the measurement as the WCET for each callback.

We also provide pWCET values specifically organized as input parameters for CIE under the `callback_to_node_latency` directory. Please refer to that folder for details.

# Final pWCET adjustment

In some cases, the original EVT/IESTA pWCET can become unrealistically large (e.g., heavy-tail or poor fit).
To keep the final pWCET value reasonable, we apply an **arctan inequality-based pWCET** as a replacement when the predefined conditions are triggered.

Use `final_result.py` to generate the final report:

Reads the original pWCET (IESTA) from an HTML report

Computes the arctan-based pWCET from timestamp JSON samples

Outputs the final value (either pWCET or arctan) into `final_result.xlsx`

Default input paths

HTML report: `report/index.html`

Timestamp JSONs: `sampled_execution_time/*.json`

Override input paths (optional)

You can change input locations via CLI arguments:

```
python3 final_result.py \
  --index-html /path/to/report/index.html \
  --json-glob "/path/to/sampled_execution_time/*.json" \
  --out final_result.xlsx
```

Minimal example
```
python3 final_result.py --out final_result.xlsx
```

The latest results are available in the **APPENDIX** section of `docs/AGATIME.md`.

# Other eBPF tools

eBPF is a powerful tool for observing system behavior.
In addition to measuring WCET, it can also perform the following tasks:

- [Measure Hz for callback functions](docs/measure_hzs.md)
- [Measure page faults triggered by callback functions](docs/measure_page_faults.md)
- [Measure malloc/free patterns of a callback function](docs/measure_malloc_free_patterns.md)

# Supplements
### ARM platform kernel configuration

Since ARM platforms have limited kprobe/uprobe support, users must manually enable these features.
For the NVidia AGX Orin, follow the instruction in
[KernelCustomization](https://docs.nvidia.com/jetson/archives/r36.2/DeveloperGuide/SD/Kernel/KernelCustomization.html). Then enable the kprobe events:

```
cd /usr/src/Linux_for_Tegra/source/kernel/kernel-jammy-src  # Use the path in your system

make menuconfig
  General architecture-dependent options  --->
  [*] Kprobes

cat .config  # See the current kernel config
make -j      # compile kernel. Once it is done, follow the kernel installation guide.
...
```

## Single-run ROS 2 target measurement

For non-Autoware or small ROS 2 targets, use `measure_single_target.py`.
It starts one target command, samples selected C++ functions once, writes raw JSON samples, and stops.

Examples:

```bash
python3 measure_single_target.py --config config/rl_itri_rl_sim_single.yaml
python3 measure_single_target.py --config config/rl_itri_rl_real_go2_single.yaml --target-cmd "ros2 run rl_ITRI rl_real_go2 eth0"
```

Candidate RL_ITRI function lists are provided in:

```text
cb_names/rl_itri_rl_sim_functions.txt
cb_names/rl_itri_rl_real_go2_functions.txt
```

See `docs/measure_rl_itri_single.md` for details.
