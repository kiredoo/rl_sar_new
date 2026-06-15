"""
Minimum example of finding the frequency (in HZ) of a callback function
Usage:
    sudo python3 measure_fps.py -i NDTScanMatcher::callback_sensor_points
where NDTScanMatcher::callback_sensor_points is the callback function we want to inspect.
"""
import argparse
import io
import json
import logging
import os
import signal
import time
from dataclasses import asdict

from bcc import BPF

from elf_utils import locate_callbacks, FuncLocation
from sig_utils import got_sigint, sigint_handler

_EBPF_C = "ebpf_hz.c"
_FUNC_LOC_CACHE_FILENAME = ".measure_hz_cache.json"


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

def _post_process(loc, bpf):
    g_num_probings = bpf["g_num_probing"].get(0).value
    g_first_probing_time_ns = bpf["g_first_probing_time_ns"].get(0).value
    g_last_probing_time_ns = bpf["g_last_probing_time_ns"].get(0).value

    duration_sec = (g_last_probing_time_ns - g_first_probing_time_ns) / 1e9
    hz = 0
    if duration_sec != 0:
        hz = (g_num_probings - 1) / duration_sec

    print((f"\n{loc.demangled_name} -- "
           f"#probings: {g_num_probings}, "
           f"first_probing_time_ns: {g_first_probing_time_ns}, "
           f"last_probing_time_ns: {g_last_probing_time_ns}, "
           f"hz: {hz:.2f}"))

def _find_hz(demangled_name):
    signal.signal(signal.SIGINT, sigint_handler)

    loc = _locate_func(demangled_name)
    bpf = _create_bpf()
    _insert_probes(loc, bpf)

    while not got_sigint():
        time.sleep(1)

    _post_process(loc, bpf)


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--demangled-name-input", "-i", required=True,
                        help="demangled function name")
    args = parser.parse_args()

    _find_hz(args.demangled_name_input)


if __name__ == "__main__":
    main()
