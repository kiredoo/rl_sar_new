"""
Collect system information.
"""
import io
import os
import platform
import psutil
import subprocess
import socket
from dataclasses import dataclass, asdict

@dataclass
class SystemInfo:
    cpu_count: int
    hostname: str
    machine_type: str
    min_cpu_freq_mhz: float
    max_cpu_freq_mhz: float
    l1_cache_size: str
    l2_cache_size: str
    l3_cache_size: str
    ram_size_gb: float


def _read_file_content(path):
    if not os.path.isfile(path):
        return ""

    with io.open(path, encoding="utf-8") as _fp:
        return _fp.read().strip()


def _get_cache_size(level: int):
    if level == 1:
        res = ""
        for index in [0, 1]:
            size_str = _read_file_content(f"/sys/devices/system/cpu/cpu0/cache/index{index}/size")
            type_str = _read_file_content(f"/sys/devices/system/cpu/cpu0/cache/index{index}/type")
            res += f"{size_str} {type_str} "
        if res[-1] == " ":
            res = res[:-1]
        return res
    else:
        return _read_file_content(f"/sys/devices/system/cpu/cpu0/cache/index{level}/size")

    return "N/A"


def collect_system_info() -> SystemInfo:
    hostname = socket.gethostname()
    machine_type = platform.machine()
    ram_size_gb = round(psutil.virtual_memory().total / (1024 ** 3), 2)
    cpu_count = psutil.cpu_count(logical=True)
    cpu_freq = psutil.cpu_freq()

    return SystemInfo(
        cpu_count=cpu_count,
        hostname=hostname,
        machine_type=machine_type,
        max_cpu_freq_mhz=cpu_freq.max,
        min_cpu_freq_mhz=cpu_freq.min,
        l1_cache_size=_get_cache_size(1),
        l2_cache_size=_get_cache_size(2),
        l3_cache_size=_get_cache_size(3),
        ram_size_gb=ram_size_gb,
    )
