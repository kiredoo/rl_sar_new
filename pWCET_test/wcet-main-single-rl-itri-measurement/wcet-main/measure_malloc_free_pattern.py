"""
Display malloc and free pattern of a callback function.
The actual behavior of memory allocation can be used for the design/testing of allocators.

Example output:
malloc,88,0x55935688fb60            #malloc,size,allocated_address
malloc,8386608,0x559357fb8430
free,0x559357fb8430
free,0x55935688fb60
...
"""
import argparse
import io
import json
import logging
import os
from dataclasses import asdict

from bcc import BPF

from elf_utils import FuncLocation, locate_callbacks

_EBPF_C = "ebpf_malloc_free_pattern.c"
_ADDR_DICT = {}

def _locate_func(demangled_name, elf_path_must_contain):
    """
    Return a FuncLocation object
    """
    func_locs = locate_callbacks([demangled_name], elf_path_must_contain=elf_path_must_contain)
    return func_locs.get(demangled_name, None)


def _create_bpf():
    cur_dir = os.path.dirname(os.path.realpath(__file__))
    src_file = os.path.join(cur_dir, _EBPF_C)
    return BPF(src_file=src_file)


def _insert_probes(bpf, loc):
    bpf.attach_uprobe(name=loc.fullpath, sym=loc.mangled_name, fn_name="cb_in")
    bpf.attach_uretprobe(name=loc.fullpath, sym=loc.mangled_name, fn_name="cb_out")

    bpf.attach_uprobe(name="/usr/lib/x86_64-linux-gnu/libc.so.6", sym="malloc", fn_name="malloc_in")
    bpf.attach_uretprobe(name="/usr/lib/x86_64-linux-gnu/libc.so.6", sym="malloc", fn_name="malloc_out")

    bpf.attach_uprobe(name="/usr/lib/x86_64-linux-gnu/libc.so.6", sym="free", fn_name="free_in")

def _measure_malloc_free_pattern(demangled_name, elf_path_must_contain):
    loc = _locate_func(demangled_name, elf_path_must_contain)
    if loc is None:
        logging.error("Cannot find %s", demangled_name)
        return
    print(loc)

    bpf = _create_bpf()
    _insert_probes(bpf, loc)

    def _print_call(_cpu, data, _size):
        global _ADDR_DICT
        obj = bpf["g_call_rbo"].event(data)
        if obj.pid_tgid == 0:
            return
        if obj.is_malloc:
            print(f"malloc,{obj.arg},0x{obj.ret:x}")
            _ADDR_DICT[obj.ret] = obj.arg
        else:
            if obj.arg == 0:
                print(f"free,0x0")
                return
            if obj.arg not in _ADDR_DICT:
                return
            print(f"free,0x{obj.arg:x}")
            _ADDR_DICT.pop(obj.arg)

    bpf["g_call_rbo"].open_ring_buffer(_print_call)
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

    _measure_malloc_free_pattern(args.demangled_name_input, args.elf_path_must_contain)


if __name__ == "__main__":
    main()
