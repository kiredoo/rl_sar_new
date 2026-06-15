"""
Find total major/minor page faults based on /proc/pid, where pid is a ROS2 process.
"""
import io
import os
from dataclasses import dataclass


@dataclass
class PageFaultAccounting():
    cmdline: str = ""
    minor: int = 0
    major: int = 0
    pid: int = 0


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


def get_major_minor_page_fault(pid):
    res = PageFaultAccounting(pid=pid)
    with io.open(f"/proc/{pid}/stat", "r") as _fp:
        stats = _fp.read().split()

        res.minor = int(stats[9])
        res.major = int(stats[11])
    with io.open(f"/proc/{pid}/cmdline", "rb") as _fp:
        raw = _fp.read()
        args = raw.split(b'\0')
        args = [arg.decode('utf-8') for arg in args if arg]
        res.cmdline = " ".join(args)
    return res


def main():
    total_minor = 0
    total_major = 0
    for pid in _find_ros2_pids():
        ret = get_major_minor_page_fault(pid)
        total_minor += ret.minor
        total_major += ret.major
    print(f"Total major faults: {total_major}, total minor faults: {total_minor}")

if __name__ == "__main__":
    main()
