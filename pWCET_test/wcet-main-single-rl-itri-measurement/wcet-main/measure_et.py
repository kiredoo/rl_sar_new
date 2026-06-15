"""
Minimum example of finding the execution time of a callback function
Usage:
    sudo python3 measure_et.py -i NDTScanMatcher::callback_sensor_points
where NDTScanMatcher::callback_sensor_points is the callback function we want to inspect.
"""
import argparse
import io
import json
import logging
import os
import signal
import statistics
import time
from dataclasses import asdict

from bcc import BPF

from elf_utils import locate_callbacks, FuncLocation
from callback_execution_time import CallbackExecutionTime
from sig_utils import got_sigint, sigint_handler

_EBPF_C = "ebpf_et.c"
_FUNC_LOC_CACHE_FILENAME = ".measure_et_cache.json"
_MAX_NUM_SAMPLES = 3000  # match MAX_NUM_SAMPLES in eBPF


def _locate_func(demangled_name):
    """
    Return a FuncLocation object
    """
    if os.path.isfile(_FUNC_LOC_CACHE_FILENAME):
        with io.open(_FUNC_LOC_CACHE_FILENAME, encoding="utf-8") as _fp:
            jdata = json.loads(_fp.read())
            loc = FuncLocation(**jdata)
        if loc.demangled_name == demangled_name:
            # cache hit
            return loc
    logging.warning("Inspect execution time for %s", demangled_name)
    func_locs = locate_callbacks([demangled_name])
    loc = func_locs[demangled_name]
    with io.open(_FUNC_LOC_CACHE_FILENAME, "w", encoding="utf-8") as _fp:
        _fp.write(json.dumps(asdict(loc), sort_keys=True))
    return loc

def _create_bpf():
    cur_dir = os.path.dirname(os.path.realpath(__file__))
    src_file = os.path.join(cur_dir, _EBPF_C)
    return BPF(src_file=src_file)

def _insert_probes(loc, bpf):
    logging.warning("Attach uprobes for %s, mangled_name: %s, elf: %s",
                    loc.demangled_name, loc.mangled_name, loc.fullpath)
    bpf.attach_uprobe(name=loc.fullpath, sym=loc.mangled_name, fn_name="cb_in")
    bpf.attach_uretprobe(name=loc.fullpath, sym=loc.mangled_name, fn_name="cb_out")

    machine = os.uname().machine
    if machine == "aarch64":
        bpf.attach_kprobe(event="invoke_syscall", fn_name="syscall_in")
        bpf.attach_kretprobe(event="invoke_syscall", fn_name="syscall_out")
    elif machine == "x86_64":
        bpf.attach_kprobe(event="__x64_sys_open", fn_name="syscall_in")
        bpf.attach_kretprobe(event="__x64_sys_open", fn_name="syscall_out")
    else:
        logging.error("Unknown machine type: %s", machine)


def _still_sampling(bpf):
    g_num_samples = bpf["g_num_samples"]
    return g_num_samples.get(0).value < _MAX_NUM_SAMPLES

def _post_process(loc, bpf):
    g_num_samples = bpf["g_num_samples"]
    print(f"Collect {g_num_samples.get(0).value} samples")

    response_times_ns = bpf["g_response_times_ns"]
    acc_syscall_times_ns = bpf["g_acc_syscall_times_ns"]
    cb_et = CallbackExecutionTime(name=loc.demangled_name)
    for idx, resp_time_ns in response_times_ns.items():
        resp_time_ns = resp_time_ns.value
        if resp_time_ns > 0:
            syscall_time_ns = acc_syscall_times_ns.get(idx).value
            print(f"resp_time_ns: {resp_time_ns}, syscall_time_ns: {syscall_time_ns}")
            cb_et.samples.append(resp_time_ns - syscall_time_ns)
    if len(cb_et.samples) > 2:
        mean = statistics.mean(cb_et.samples)
        stdev = statistics.stdev(cb_et.samples)
        print(f"{loc.demangled_name} -- min: {min(cb_et.samples):,} ns, max: {max(cb_et.samples):,} ns, "
              f"avg: {mean:,.0f} ns, stdev: {stdev:,.0f}")
    else:
        print("No sampling data")

def _find_execution_time(demangled_name):
    signal.signal(signal.SIGINT, sigint_handler)

    loc = _locate_func(demangled_name)
    bpf = _create_bpf()
    _insert_probes(loc, bpf)

    print(f"Collection process stops when hitting Ctrl+C or |samples| == {_MAX_NUM_SAMPLES}")
    while (not got_sigint()) and _still_sampling(bpf):
        time.sleep(1)

    _post_process(loc, bpf)


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--demangled-name-input", "-i", required=True,
                        help="demangled function name")
    args = parser.parse_args()

    _find_execution_time(args.demangled_name_input)


if __name__ == "__main__":
    main()
