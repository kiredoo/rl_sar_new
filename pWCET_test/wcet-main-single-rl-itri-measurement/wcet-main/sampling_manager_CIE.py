"""
Bring up autoware, eBPF, and play rosbag to sample a block maxima.
"""
import io
import logging
import os
import shlex
import signal
import subprocess
import time
import re  # for CIE patterns
import shutil  # for which()
import tempfile

from measure_ets_utils import is_ebpf_loaded
from proc_manager import ProcManager
from python_cmd_utils import build_python_cmd
from sampling_config import SamplingConfig, load_sampling_config

_DEFAULT_REPO_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CFG = load_sampling_config(repo_dir=_DEFAULT_REPO_DIR)
_BAG_PLAY_RATE_ON_ARM = _DEFAULT_CFG.bag_play_rate_arm
_BAG_PLAY_RATE_ON_X86 = _DEFAULT_CFG.bag_play_rate_x86
_DEFAULT_CALLBACKS_TXT = _DEFAULT_CFG.callback_names_txt

DEFAULT_AW_ROSBAG = _DEFAULT_CFG.rosbag_path
DEFAULT_AW_cmd = _DEFAULT_CFG.build_ros2_launch_cmd()

# =========================
# CIE integration (tmux)
# =========================

class _CieDefaults:
    """
    Built-in defaults so you don't need to export env vars.
    Adjust paths if your repo layout differs.
    """
    ENABLE = True  # set to False to disable CIE flow without touching caller
    SCRIPT = os.path.expanduser(
        "~/aga/autoware_CIE_MP/src/callback_isolated_executor/scripts/rt_all_symlink.sh"
    )
    YAML = os.path.expanduser(
        "~/aga/autoware_CIE_MP/src/callback_isolated_executor/scripts/"
        "20251003_cbg304_25edf-cpu_190fifo90_89cfs_align-target-cp_tight-dl_caret-awu.yaml"
    )
    EXPECTED_UNAPPLIED = 23              # target threshold
    TMUX_SESSION = "aga_wcet"            # visible terminal session
    TMUX_WINDOW  = "cie"                 # window name
    WAIT_READY_TIMEOUT_S = 180           # wait for drop<=EXPECTED + prompt to apply
    FINALIZE_TIMEOUT_S   = 60            # wait for cleanup prompt at the end

    # New: auto open GUI terminal and attach to tmux for live view
    ATTACH_ON_START = True               # set False to disable auto attach window
    TERMINAL_CANDIDATES = [
        "gnome-terminal",                # primary
        "x-terminal-emulator",           # Debian/Ubuntu alternatives
        "konsole",
        "xfce4-terminal",
        "mate-terminal",
        "lxterminal",
        "alacritty",
        "kitty",
        "terminator"
    ]

    # Robust apply options
    STABLE_BELOW_SEC = 2.0               # unapplied<=EXPECTED for this long → force Enter
    POLL_INTERVAL_SEC = 0.5              # check pane every 0.5s
    CAPTURE_LAST_LINES = 4000            # lines captured from pane buffer
    DEBUG_DUMP = False                   # write pane snapshot to cie_tmux_debug.log


