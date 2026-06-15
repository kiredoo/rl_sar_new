"""Bring up autoware, eBPF, and play rosbag to sample block maxima."""
from __future__ import annotations

import logging
import os
import shlex
import subprocess
import tempfile
import time

from measure_ets_utils import is_ebpf_loaded
from proc_manager import ProcManager
from python_cmd_utils import build_python_cmd
from sampling_config import SamplingConfig, load_sampling_config

_DEFAULT_REPO_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CFG = load_sampling_config(repo_dir=_DEFAULT_REPO_DIR)
_DEFAULT_CALLBACKS_TXT = _DEFAULT_CFG.callback_names_txt
DEFAULT_AW_ROSBAG = _DEFAULT_CFG.rosbag_path
DEFAULT_AW_cmd = _DEFAULT_CFG.build_ros2_launch_cmd()


def _make_wait_ready_func(timeout_seconds: int):
    return lambda log_fn: wait_aw_fully_loaded(log_fn, timeout_seconds=timeout_seconds)


def _legacy_runtime_config(
    num_sampling: int,
    callback_names_txt: str,
    cool_down_seconds: float,
    ld_preload: str | None,
    *,
    repo_dir: str = _DEFAULT_REPO_DIR,
) -> SamplingConfig:
    cfg = load_sampling_config(repo_dir=repo_dir)
    cfg.num_sampling = num_sampling
    cfg.callback_names_txt = callback_names_txt
    cfg.cool_down_seconds = cool_down_seconds
    cfg.ld_preload = ld_preload
    return cfg


def do_aw_sampling(
    num_sampling: int | None = None,
    callback_names_txt: str | None = None,
    cool_down_seconds: float | None = None,
    ld_preload: str | None = None,
    *,
    sampling_config: SamplingConfig | None = None,
) -> None:
    cfg = sampling_config or _legacy_runtime_config(
        num_sampling or _DEFAULT_CFG.num_sampling,
        callback_names_txt or _DEFAULT_CFG.callback_names_txt,
        cool_down_seconds if cool_down_seconds is not None else _DEFAULT_CFG.cool_down_seconds,
        ld_preload,
    )

    mgr = SamplingManager(
        callback_names_txt=cfg.callback_names_txt,
        ros2_launch_cmd=cfg.build_ros2_launch_cmd(),
        rosbag_fullpath=cfg.rosbag_path,
        wait_ros2_func=_make_wait_ready_func(cfg.ready_timeout_seconds),
        ld_preload=cfg.ld_preload,
        elf_path_must_contain=cfg.elf_path_must_contain,
        bag_play_rate_x86=cfg.bag_play_rate_x86,
        bag_play_rate_arm=cfg.bag_play_rate_arm,
        burn_in_seconds=cfg.burn_in_seconds,
        min_pause_seconds=cfg.min_pause_seconds,
        sample_duration_seconds_without_bag=cfg.sample_duration_seconds_without_bag,
    )
    mgr.sample_many_times(cfg.num_sampling, cool_down_seconds=cfg.cool_down_seconds)


