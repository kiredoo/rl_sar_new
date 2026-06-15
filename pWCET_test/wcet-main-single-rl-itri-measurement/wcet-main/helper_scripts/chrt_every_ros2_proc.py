"""
Make every ROS2 process to apply the FIFO scheduling policy.

You need root permission to make this script work.

Make sure if a process uses FIFO:
    cat /proc/{pid}/sched
and look for the policy line:
policy : 1

Value   Policy
0       SCHED_NORMAL
1       SCHED_FIFO
2       SCHED_RR
3       SCHED_BATCH
5       SCHED_IDLE
6       SCHED_DEADLINE

Or using command line:
$ sudo chrt -p 3252221
pid 3252221's current scheduling policy: SCHED_FIFO
pid 3252221's current scheduling priority: 98
"""
import io
import logging
import os
import shlex
import subprocess


def _is_ros2_pid(pid):
    maps_fn = f"/proc/{pid}/maps"
    if not os.path.isfile(maps_fn):
        return False
    try:
        with io.open(maps_fn, encoding="utf-8") as _fp:
            lines = _fp.read().splitlines()
    except PermissionError:
        return False

    for line in lines:
        if "librclcpp.so" in line:
            return True
    return False


def _find_ros2_pids():
    pids = set()
    for pid in os.listdir("/proc"):
        dirname = os.path.join("/proc", pid)
        if not os.path.isdir(dirname):
            continue
        if _is_ros2_pid(pid):
            pids.add(int(pid))
    return pids


def _check_call(cmd):
    """
    Invoke a shell command; Suitable for light-weight commands.
    """
    logging.warning("Run %s", cmd)
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError:
        logging.warning("Cannot run %s", cmd)

def apply_fifo_to_pid(pid):
    # Use chrt to apply FIFO to the process and its threads
    cmd = shlex.split(f"sudo chrt --all-tasks --fifo -p 98 {pid}")
    _check_call(cmd)


def main():
    for pid in _find_ros2_pids():
        apply_fifo_to_pid(pid)


if __name__ == "__main__":
    main()
