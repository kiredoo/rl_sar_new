"""
Measure the malloc pattern of callback functions.
"""
import argparse
import io
import json
import logging
import os
import time
from dataclasses import asdict

from bcc import BPF
from jinja2 import Template

from measure_ets_utils import locate_callbacks_by_txt

_MAX_NUM_MALLOC_CALLS_PER_BUCKET_DICT = {}
_MAX_NUM_MALLOC_CALLS_WINNER_PER_BUCKET_DICT = {}
_EBPF_C = "ebpf_malloc_as_histogram_multi_cb.c"
_EBPF_C_RENDERED = ".ebpf_malloc_patterns.c"
_FUNC_LOC_CACHE_FILENAME = ".measure_malloc_as_histogram_multi_cb.json"
_TOTAL_BIT_LEN_COUNTS_DICT = {}
_NO_PRINT_CB_MALLOC = False


def _create_bpf(cb_locs):
    cur_dir = os.path.dirname(os.path.realpath(__file__))
    template_file = os.path.join(cur_dir, _EBPF_C)
    with io.open(template_file, encoding="utf-8") as _fp:
        template = Template(_fp.read())
    bpf_code = template.render(cb_locs=cb_locs)

    bpf_filename = os.path.join(cur_dir, _EBPF_C_RENDERED)
    logging.warning("Write %s", bpf_filename)
    with io.open(bpf_filename, "w", encoding="utf-8") as _fp:
        _fp.write(bpf_code)
    return BPF(src_file=bpf_filename)


def _insert_probes(bpf, cb_locs):
    for _demangled_name, loc in cb_locs.items():
        bpf.attach_uprobe(name=loc.fullpath, sym=loc.mangled_name,
                          fn_name=f"cb_in_{loc.mangled_name}")
        bpf.attach_uretprobe(name=loc.fullpath, sym=loc.mangled_name,
                             fn_name=f"cb_out_{loc.mangled_name}")
    bpf.attach_uprobe(name="/usr/lib/x86_64-linux-gnu/libc.so.6", sym="malloc", fn_name="malloc_in")


def _measure_malloc_patterns(demangled_name_txt, elf_path_must_contain, ignore_cache):
    cb_locs = locate_callbacks_by_txt(demangled_name_txt,
                                      elf_path_must_contain,
                                      ignore_cache,
                                      cached_json_file=_FUNC_LOC_CACHE_FILENAME)

    bpf = _create_bpf(cb_locs)
    _insert_probes(bpf, cb_locs)

    def _print_histogram(_cpu, data, _size):
        obj = bpf["g_histogram_rbo"].event(data)
        global _TOTAL_BIT_LEN_COUNTS_DICT
        global _MAX_NUM_MALLOC_CALLS_PER_BUCKET_DICT
        global _MAX_NUM_MALLOC_CALLS_WINNER_PER_BUCKET_DICT
        if not _NO_PRINT_CB_MALLOC:
            print("-" * 20 + str(obj.cb_name) + "-" * 20)
            print(f"Allocate {obj.total_allocated_bytes:,} bytes")
        for bit_len in range(65):
            count = obj.bit_len_count[bit_len]
            if count > 0:
                if not _NO_PRINT_CB_MALLOC:
                    print(f"[2^{bit_len-1}, 2^{bit_len}):  {count}")
                _TOTAL_BIT_LEN_COUNTS_DICT[bit_len] = _TOTAL_BIT_LEN_COUNTS_DICT.get(bit_len, 0) + count
                cur_max_malloc_calls = _MAX_NUM_MALLOC_CALLS_PER_BUCKET_DICT.get(bit_len, 0)
                if count > cur_max_malloc_calls:
                    _MAX_NUM_MALLOC_CALLS_PER_BUCKET_DICT[bit_len] = count
                    _MAX_NUM_MALLOC_CALLS_WINNER_PER_BUCKET_DICT[bit_len] = obj.cb_name

    bpf["g_histogram_rbo"].open_ring_buffer(_print_histogram)
    done = False
    sampling_start_time = time.time()
    while not done:
        try:
            bpf.ring_buffer_poll()
        except KeyboardInterrupt:
            done = True
    sampling_duration = time.time() - sampling_start_time

    with io.open(_FUNC_LOC_CACHE_FILENAME, "w", encoding="utf-8") as _fp:
        jdata = {key: asdict(obj) for key, obj in cb_locs.items()}
        _fp.write(json.dumps(jdata, sort_keys=True))
    print("-" * 40)
    print(f"Sampled for {sampling_duration:.3f} seconds")
    print(f"Total number of malloc calls for each size bucket:")
    for bit_len in sorted(_TOTAL_BIT_LEN_COUNTS_DICT):
        count = _TOTAL_BIT_LEN_COUNTS_DICT[bit_len]
        print(f"[2^{bit_len-1}, 2^{bit_len}):  {count}")
    print("-" * 40)
    print(f"Max number of malloc calls for each size bucket")
    for bit_len in sorted(_MAX_NUM_MALLOC_CALLS_PER_BUCKET_DICT):
        count = _MAX_NUM_MALLOC_CALLS_PER_BUCKET_DICT[bit_len]
        winner = _MAX_NUM_MALLOC_CALLS_WINNER_PER_BUCKET_DICT[bit_len]
        print(f"[2^{bit_len-1}, 2^{bit_len}):  {count} - claimed by {winner}")


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--demangled-name-txt", "-i", default="callbacks.txt",
                        help="txt file containing demangled function names")
    parser.add_argument("--elf-path-must-contain", default="",
                        help="Only look for symbols with the path constraint")
    parser.add_argument("--ignore-cache", action="store_true",
                        help="Force to scan opened ELF files and insert uprobe")
    parser.add_argument("--no-print-cb-malloc", action="store_true",
                        help="Do not print malloc info for each invocation of a callback")
    args = parser.parse_args()
    global _NO_PRINT_CB_MALLOC
    _NO_PRINT_CB_MALLOC = args.no_print_cb_malloc

    _measure_malloc_patterns(args.demangled_name_txt, args.elf_path_must_contain,
                             args.ignore_cache)


if __name__ == "__main__":
    main()
