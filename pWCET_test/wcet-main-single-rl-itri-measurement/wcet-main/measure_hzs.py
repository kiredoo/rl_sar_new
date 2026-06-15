# pylint: disable=invalid-name
"""
Finding the HZ of many callback functions.
Usage:
    sudo python3 measure_hzs.py -i callbacks.txt
where callbacks.txt is a text file with each line containing a demangled function name.
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
from jinja2 import Template
from sig_utils import got_sigint, sigint_handler

from measure_ets_utils import locate_callbacks_by_txt

_EBPF_C_TEMPLATE = "ebpf_hzs_template.c"
_EBPF_C_RENDERED = ".ebpf_hzs.c"
_FUNC_LOC_CACHE_FILENAME = ".measure_hzs_cache.json"

def _create_bpf(cb_locs):
    cur_dir = os.path.dirname(os.path.realpath(__file__))
    template_filename = os.path.join(cur_dir, _EBPF_C_TEMPLATE)

    with io.open(template_filename, encoding="utf-8") as _fp:
        template = Template(_fp.read())

    bpf_code = template.render(cb_locs=cb_locs)

    bpf_filename = os.path.join(cur_dir, _EBPF_C_RENDERED)
    logging.warning("Write %s", bpf_filename)
    with io.open(bpf_filename, "w", encoding="utf-8") as _fp:
        _fp.write(bpf_code)

    return BPF(src_file=bpf_filename)

def _post_process(cb_locs, bpf):
    for _demangled_name, cb_loc in cb_locs.items():
        g_num_probings = bpf[f"g_num_probing_{cb_loc.mangled_name}"].get(0).value
        g_first_probing_time_ns = bpf[f"g_first_probing_time_ns_{cb_loc.mangled_name}"].get(0).value
        g_last_probing_time_ns = bpf[f"g_last_probing_time_ns_{cb_loc.mangled_name}"].get(0).value

        duration_sec = (g_last_probing_time_ns - g_first_probing_time_ns) / 1e9
        hz = 0
        if duration_sec != 0:
            hz = (g_num_probings - 1) / duration_sec

        print((f"{cb_loc.demangled_name} -- "
               f"#probings: {g_num_probings}, "
               f"first_probing_time_ns: {g_first_probing_time_ns}, "
               f"last_probing_time_ns: {g_last_probing_time_ns}, "
               f"hz: {hz:.2f}"))


def _measure_hzs(demangled_name_txt, elf_path_must_contain, ignore_cache):
    signal.signal(signal.SIGINT, sigint_handler)
    signal.signal(signal.SIGTERM, sigint_handler)

    cb_locs = locate_callbacks_by_txt(demangled_name_txt,
                                      elf_path_must_contain,
                                      ignore_cache,
                                      cached_json_file=_FUNC_LOC_CACHE_FILENAME)
    bpf = _create_bpf(cb_locs)

    for demangled_name, loc in cb_locs.items():
        logging.warning("Attach uprobes for %s, mangled_name: %s, elf: %s",
                        demangled_name, loc.mangled_name, loc.fullpath)
        bpf.attach_uprobe(name=loc.fullpath,
                          sym=loc.mangled_name,
                          fn_name=f"cb_in_{loc.mangled_name}")


    logging.info("Collection process stops when hitting Ctrl+C or |samples| reaches maximum")

    while not got_sigint():
        time.sleep(1)

    _post_process(cb_locs, bpf)

    with io.open(_FUNC_LOC_CACHE_FILENAME, "w", encoding="utf-8") as _fp:
        jdata = {key: asdict(obj) for key, obj in cb_locs.items()}
        _fp.write(json.dumps(jdata, sort_keys=True))

def main():
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--demangled-name-txt", "-i", default="callbacks.txt",
                        help="txt file containing demangled function names")
    parser.add_argument("--elf-path-must-contain", default="autoware",
                        help="Only readelf the files matching the path, empty string means match all paths")
    parser.add_argument("--ignore-cache", action="store_true",
                        help="Force to scan opened ELF files and insert uprobe")
    args = parser.parse_args()
    _measure_hzs(args.demangled_name_txt, args.elf_path_must_contain, args.ignore_cache)


if __name__ == "__main__":
    main()
