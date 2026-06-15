"""
Control the life cycle of a process.
"""
import io
import logging
import os
import shlex
import signal
import subprocess
import sys

import psutil


def _check_call(cmd):
    """
    Invoke a shell command; Suitable for light-weight commands.
    """
    logging.warning("Run %s", cmd)
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError:
        logging.warning("Cannot run %s", cmd)


def _signal_pid(pid, sig):
    try:
        this_proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return

    try:
        uids = this_proc.uids()
        is_root = uids.effective == 0
    except (psutil.AccessDenied, AttributeError):
        is_root = False

    sig_name = sig.name.replace("SIG", "")
    if is_root:
        cmd = ["sudo", "kill", f"-{sig_name}", str(pid)]
        logging.warning("Run %s", cmd)
        _check_call(cmd)
        return

    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        return


def _kill_proc_by_pid(pid):
    _signal_pid(pid, signal.SIGKILL)


class ProcManager:
    """
    Managing the life cycle of a long-running process
    """

    def __init__(self, cmd, silent=False, log_filename=None, ld_preload=None):
        if isinstance(cmd, str):
            self._cmd = shlex.split(cmd)
        else:
            self._cmd = list(cmd)
        self._proc = None
        self._pgid = None
        self._ld_preload = ld_preload
        self._silent = silent
        self._log_filename = log_filename
        self._log_fp = None
        if log_filename:
            self._log_fp = io.open(log_filename, "w", encoding="utf-8")

    @property
    def pid(self):
        if self._proc is None:
            return None
        return self._proc.pid

    def poll(self):
        if self._proc is None:
            return None
        return self._proc.poll()

    def wait(self, timeout=None):
        if self._proc is None:
            return None
        return self._proc.wait(timeout=timeout)

    def is_alive(self):
        return self._proc is not None and self._proc.poll() is None

    def _open_log_if_needed(self):
        if self._log_filename and self._log_fp is None:
            self._log_fp = io.open(self._log_filename, "w", encoding="utf-8")

    def _cleanup(self):
        if self._log_fp is not None:
            try:
                self._log_fp.close()
            except Exception:
                pass
            self._log_fp = None
        self._proc = None
        self._pgid = None

    def _collect_child_pids(self):
        if self._proc is None:
            return []
        try:
            return [child.pid for child in psutil.Process(self._proc.pid).children(recursive=True)]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return []

    def _restore_tty_if_needed(self):
        if os.environ.get("WCET_RESTORE_TTY") != "1":
            return
        if not self._cmd or self._cmd[0] != "sudo":
            return
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return
        _check_call(["stty", "sane"])

    def _signal_group(self, sig):
        if self._pgid is None:
            return

        sig_name = sig.name.replace("SIG", "")
        is_root_group = False
        if self._proc is not None:
            try:
                is_root_group = psutil.Process(self._proc.pid).uids().effective == 0
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                is_root_group = False

        if is_root_group:
            _check_call(["sudo", "kill", f"-{sig_name}", "--", f"-{self._pgid}"])
            return

        try:
            os.killpg(self._pgid, sig)
        except ProcessLookupError:
            return
        except PermissionError:
            _check_call(["sudo", "kill", f"-{sig_name}", "--", f"-{self._pgid}"])

    def start(self):
        if self.is_alive():
            raise RuntimeError(f"Process already started: {self._cmd}")

        if self._proc is not None and self._proc.poll() is not None:
            self._cleanup()

        if self._ld_preload:
            env = os.environ.copy()
            env["LD_PRELOAD"] = self._ld_preload
            logging.warning("env LD_PRELOAD=%s", self._ld_preload)
        else:
            env = None

        self._open_log_if_needed()

        if self._silent:
            self._proc = subprocess.Popen(
                self._cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
        else:
            self._proc = subprocess.Popen(
                self._cmd,
                stdout=self._log_fp,
                stderr=self._log_fp,
                env=env,
                start_new_session=True,
            )
        self._pgid = self._proc.pid

    def make_proc_rt(self):
        """
        context switch can affect sampling, use the RT-scheduler
        SCHED_FIFO to avoid this.
        """
        if not self.is_alive():
            return
        pids = [self._proc.pid]
        pids += self._collect_child_pids()

        for pid in pids:
            cmd = shlex.split(f"sudo chrt --all-tasks --fifo -p 98 {pid}")
            _check_call(cmd)

    def is_root_process(self):
        if self._proc is None:
            return False
        try:
            uids = psutil.Process(self._proc.pid).uids()
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
            return False
        return uids.effective == 0

    def stop(self, timeout=10):
        logging.info("Stop the process %s", self._cmd)

        if self._proc is None:
            self._cleanup()
            self._restore_tty_if_needed()
            return

        child_pids = self._collect_child_pids()
        snapshot_pids = [self._proc.pid] + child_pids

        try:
            if self._proc.poll() is None:
                logging.info("This process pid: %d, Child PIDs: %s", self._proc.pid, child_pids)
                self._signal_group(signal.SIGTERM)
                try:
                    self._proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    logging.warning("Force to kill process group pgid=%s", self._pgid)
                    self._signal_group(signal.SIGKILL)
                    try:
                        self._proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        logging.warning("Process leader %d did not exit after group SIGKILL", self._proc.pid)
                        _kill_proc_by_pid(self._proc.pid)
            else:
                logging.info("Process has already finished")
        finally:
            for pid in snapshot_pids[1:]:
                try:
                    psutil.Process(pid)
                except psutil.NoSuchProcess:
                    continue
                logging.info("Try to kill leftover child process %d", pid)
                _kill_proc_by_pid(pid)
            self._cleanup()
            self._restore_tty_if_needed()

    def __str__(self):
        return f"ProcManager: cmd={self._cmd}"
