"""
Trace a single callback function and write tracing data
that can be displayed by chrome:://tracing or perfetto.

Usage:
    sudo python3 trace_et.py -i NDTScanMatcher::callback_sensor_points
where NDTScanMatcher::callback_sensor_points is the callback function we want to trace.

To see the tracing result, either
- Open chromimum browser and use the URL chrome://tracing, then load trace.json, or
- Visit https://ui.perfetto.dev/ and load trace.json.

The trace file format can be found in
  https://docs.google.com/document/d/1CvAClvFfyA5R-PhYUmn5OOQtYMH4h6I0nSsKchNAySU/preview?pli=1&tab=t.0
"""
import argparse
import io
import json
import logging
import os
from dataclasses import asdict

from bcc import BPF

from elf_utils import FuncLocation, locate_callbacks

_EBPF_C = "ebpf_trace_et.c"
_FUNC_LOC_CACHE_FILENAME = ".trace_et_cache.json"


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

def _insert_probes(loc, bpf):
    logging.warning("Attach uprobes for %s, mangled_name: %s, elf: %s",
                    loc.demangled_name, loc.mangled_name, loc.fullpath)
    bpf.attach_uprobe(name=loc.fullpath, sym=loc.mangled_name, fn_name="cb_in")
    bpf.attach_uretprobe(name=loc.fullpath, sym=loc.mangled_name, fn_name="cb_out")


def _trace_et(demangled_name, output_fn, elf_path_must_contain):
    loc = _locate_func(demangled_name, elf_path_must_contain)
    bpf = _create_bpf()
    _insert_probes(loc, bpf)

    with io.open(output_fn, "w", encoding="utf-8") as _fp:
        print(f"Write trace entries to {output_fn}, Ctrl+C to stop")
        _fp.write("{\n")
        # _fp.write('"displayTimeUnit": "ns",\n')
        _fp.write('"traceEvents": [\n')
        has_entry = False
        def _write_trace_entry(_cpu, data, _size):
            nonlocal has_entry
            obj = bpf["g_trace_event_rbo"].event(data)
            entry = {}
            entry["ph"] = "X"
            entry["cat"] = "callback"
            entry["name"] = demangled_name
            entry["cpu"] = obj.cpu
            entry["pid"] = obj.tgid
            entry["tid"] = obj.pid
            entry["ts"] = obj.ts_in_ns / 1000.0
            entry["dur"] = obj.dur_in_ns / 1000.0
            if not obj.is_cb_event:
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
    parser.add_argument("--demangled-name-input", "-i", required=True,
                        help="demangled function name")
    parser.add_argument("--output", "-o", default="/tmp/trace.json",
                        help="trace file")
    parser.add_argument("--elf-path-must-contain", default="autoware",
                        help=("Only readelf the files matching the path, "
                              "empty string means match all paths"))
    args = parser.parse_args()

    _trace_et(args.demangled_name_input, args.output, args.elf_path_must_contain)


if __name__ == "__main__":
    main()