def wait_aw_fully_loaded(log_fn, timeout_seconds=180):
    logging.info("Wait autoware to be fully loaded...")

    cmd = shlex.split(f"tail -n 3 {log_fn}")
    logging.info("Use %s to check AW readiness", cmd)
    done = False
    unexpected_logs = [
        "[perception.object_recognition.detection.voxel_based_compare_map_filter]: service not available, waiting again",
        "[localization.util.pose_initializer_node]: waiting response",
    ]
    total_wait_time = 0
    prev_last_lines_str = ""
    num_seconds_of_unchanging_log = 0
    while not done:
        try:
            last_lines_str = subprocess.check_output(cmd, encoding="utf-8")
            last_lines = last_lines_str.splitlines()
        except subprocess.CalledProcessError:
            logging.error("Fail to execute %s", cmd)
            last_lines_str = ""
            last_lines = []

        if prev_last_lines_str == last_lines_str:
            num_seconds_of_unchanging_log += 1
        else:
            num_seconds_of_unchanging_log = 0

        if (
            last_lines_str
            and prev_last_lines_str == last_lines_str
            and num_seconds_of_unchanging_log > 10
            and "traffic_light_recognition" in last_lines[-1]
        ):
            done = True
        if last_lines and "Package 'autoware_launch' not found" in last_lines[-1]:
            logging.error("Please source autoware/install/setup.bash and then restarts this script")
            done = True
            return 1
        if last_lines:
            for log in unexpected_logs:
                if log in last_lines[-1]:
                    logging.error("autoware starts abnormally, try next round")
                    done = True
                    return 1
        if not done:
            time.sleep(1)
        total_wait_time += 1
        if total_wait_time > timeout_seconds:
            logging.error("It is unlikely to launch autoware for more than %s seconds", timeout_seconds)
            done = True
            return 1
        prev_last_lines_str = last_lines_str
    logging.info("Autoware is fully loaded.")
    return 0


