"""
Count memory allocation made by malloc. The count only applies to ROS2 processes.

Example output:
size,count
0,0
1,62
...
1024,107
>=1025,2054
"""
import argparse
import io
import logging
import os
import time

from bcc import BPF
from jinja2 import Template

_EBPF_C = "ebpf_count_malloc_size_template.c"
_EBPF_C_RENDERED = "/tmp/ebpf_count_malloc_size.c"


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


def _create_bpf():
    cur_dir = os.path.dirname(os.path.realpath(__file__))
    template_file = os.path.join(cur_dir, _EBPF_C)
    with io.open(template_file, encoding="utf-8") as _fp:
        template = Template(_fp.read())
    ros2_pids = _find_ros2_pids()
    bpf_code = template.render(ros2_pids=ros2_pids)

    bpf_filename = _EBPF_C_RENDERED
    logging.warning("Write %s", bpf_filename)
    with io.open(bpf_filename, "w", encoding="utf-8") as _fp:
        _fp.write(bpf_code)
    return BPF(src_file=bpf_filename)


def _insert_probes(bpf):
    bpf.attach_uprobe(name="/usr/lib/x86_64-linux-gnu/libc.so.6", sym="malloc", fn_name="malloc_in")


def _count_malloc_size():
    bpf = _create_bpf()
    _insert_probes(bpf)

    done = False
    while not done:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            done = True

    g_malloc_size_count = bpf["g_malloc_size_count"]
    print("")
    with io.open("out.csv", "w", encoding="utf-8") as _fp:
        line = "size,count"
        print(line)
        _fp.write(line + "\n")

        num_size = len(g_malloc_size_count)
        for index in range(num_size - 1):
            item = g_malloc_size_count[index]
            line = f"{index},{item.count}"
            print(line)
            _fp.write(line + "\n")
        index = num_size - 1
        count = g_malloc_size_count[index].count
        line = f">={index},{count}"
        print(line)
        _fp.write(line + "\n")

    print(f"Write to out.csv")

def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    args = parser.parse_args()

    _count_malloc_size()


if __name__ == "__main__":
    main()