class _CieSession:
    """
    Manage a visible terminal (tmux window) that runs:
        ./rt_all_symlink.sh --apply-root <yaml>
    and interact with it by sending <Enter> twice:
      1) when conditions for apply are satisfied
      2) at the end when "Press enter to exit and remove cgroups" appears

    Optionally open a GUI terminal and auto-attach to the tmux session for live viewing.
    """
    def __init__(self,
                 enable=_CieDefaults.ENABLE,
                 script=_CieDefaults.SCRIPT,
                 yaml_path=_CieDefaults.YAML,
                 expected=_CieDefaults.EXPECTED_UNAPPLIED,
                 session=_CieDefaults.TMUX_SESSION,
                 window=_CieDefaults.TMUX_WINDOW,
                 wait_ready_timeout=_CieDefaults.WAIT_READY_TIMEOUT_S,
                 finalize_timeout=_CieDefaults.FINALIZE_TIMEOUT_S,
                 attach_on_start=_CieDefaults.ATTACH_ON_START,
                 terminal_candidates=_CieDefaults.TERMINAL_CANDIDATES):
        self.enable = bool(enable)
        self.script = script
        self.yaml   = yaml_path
        self.expected = int(expected)
        self.session = session
        self.window  = window
        self.wait_ready_timeout = int(wait_ready_timeout)
        self.finalize_timeout   = int(finalize_timeout)
        self.attach_on_start    = bool(attach_on_start)
        self.terminal_candidates = list(terminal_candidates)
        self._pane = None

        # patterns observed from your logs
        # 1) "Apply SCHED_DEADLINE now?  ⏎ = apply"
        self._re_prompt_apply_1 = re.compile(r"Apply SCHED_DEADLINE now\?", re.IGNORECASE)
        # 2) backup trigger: "⏎ = apply" (contains the return symbol)
        self._re_prompt_apply_2 = re.compile(r"⏎\s*=\s*apply", re.IGNORECASE)
        # "Press enter to exit and remove cgroups"
        self._re_prompt_exit  = re.compile(r"Press enter to exit and remove cgroups", re.IGNORECASE)
        # capture unapplied_num_=
        self._re_unapplied = re.compile(r"unapplied_num_=\s*(\d+)")

        # state for robust matching (order-independent)
        self._last_seen_prompt_ts = None
        self._last_seen_below_ts  = None
        self._last_unapplied_val  = None

    def _tmux(self, *args):
        return subprocess.run(["tmux", *args], check=False, capture_output=True, text=True)

    def _ensure_tmux(self):
        # create session if not exists
        if self._tmux("has-session", "-t", self.session).returncode != 0:
            self._tmux("new-session", "-d", "-s", self.session, "-n", self.window, "bash")
        else:
            self._tmux("new-window", "-t", f"{self.session}:", "-n", self.window, "bash")
        out = self._tmux("display-message", "-p", "-t", f"{self.session}:{self.window}.0", "#{pane_id}")
        self._pane = out.stdout.strip()

    def _send_keys(self, keys):
        self._tmux("send-keys", "-t", self._pane, keys)

    def _enter(self):
        self._tmux("send-keys", "-t", self._pane, "Enter")

    def _dump(self, last_lines=_CieDefaults.CAPTURE_LAST_LINES):
        r = self._tmux("capture-pane", "-p", "-t", self._pane, "-S", f"-{last_lines}")
        return r.stdout if r.returncode == 0 else ""

    def _try_open_terminal_attach(self):
        """
        Try to open a GUI terminal that runs: tmux attach -t <session>.
        Non-blocking; failures are logged but ignored (headless servers).
        """
        if not self.attach_on_start:
            return
        if not os.environ.get("DISPLAY"):
            logging.info("[CIE] DISPLAY not set; skip opening GUI terminal.")
            return
        term = None
        for cand in self.terminal_candidates:
            if shutil.which(cand):
                term = cand
                break
        if not term:
            logging.info("[CIE] no GUI terminal found from candidates; skip attach window.")
            return
        attach_cmd = f"tmux attach -t {shlex.quote(self.session)}"
        if term in ("gnome-terminal", "mate-terminal", "xfce4-terminal", "lxterminal", "alacritty", "kitty", "terminator"):
            cmd = [term, "--", "bash", "-lc", attach_cmd]
        elif term in ("konsole",):
            cmd = [term, "-e", "bash", "-lc", attach_cmd]
        else:
            cmd = [term, "-e", "bash", "-lc", attach_cmd]
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logging.info("[CIE] opened GUI terminal: %s", " ".join(cmd))
        except Exception as e:  # noqa
            logging.info("[CIE] failed to open GUI terminal (%s): %s", term, e)

    def start(self):
        if not self.enable:
            logging.info("[CIE] disabled")
            return True
        if not os.path.isfile(self.script):
            logging.error("[CIE] script not found: %s", self.script)
            return False
        if not os.path.isfile(self.yaml):
            logging.error("[CIE] yaml not found: %s", self.yaml)
            return False
        self._ensure_tmux()
        cmd = f"{shlex.quote(self.script)} --apply-root {shlex.quote(self.yaml)}"
        logging.info("[CIE] launch in tmux: %s", cmd)
        self._send_keys(cmd)
        self._enter()
        self._try_open_terminal_attach()
        # reset state
        self._last_seen_prompt_ts = None
        self._last_seen_below_ts  = None
        self._last_unapplied_val  = None
        return True

    def _update_state_from_buf(self, buf):
        now = time.time()
        # prompt?
        if self._re_prompt_apply_1.search(buf) or self._re_prompt_apply_2.search(buf):
            if not self._last_seen_prompt_ts:
                logging.info("[CIE] detected apply prompt")
            self._last_seen_prompt_ts = now
        # number?
        m = self._re_unapplied.findall(buf)
        if m:
            cur = int(m[-1])
            if cur != self._last_unapplied_val:
                logging.debug("[CIE] unapplied_num_=%d", cur)
            self._last_unapplied_val = cur
            if cur <= self.expected:
                self._last_seen_below_ts = now

    def _should_force_enter(self):
        """
        True when unapplied <= expected and remained below for STABLE_BELOW_SEC.
        """
        if self._last_seen_below_ts is None:
            return False
        return (time.time() - self._last_seen_below_ts) >= _CieDefaults.STABLE_BELOW_SEC

    def _should_apply(self):
        """
        Apply when (prompt seen recently AND unapplied seen <= expected recently),
        regardless of ordering. As a backup, also apply if we've stayed <= expected
        for STABLE_BELOW_SEC (even if prompt was missed).
        """
        # Main condition: both signals have been observed (order-agnostic)
        if self._last_seen_below_ts and self._last_seen_prompt_ts:
            return True
        # Backup: stable-below for a while
        if self._should_force_enter():
            logging.info("[CIE] unapplied<=%d stable for %.1fs → force apply",
                         self.expected, _CieDefaults.STABLE_BELOW_SEC)
            return True
        return False

    def wait_and_apply(self):
        """
        Wait until conditions to apply are satisfied, then press Enter once.
        Conditions (any of the following):
          - Prompt 'Apply SCHED_DEADLINE now?' (or '⏎ = apply') seen AND
            unapplied_num_ <= expected seen; order doesn't matter.
          - OR unapplied_num_ <= expected remains true for STABLE_BELOW_SEC.
        """
        if not self.enable:
            return True
        t0 = time.time()
        while time.time() - t0 < self.wait_ready_timeout:
            buf = self._dump()
            if _CieDefaults.DEBUG_DUMP:
                with open("cie_tmux_debug.log", "a", encoding="utf-8") as f:
                    f.write(buf + "\n" + ("-"*80) + "\n")
            self._update_state_from_buf(buf)
            if self._should_apply():
                logging.info("[CIE] sending Enter to apply SCHED_*")
                self._enter()
                return True
            time.sleep(_CieDefaults.POLL_INTERVAL_SEC)
        logging.warning("[CIE] wait_and_apply timeout within %ds", self.wait_ready_timeout)
        return False

    def finalize_and_cleanup(self):
        """Before stopping AW, press Enter once when cleanup prompt appears, then close tmux window."""
        if not self.enable:
            return
        t0 = time.time()
        while time.time() - t0 < self.finalize_timeout:
            buf = self._dump()
            if self._re_prompt_exit.search(buf):
                logging.info("[CIE] cleanup prompt detected; sending Enter to remove cgroups ...")
                self._enter()
                break
            time.sleep(0.5)
        self._tmux("kill-window", "-t", f"{self.session}:{self.window}")
        logging.info("[CIE] tmux window closed")

    def abort(self):
        if not self.enable:
            return
        logging.warning("[CIE] abort(): kill tmux window")
        self._tmux("kill-window", "-t", f"{self.session}:{self.window}")

