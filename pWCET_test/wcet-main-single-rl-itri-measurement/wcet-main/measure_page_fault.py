import argparse
import io
import json
import logging
import os
import time
from dataclasses import asdict

from bcc import BPF

from elf_utils import FuncLocation, locate_callbacks
from sig_utils import got_sigint

_EBPF_C = "ebpf_page_fault.c"
_MAX_NUM_SAMPLES = 100
_FUNC_LOC_CACHE_FILENAME = ".measure_page_fault_cache.json"

def _locate_func(demangled_name, elf_path_must_contain):
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
    func_locs = locate_callbacks([demangled_name], elf_path_must_contain=elf_path_must_contain)
    loc = func_locs[demangled_name]
    with io.open(_FUNC_LOC_CACHE_FILENAME, "w", encoding="utf-8") as _fp:
        _fp.write(json.dumps(asdict(loc), sort_keys=True))
    return loc


def _create_bpf():
    cur_dir = os.path.dirname(os.path.realpath(__file__))
    src_file = os.path.join(cur_dir, _EBPF_C)
    return BPF(src_file=src_file)


def _insert_probes(bpf, loc):
    bpf.attach_uprobe(name=loc.fullpath, sym=loc.mangled_name, fn_name="cb_in")
    bpf.attach_uretprobe(name=loc.fullpath, sym=loc.mangled_name, fn_name="cb_out")
    bpf.attach_kprobe(event="handle_mm_fault", fn_name="handle_mm_fault_in")
    bpf.attach_kretprobe(event="handle_mm_fault", fn_name="handle_mm_fault_out")


def _measure_page_faults(demangled_name, elf_path_must_contain, sampling_seconds):
    loc = _locate_func(demangled_name, elf_path_must_contain)

    bpf = _create_bpf()
    _insert_probes(bpf, loc)
    print(f"Take {sampling_seconds:.3f} seconds to collect data")
    time.sleep(sampling_seconds)

    fault_data = bpf["g_mm_faults_table"].get(0)
    if fault_data.num_cb_called > 0:
        avg_minor_faults = fault_data.num_minor_faults // fault_data.num_cb_called
        avg_major_faults = fault_data.num_major_faults // fault_data.num_cb_called
        avg_handle_mm_fault_time_ns = fault_data.handle_mm_fault_time_ns // fault_data.num_cb_called
    else:
        avg_minor_faults = 0
        avg_major_faults = 0
        avg_handle_mm_fault_time_ns = 0

    print((f"minor faults: {fault_data.num_minor_faults} (avg: {avg_minor_faults}), "
           f"major faults: {fault_data.num_major_faults} (avg: {avg_major_faults}), "
           f"handle_mm_fault time: {fault_data.handle_mm_fault_time_ns:,} ns "
           f"(avg: {avg_handle_mm_fault_time_ns:,} ns), "
           f"#samples: {fault_data.num_cb_called}"))

def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--demangled-name-input", "-i", required=True,
                        help="demangled function name")
    parser.add_argument("--elf-path-must-contain", default="",
                        help="Only look for symbols with the path constraint")

    parser.add_argument("--sampling-seconds", type=float, default=10,
                        help="Number of seconds to probe callback functions.")
    args = parser.parse_args()

    _measure_page_faults(args.demangled_name_input, args.elf_path_must_contain, args.sampling_seconds)


if __name__ == "__main__":
    main()
