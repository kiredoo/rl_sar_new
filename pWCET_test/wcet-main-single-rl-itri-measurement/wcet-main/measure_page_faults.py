"""
Measure page faults for multiple callbacks
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

_EBPF_C = "ebpf_page_faults_template.c"
_EBPF_C_RENDERED = ".ebpf_page_faults.c"
_MAX_NUM_SAMPLES = 100
_FUNC_LOC_CACHE_FILENAME = ".measure_page_faults_cache.json"


def _create_bpf(cb_locs):
    cur_dir = os.path.dirname(os.path.realpath(__file__))
    template_file = os.path.join(cur_dir, _EBPF_C)
    with io.open(template_file, encoding="utf-8") as _fp:
        template = Template(_fp.read())
    bpf_code = template.render(cb_locs=cb_locs, num_cb=len(cb_locs))

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

    bpf.attach_kprobe(event="handle_mm_fault", fn_name="handle_mm_fault_in")
    bpf.attach_kretprobe(event="handle_mm_fault", fn_name="handle_mm_fault_out")


def _postprocess(bpf, cb_locs):
    mm_faults_table = bpf["g_mm_faults_table"]
    csv_header = "name,major,minor,handle_mm_fault_time_ns,samples\n"
    csv_lines = []
    for demangled_name, cb_loc in cb_locs.items():
        cb_index = cb_loc.index
        entry = mm_faults_table.get(cb_index)
        num_major_faults = entry.num_major_faults
        num_minor_faults = entry.num_minor_faults
        num_cb_called = entry.num_cb_called
        handle_mm_fault_time_ns = entry.handle_mm_fault_time_ns
        print((f"{demangled_name} -- "
               f"major faults: {num_major_faults}, "
               f"minor faults {num_minor_faults}, "
               f"handle_mm_fault_time_ns: {handle_mm_fault_time_ns:,} ns, "
               f"#samples: {num_cb_called}"))
        csv_line = (f"{demangled_name},{num_major_faults},{num_minor_faults},"
                    f"{handle_mm_fault_time_ns},{num_cb_called}\n")
        csv_lines.append(csv_line)
    output_fn = "page_faults.csv"
    print(f"Write {output_fn}")
    with io.open(output_fn, "w", encoding="utf-8") as _fp:
        _fp.write(csv_header)
        for line in csv_lines:
            _fp.write(line)

def _measure_page_faults(demangled_name_txt, elf_path_must_contain, ignore_cache, sampling_seconds):
    cb_locs = locate_callbacks_by_txt(demangled_name_txt,
                                      elf_path_must_contain,
                                      ignore_cache,
                                      cached_json_file=_FUNC_LOC_CACHE_FILENAME)
    bpf = _create_bpf(cb_locs)
    _insert_probes(bpf, cb_locs)

    print(f"Take {sampling_seconds:.3f} seconds to collect data")
    time.sleep(sampling_seconds)
    _postprocess(bpf, cb_locs)
    with io.open(_FUNC_LOC_CACHE_FILENAME, "w", encoding="utf-8") as _fp:
        jdata = {key: asdict(obj) for key, obj in cb_locs.items()}
        _fp.write(json.dumps(jdata, sort_keys=True))


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--demangled-name-txt", "-i", default="callbacks.txt",
                        help="txt file containing demangled function names")
    parser.add_argument("--elf-path-must-contain", default="autoware",
                        help="Only look for symbols with the path constraint")
    parser.add_argument("--ignore-cache", action="store_true",
                        help="Force to scan opened ELF files and insert uprobe")
    parser.add_argument("--sampling-seconds", type=float, default=10,
                        help="Number of seconds to probe callback functions.")
    args = parser.parse_args()

    _measure_page_faults(args.demangled_name_txt,
                         args.elf_path_must_contain,
                         args.ignore_cache,
                         args.sampling_seconds)


if __name__ == "__main__":
    main()