# =========================
# End of CIE integration
# =========================


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
):
    cfg = sampling_config or _legacy_runtime_config(
        num_sampling or _DEFAULT_CFG.num_sampling,
        callback_names_txt or _DEFAULT_CFG.callback_names_txt,
        cool_down_seconds if cool_down_seconds is not None else _DEFAULT_CFG.cool_down_seconds,
        ld_preload,
    )
    mgr = SamplingManager(callback_names_txt=cfg.callback_names_txt,
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
                          cie_enable=cfg.cie.enable,
                          cie_script=cfg.cie.script,
                          cie_yaml=cfg.cie.yaml_path,
                          cie_expected_unapplied=cfg.cie.expected_unapplied,
                          cie_tmux_session=cfg.cie.tmux_session,
                          cie_tmux_window=cfg.cie.tmux_window,
                          cie_wait_ready_timeout=cfg.cie.wait_ready_timeout_s,
                          cie_finalize_timeout=cfg.cie.finalize_timeout_s,
                          cie_attach_on_start=cfg.cie.attach_on_start,
                          cie_terminal_candidates=cfg.cie.terminal_candidates)
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

        if (last_lines_str and
            prev_last_lines_str == last_lines_str and
            num_seconds_of_unchanging_log > 10 and
            "traffic_light_recognition" in last_lines[-1]):
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
    """
    Sampling execution time of callback functions by launching ros2 application once
    """
    def __init__(self, callback_names_txt=_DEFAULT_CALLBACKS_TXT, ros2_launch_cmd=None, rosbag_fullpath="", wait_ros2_func=wait_aw_fully_loaded, ld_preload=None, elf_path_must_contain="",
                 bag_play_rate_x86: float = _DEFAULT_CFG.bag_play_rate_x86,
                 bag_play_rate_arm: float = _DEFAULT_CFG.bag_play_rate_arm,
                 burn_in_seconds: float = _DEFAULT_CFG.burn_in_seconds,
                 min_pause_seconds: float = _DEFAULT_CFG.min_pause_seconds,
                 sample_duration_seconds_without_bag: float = _DEFAULT_CFG.sample_duration_seconds_without_bag,
                 # Optional overrides for CIE (you can ignore these; defaults above are fine)
                 cie_enable=_CieDefaults.ENABLE,
                 cie_script=_CieDefaults.SCRIPT,
                 cie_yaml=_CieDefaults.YAML,
                 cie_expected_unapplied=_CieDefaults.EXPECTED_UNAPPLIED,
                 cie_tmux_session=_CieDefaults.TMUX_SESSION,
                 cie_tmux_window=_CieDefaults.TMUX_WINDOW,
                 cie_wait_ready_timeout=_CieDefaults.WAIT_READY_TIMEOUT_S,
                 cie_finalize_timeout=_CieDefaults.FINALIZE_TIMEOUT_S,
                 cie_attach_on_start=_CieDefaults.ATTACH_ON_START,
                 cie_terminal_candidates=_CieDefaults.TERMINAL_CANDIDATES):
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

        # CIE hook instance (visible terminal via tmux)
        self._cie = _CieSession(enable=cie_enable,
                                script=cie_script,
                                yaml_path=cie_yaml,
                                expected=cie_expected_unapplied,
                                session=cie_tmux_session,
                                window=cie_tmux_window,
                                wait_ready_timeout=cie_wait_ready_timeout,
                                finalize_timeout=cie_finalize_timeout,
                                attach_on_start=cie_attach_on_start,
                                terminal_candidates=cie_terminal_candidates)

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
        """
        Sampling the execution time of callback functions by launching ros2 and eBPF program.
        This function controls the life cycle of ros2/eBPF process + CIE tmux terminal.
        """
        logging.warning("Start sampling, log file: %s", self._ros2_terminal_logfile)

        ros2_launch_proc = None
        ebpf_proc = None
        expect_proc = None
        script_path = None
        cie_started = False
        cie_apply_completed = False

        try:
            if not self._cie.start():
                return -1
            cie_started = True

            ros2_launch_proc = ProcManager(self._ros2_launch_cmd,
                                           log_filename=self._ros2_terminal_logfile,
                                           ld_preload=self._ld_preload)
            ros2_launch_proc.start()

            if self._wait_ros2_proc_ready_func:
                logging.warning("Wait for ros2 launch to be fully loaded, check %s for details",
                                self._ros2_terminal_logfile)
                ret = self._wait_ros2_proc_ready_func(self._ros2_terminal_logfile)
                if ret != 0:
                    return ret

                ros2_launch_proc = self._apply_cie_until_ok(ros2_launch_proc)
                cie_apply_completed = True

            # ros2_launch_proc.make_proc_rt()

            ebpf_proc = ProcManager(self.ebpf_cmd)
            ebpf_proc.start()
            logging.warning("Wait for eBPF program to be fully loaded")
            while not is_ebpf_loaded():
                time.sleep(1)

            if self.rosbag_fullpath and os.path.exists(self.rosbag_fullpath):
                if os.uname().machine == "aarch64":
                    rate = self._bag_play_rate_arm
                else:
                    rate = self._bag_play_rate_x86
                cmd_str = f"ros2 bag play -r {rate} {shlex.quote(self.rosbag_fullpath)}"

                fd, script_path = tempfile.mkstemp(prefix="rosbag_play_", suffix=".exp", dir=os.getcwd())
                os.close(fd)
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(f"""#!/usr/bin/expect -f
spawn sh -c "{cmd_str}"
sleep {self._burn_in_seconds}
send " "
sleep {self._min_pause_seconds}
send " "
sleep 26
expect eof
""")
                os.chmod(script_path, 0o755)

                logging.warning("play rosbag and press space at %.1fs / %.1fs …", self._burn_in_seconds, self._burn_in_seconds + self._min_pause_seconds)
                expect_proc = ProcManager(["expect", script_path], silent=True)
                expect_proc.start()
                expect_proc.wait()
            else:
                logging.warning("No bag to play; sampling for %.1f seconds", self._sample_duration_seconds_without_bag)
                time.sleep(self._sample_duration_seconds_without_bag)

            return 0
        except KeyboardInterrupt:
            logging.warning("[CIE] interrupted by user (Ctrl+C); aborting this round.")
            return -1
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
                    if cie_started:
                        try:
                            if cie_apply_completed:
                                self._cie.finalize_and_cleanup()
                            else:
                                self._cie.abort()
                        except Exception:
                            logging.exception("[CIE] cleanup failed")
                    if ros2_launch_proc is not None:
                        logging.warning("Terminating ros2 process, please wait.")
                        ros2_launch_proc.stop()

    def _apply_cie_until_ok(self, ros2_launch_proc):
        """
        Keep retrying (restart BOTH CIE and Autoware) until:
          - CIE.wait_and_apply() succeeds (conditions met), or
          - user hits Ctrl+C to stop.
        Returns the (possibly restarted) ros2_launch_proc to continue the normal flow.
        Raises KeyboardInterrupt if user cancels.
        """
        while True:
            if self._cie.wait_and_apply():
                return ros2_launch_proc

            logging.warning("[CIE] not ready (unapplied not stabilized/prompt missing) → restarting CIE + Autoware, then retry")
            # Restart BOTH
            ros2_launch_proc.stop()
            self._cie.abort()
            time.sleep(2)

            # Start CIE again
            if not self._cie.start():
                continue

            # Start AW again
            ros2_launch_proc = ProcManager(self._ros2_launch_cmd,
                                           log_filename=self._ros2_terminal_logfile,
                                           ld_preload=self._ld_preload)
            ros2_launch_proc.start()

            # Wait AW ready again; if failed, loop will retry
            ret = self._wait_ros2_proc_ready_func(self._ros2_terminal_logfile)
            if ret != 0:
                logging.warning("[CIE] Autoware failed to become ready after restart; retrying...")
                continue

    def sample_many_times(self, num_sampling: int, cool_down_seconds=60):
        for idx in range(num_sampling):
            logging.warning("start sampling: %d/%d", idx + 1, num_sampling)
            self.sample_once()
            logging.warning("end sampling: %d/%d", idx + 1, num_sampling)
            if cool_down_seconds > 0:
                logging.info("Cool down for %.3f seconds to avoid overheat", cool_down_seconds)
                time.sleep(cool_down_seconds)

    def __str__(self):
        return (f"SamplingManager(ros2_launch_cmd={self.ros2_launch_cmd}, "
                f"logfile={self._ros2_terminal_logfile}, "
                f"rosbag={self._rosbag_fullpath})")

