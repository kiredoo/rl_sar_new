"""
Trace multiple callback functions and write tracing data that can be displayed
by chrome:://tracing or perfecto.

Usage:
    sudo python3 trace_et.py -i demangled_cb_names.txt

To see the tracing result, open chromimum browser and
use the URL chrome://tracing, then load trace.json.
Another way to see the tracing result is to visit
https://ui.perfetto.dev/ and load trace.json.
"""
import argparse
import io
import json
import logging
from dataclasses import asdict

from measure_ets_utils import create_bpf, locate_callbacks_by_txt

_EBPF_C_TEMPLATE = "ebpf_trace_ets_template.c"
_EBPF_C_RENDERED = ".ebpf_trace_ets.c"
_FUNC_LOC_CACHE_FILENAME = ".trace_ets_cache.json"


def _insert_probes(cb_locs_list, bpf):
    for loc in cb_locs_list:
        logging.warning("Attach uprobes for %s, mangled_name: %s, elf: %s",
                        loc.demangled_name, loc.mangled_name, loc.fullpath)
        bpf.attach_uprobe(name=loc.fullpath,
                          sym=loc.mangled_name,
                          fn_name=f"cb_in_{loc.mangled_name}")
        bpf.attach_uretprobe(name=loc.fullpath,
                             sym=loc.mangled_name,
                             fn_name=f"cb_out_{loc.mangled_name}")


def _trace_ets(callback_names_txt, output_fn, elf_path_must_contain, ignore_cache):
    cb_locs_dict = locate_callbacks_by_txt(callback_names_txt,
                                           elf_path_must_contain,
                                           ignore_cache,
                                           cached_json_file=_FUNC_LOC_CACHE_FILENAME)
    cb_locs_list = [val for _, val in cb_locs_dict.items()]
    bpf = create_bpf(cb_locs_list, template_fn=_EBPF_C_TEMPLATE, ebpf_c_fn=_EBPF_C_RENDERED)
    _insert_probes(cb_locs_list, bpf)

    with io.open(_FUNC_LOC_CACHE_FILENAME, "w", encoding="utf-8") as _fp:
        jdata = {key: asdict(obj) for key, obj in cb_locs_dict.items()}
        _fp.write(json.dumps(jdata, sort_keys=True))

    with io.open(output_fn, "w", encoding="utf-8") as _fp:
        print(f"Write trace entries to {output_fn}, Ctrl+C to stop")
        _fp.write("{\n")
        _fp.write('"traceEvents": [\n')
        has_entry = False
        def _write_trace_entry(_cpu, data, _size):
            nonlocal has_entry
            obj = bpf["g_trace_event_rbo"].event(data)
            if obj.cb_index >= 0 and obj.cb_index < len(cb_locs_list):
                demangled_name = cb_locs_list[obj.cb_index].demangled_name
            else:
                demangled_name = "unknown"

            entry = {}
            entry["ph"] = "X"
            entry["cpu"] = obj.cpu
            entry["pid"] = obj.tgid
            entry["tid"] = obj.pid
            entry["ts"] = obj.ts_in_ns / 1000.0
            entry["dur"] = obj.dur_in_ns / 1000.0
            if obj.is_cb_event:
                entry["cat"] = "callback"
                entry["name"] = demangled_name
            else:
                entry["cat"] = "sched"
                entry["name"] = "sched_switch"

            if has_entry:
                _fp.write(",\n")
            else:
                has_entry = True
            _fp.write(json.dumps(entry))

        bpf["g_trace_event_rbo"].open_ring_buffer(_write_trace_entry)

        done = False
        while not done:
            try:
                bpf.ring_buffer_poll()
            except KeyboardInterrupt:
                done = True
        _fp.write("]\n")
        _fp.write("}\n")

def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--callback-names-txt", "-i", default="/tmp/callbacks.txt",
                        help="txt file containing demangled function names")
    parser.add_argument("--output", "-o", default="/tmp/trace.json",
                        help="trace file")
    parser.add_argument("--elf-path-must-contain", default="autoware",
                        help=("Only readelf the files matching the path, "
                              "empty string means match all paths"))
    parser.add_argument("--ignore-cache", action="store_true",
                        help="Force to scan opened ELF files and insert uprobe")
    args = parser.parse_args()

    _trace_ets(args.callback_names_txt, args.output, args.elf_path_must_contain, args.ignore_cache)


if __name__ == "__main__":
    main()
