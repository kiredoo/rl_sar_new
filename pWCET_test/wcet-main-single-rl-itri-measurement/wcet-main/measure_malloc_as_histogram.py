"""
Measure the malloc pattern of a callback function. Typically a callback
function is evoked periodically and thus has a fixed memory allocation
pattern. Investigating the pattern can help design an efficient memory
allocator.
"""
import argparse
import io
import json
import logging
import os
from dataclasses import asdict

from bcc import BPF

from elf_utils import FuncLocation, locate_callbacks

_EBPF_C = "ebpf_malloc_as_histogram.c"
_FUNC_LOC_CACHE_FILENAME = ".measure_malloc_as_histogram.json"

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
    bpf.attach_uprobe(name="/usr/lib/x86_64-linux-gnu/libc.so.6", sym="malloc", fn_name="malloc_in")


def _measure_malloc_pattern(demangled_name, elf_path_must_contain):
    loc = _locate_func(demangled_name, elf_path_must_contain)

    bpf = _create_bpf()
    _insert_probes(bpf, loc)

    def _print_histogram(_cpu, data, _size):
        obj = bpf["g_histogram_rbo"].event(data)
        print("-" * 40)
        print(f"Allocate {obj.total_allocated_bytes:,} bytes")
        for bit_len in range(65):
            count = obj.bit_len_count[bit_len]
            if count > 0:
                print(f"[2^{bit_len-1}, 2^{bit_len}):  {count}")

    bpf["g_histogram_rbo"].open_ring_buffer(_print_histogram)
    done = False
    while not done:
        try:
            bpf.ring_buffer_poll()
        except KeyboardInterrupt:
            done = True

def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--demangled-name-input", "-i", required=True,
                        help="demangled function name")

    parser.add_argument("--elf-path-must-contain", default="",
                        help="Only look for symbols with the path constraint")
    args = parser.parse_args()

    _measure_malloc_pattern(args.demangled_name_input, args.elf_path_must_contain)


if __name__ == "__main__":
    main()