class SamplingManager:
    """Sampling execution time of callback functions by launching ros2 application once."""

    def __init__(
        self,
        callback_names_txt=_DEFAULT_CALLBACKS_TXT,
        ros2_launch_cmd=None,
        rosbag_fullpath="",
        wait_ros2_func=wait_aw_fully_loaded,
        ld_preload=None,
        elf_path_must_contain="",
        bag_play_rate_x86: float = _DEFAULT_CFG.bag_play_rate_x86,
        bag_play_rate_arm: float = _DEFAULT_CFG.bag_play_rate_arm,
        burn_in_seconds: float = _DEFAULT_CFG.burn_in_seconds,
        min_pause_seconds: float = _DEFAULT_CFG.min_pause_seconds,
        sample_duration_seconds_without_bag: float = _DEFAULT_CFG.sample_duration_seconds_without_bag,
    ):
        self._ros2_launch_cmd = ros2_launch_cmd or list(DEFAULT_AW_cmd)
        self._wait_ros2_proc_ready_func = wait_ros2_func
        self._rosbag_fullpath = rosbag_fullpath
        self._ros2_terminal_logfile = f"ros2_terminal_{os.getpid()}.log"
        self._ld_preload = ld_preload
        self._bag_play_rate_x86 = bag_play_rate_x86
        self._bag_play_rate_arm = bag_play_rate_arm
        self._burn_in_seconds = burn_in_seconds
        self._min_pause_seconds = min_pause_seconds
        self._sample_duration_seconds_without_bag = sample_duration_seconds_without_bag
        ebpf_args = ["-i", callback_names_txt]
        if elf_path_must_contain:
            ebpf_args += ["--elf-path-must-contain", elf_path_must_contain]
        self._ebpf_cmd = build_python_cmd("measure_ets.py", ebpf_args, use_sudo=True)

    @property
    def ros2_launch_cmd(self):
        return self._ros2_launch_cmd

    @ros2_launch_cmd.setter
    def ros2_launch_cmd(self, cmd):
        self._ros2_launch_cmd = cmd

    @property
    def wait_ros2_proc_ready_func(self):
        return self._wait_ros2_proc_ready_func

    @wait_ros2_proc_ready_func.setter
    def wait_ros2_proc_ready_func(self, func):
        self._wait_ros2_proc_ready_func = func

    @property
    def rosbag_fullpath(self):
        return self._rosbag_fullpath

    @rosbag_fullpath.setter
    def rosbag_fullpath(self, path):
        if os.path.isfile(path) or os.path.isdir(path):
            self._rosbag_fullpath = path
        else:
            logging.warning("No such file or directory: %s", path)

    @property
    def ebpf_cmd(self):
        return self._ebpf_cmd

    @ebpf_cmd.setter
    def ebpf_cmd(self, cmd):
        self._ebpf_cmd = cmd

    def sample_once(self):
        logging.warning("Start sampling, log file: %s", self._ros2_terminal_logfile)
        ros2_launch_proc = ProcManager(
            self._ros2_launch_cmd,
            log_filename=self._ros2_terminal_logfile,
            ld_preload=self._ld_preload,
        )
        ebpf_proc = None
        expect_proc = None
        script_path = None

        ros2_launch_proc.start()
        try:
            if self._wait_ros2_proc_ready_func:
                logging.warning(
                    "Wait for ros2 launch to be fully loaded, check %s for details",
                    self._ros2_terminal_logfile,
                )
                ret = self._wait_ros2_proc_ready_func(self._ros2_terminal_logfile)
                if ret != 0:
                    return ret

            if self.rosbag_fullpath and os.path.exists(self.rosbag_fullpath):
                if os.uname().machine == "aarch64":
                    rate = self._bag_play_rate_arm
                else:
                    rate = self._bag_play_rate_x86

                bag_cmd = f"ros2 bag play -r {rate} {shlex.quote(self.rosbag_fullpath)}"

                fd, script_path = tempfile.mkstemp(prefix="rosbag_play_", suffix=".exp", dir=os.getcwd())
                os.close(fd)
                script_content = f"""#!/usr/bin/expect -f
set cmd \"{bag_cmd}\"
spawn sh -c $cmd
sleep {self._burn_in_seconds}
send \" \"
set t0 [clock seconds]
while 1 {{
    if {{[file exists \"/tmp/ebpf_is_loaded\"] && ([clock seconds] - $t0) >= {self._min_pause_seconds} }} {{
        break
    }}
    sleep 1
}}
send \" \"
sleep 26
expect eof
"""
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(script_content)
                os.chmod(script_path, 0o755)

                logging.warning("Start rosbag expect script: %s", script_path)
                expect_proc = ProcManager(["expect", script_path], silent=True)
                expect_proc.start()

                time.sleep(self._burn_in_seconds + 0.5)

                logging.warning("Burn-in finished, start eBPF measurement process")
                ebpf_proc = ProcManager(self.ebpf_cmd)
                ebpf_proc.start()
                logging.warning(
                    "eBPF process started; expect script will resume rosbag after "
                    "eBPF is ready and pause >= %.0f seconds",
                    self._min_pause_seconds,
                )

                expect_proc.wait()
                logging.warning("rosbag playback and expect script finished")
            else:
                logging.warning("No bag to play; start eBPF directly and sample for %.1f seconds", self._sample_duration_seconds_without_bag)
                ebpf_proc = ProcManager(self.ebpf_cmd)
                ebpf_proc.start()
                logging.warning("Wait for eBPF program to be fully loaded")
                while not is_ebpf_loaded():
                    time.sleep(1)
                time.sleep(self._sample_duration_seconds_without_bag)

            return 0
        finally:
            try:
                if ebpf_proc is not None:
                    logging.warning("Terminating eBPF process, please wait.")
                    ebpf_proc.stop()
            finally:
                try:
                    if expect_proc is not None:
                        logging.warning("Terminating expect (rosbag) process, please wait.")
                        expect_proc.stop()
                finally:
                    if script_path is not None and os.path.exists(script_path):
                        try:
                            os.remove(script_path)
                        except OSError:
                            pass
                    logging.warning("Terminating ros2 process, please wait.")
                    ros2_launch_proc.stop()

    def sample_many_times(self, num_sampling: int, cool_down_seconds=60):
        for idx in range(num_sampling):
            logging.warning("start sampling: %d/%d", idx + 1, num_sampling)
            self.sample_once()
            logging.warning("end sampling: %d/%d", idx + 1, num_sampling)
            if cool_down_seconds > 0:
                logging.info("Cool down for %.3f seconds to avoid overheat", cool_down_seconds)
                time.sleep(cool_down_seconds)

    def __str__(self):
        return (
            f"SamplingManager(ros2_launch_cmd={self.ros2_launch_cmd}, "
            f"logfile={self._ros2_terminal_logfile}, "
            f"rosbag={self._rosbag_fullpath})"
        )
