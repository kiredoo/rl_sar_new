"""
Utility functions for measuing execution time of many callback functions
"""
import datetime
import io
import json
import logging
import os
import signal
import socket
import statistics
import time
import ctypes as ct  # NEW: for BPF table element access
from dataclasses import asdict

from bcc import BPF
from jinja2 import Template

from callback_execution_time import (CallbackExecutionTime,
                                     CallbackExecutionTimeCollection)
from elf_utils import FuncLocation, locate_callbacks
from sig_utils import got_sigint, sigint_handler

_EBPF_C_TEMPLATE = "ebpf_ets_template.c"
_EBPF_C_RENDERED = ".ebpf_ets.c"
_FUNC_LOC_CACHE_FILENAME = ".measure_ets_cache.json"
_MAX_NUM_SAMPLES = 3000
SAMPLED_EXECUTION_TIME_DIR = "sampled_execution_time"
_EPF_HAS_LOADED_FILENAME = "/tmp/ebpf_is_loaded"

_EBPF_GOT_SIGINT = False

def _create_loaded_status_file():
    if not os.path.isfile(_EPF_HAS_LOADED_FILENAME):
        open(_EPF_HAS_LOADED_FILENAME, "a").close()

def _delete_loaded_status_file():
    try:
        os.unlink(_EPF_HAS_LOADED_FILENAME)
    except FileNotFoundError:
        pass

def _ebpf_sigint_handler(_sig, _frame):
    global _EBPF_GOT_SIGINT
    _EBPF_GOT_SIGINT = True
    _delete_loaded_status_file()

def _ebpf_got_sigint():
    return _EBPF_GOT_SIGINT


def is_ebpf_loaded():
    return os.path.isfile(_EPF_HAS_LOADED_FILENAME)

def locate_callbacks_by_txt(callback_names_txt, elf_path_must_contain, ignore_cache, cached_json_file=_FUNC_LOC_CACHE_FILENAME):
    """
    Return a dict[str, FuncLocation]
    """
    if not os.path.isfile(callback_names_txt):
        logging.error("File not exist: %s", callback_names_txt)
        return {}
    names = []
    # Get demangled callback names, skip lines beginning with #
    with io.open(callback_names_txt, encoding="utf-8") as _fp:
        lines = _fp.read().splitlines()
        for line in lines:
            if line and line[0] != "#":
                names.append(line.strip())
    logging.warning("Insert uprobes for %s", names)

    if not ignore_cache:
        if os.path.isfile(cached_json_file) and os.path.getsize(cached_json_file) > 0:
            with io.open(cached_json_file, encoding="utf-8") as _fp:
                jdata = json.loads(_fp.read())
            res = {}
            for name in names:
                if name in jdata:
                    res[name] = FuncLocation(**jdata[name])
                else:
                    logging.warning("%s not in %s. please check!", name, cached_json_file)
            return res

    cb_locs = locate_callbacks(names, elf_path_must_contain=elf_path_must_contain)
    index = 0
    for _, cb_loc in cb_locs.items():
        cb_loc.index = index
        index += 1
    return cb_locs

def create_bpf(cb_locs, template_fn=_EBPF_C_TEMPLATE, ebpf_c_fn=_EBPF_C_RENDERED):
    cur_dir = os.path.dirname(os.path.realpath(__file__))

    with io.open(os.path.join(cur_dir, template_fn), encoding="utf-8") as _fp:
        template = Template(_fp.read())
    # keep current template contract (expects dict and uses .items())
    ebpf_code = template.render(cb_locs=cb_locs)

    ebpf_c_fullpath = os.path.join(cur_dir, ebpf_c_fn)
    logging.warning("Write %s", ebpf_c_fullpath)
    with io.open(ebpf_c_fullpath, "w", encoding="utf-8") as _fp:
        _fp.write(ebpf_code)

    return BPF(src_file=ebpf_c_fullpath)

def _insert_probes(cb_locs, bpf):
    # Attach function probes
    for demangled_name, loc in cb_locs.items():
        logging.warning("Attach uprobes for %s, mangled_name: %s, elf: %s",
                        demangled_name, loc.mangled_name, loc.fullpath)
        bpf.attach_uprobe(name=loc.fullpath,
                          sym=loc.mangled_name,
                          fn_name=f"cb_in_{loc.mangled_name}")
        bpf.attach_uretprobe(name=loc.fullpath,
                             sym=loc.mangled_name,
                             fn_name=f"cb_out_{loc.mangled_name}")

    # Attach syscall hooks (REVERTED to your original behavior)
    machine = os.uname().machine
    if machine == "aarch64":
        bpf.attach_kprobe(event="invoke_syscall", fn_name="syscall_in")
        bpf.attach_kretprobe(event="invoke_syscall", fn_name="syscall_out")
    elif machine == "x86_64":
        bpf.attach_kprobe(event="__x64_sys_open", fn_name="syscall_in")
        bpf.attach_kretprobe(event="__x64_sys_open", fn_name="syscall_out")
    else:
        logging.error("Unknown machine type: %s", machine)

def _still_sampling(bpf, cb_locs):
    for loc in cb_locs.values():
        # bcc.Table supports int key directly; treat 0 as first slot
        try:
            num_samples = bpf[f"g_num_samples_{loc.mangled_name}"].get(0).value
        except Exception:
            num_samples = _MAX_NUM_SAMPLES
        if num_samples < _MAX_NUM_SAMPLES:
            return True
    return False

def _post_process(cb_locs, bpf) -> CallbackExecutionTimeCollection:
    """
    Read per-callback response_ns and syscall_ns (new or legacy),
    and store compute_ns = max(0, response - syscall) into samples.

    Burn-in rule:
    - If a callback has 3 or more samples, drop the first 2 samples.
    - If it has exactly 2 samples, drop the first 1 sample and keep 1.
    - If it has only 1 sample, keep it (do not drop anything).
    """
    def _get_table_or_none(tabname: str):
        try:
            return bpf.get_table(tabname)
        except KeyError:
            return None

    collback_col = CallbackExecutionTimeCollection(
        unit="nanosecond",
        sampling_time=datetime.datetime.now().isoformat(),
        hostname=socket.gethostname())

    for demangled_name, loc in cb_locs.items():
        # 1) Get response / num_samples tables
        resp_tab = _get_table_or_none(f"g_response_times_ns_{loc.mangled_name}")
        num_tab = _get_table_or_none(f"g_num_samples_{loc.mangled_name}")
        if resp_tab is None or num_tab is None:
            logging.warning(
                "[post] skip %s: response/num_samples table missing",
                demangled_name,
            )
            continue

        # 2) Get syscall table
        sys_tab = _get_table_or_none(f"g_syscall_times_ns_{loc.mangled_name}")
        if sys_tab is None:
            sys_tab = _get_table_or_none(
                f"g_acc_syscall_times_ns_{loc.mangled_name}"
            )
            if sys_tab is None:
                class _ZeroTab:  # mimic bcc table API
                    def __getitem__(self, k):
                        class V:
                            value = 0
                        return V()
                sys_tab = _ZeroTab()
                logging.warning(
                    "[post] no syscall table for %s; treat syscall_ns as 0",
                    demangled_name,
                )

        # 3) Read num_samples
        zero = ct.c_int(0)
        try:
            n = int(ct.c_int32(num_tab[zero].value).value)
        except Exception:
            n = 0

        cb_et = CallbackExecutionTime(name=demangled_name)

        # 4) Extract all samples: compute_ns = max(response_ns - syscall_ns, 0)
        if n > 0:
            for i in range(n):
                k = ct.c_int(i)
                try:
                    resp_ns = int(resp_tab[k].value)
                except Exception:
                    resp_ns = 0
                try:
                    sys_ns = int(sys_tab[k].value)
                except Exception:
                    sys_ns = 0

                if resp_ns > 0:
                    comp_ns = resp_ns - sys_ns
                    if comp_ns < 0:
                        comp_ns = 0
                    cb_et.samples.append(comp_ns)

        # 5) Burn-in guard: decide how many samples to drop based on count
        n_samples = len(cb_et.samples)
        if n_samples >= 3:
            burn_in_to_drop = 2
        elif n_samples == 2:
            burn_in_to_drop = 1
        else:
            burn_in_to_drop = 0

        if burn_in_to_drop > 0:
            logging.warning(
                "%s: drop first %d samples as burn-in (original %d samples)",
                demangled_name,
                burn_in_to_drop,
                n_samples,
            )
            cb_et.samples = cb_et.samples[burn_in_to_drop:]
        else:
            logging.warning(
                "%s: burn-in not applied (only %d samples)",
                demangled_name,
                n_samples,
            )

        # 6) Statistics (only log mean/stdev when remaining samples > 2)
        if len(cb_et.samples) > 2:
            mean = statistics.mean(cb_et.samples)
            stdev = statistics.stdev(cb_et.samples)
            logging.warning(
                (
                    f"{demangled_name} -- min: {min(cb_et.samples):,} ns, "
                    f"max: {max(cb_et.samples):,} ns, "
                    f"avg: {mean:,.0f} ns, "
                    f"stdev: {stdev:,.0f}, "
                    f"#samples(after burn-in): {len(cb_et.samples)}"
                )
            )
        else:
            logging.warning(
                "%s -- No sufficient statistics data, #samples after burn-in: %d",
                demangled_name,
                len(cb_et.samples),
            )

        collback_col.callbacks.append(cb_et)

    return collback_col



def _write_ets_to_json(collback_col):
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    dest_dir = os.path.join(cur_dir, SAMPLED_EXECUTION_TIME_DIR)
    if not os.path.isdir(dest_dir):
        os.makedirs(dest_dir)
    now = datetime.datetime.now()
    dest_filename = os.path.join(dest_dir, now.strftime("%Y%m%d%H%M%S") + ".json")
    logging.warning("Write %s", dest_filename)
    with io.open(dest_filename, "w", encoding="utf-8") as _fp:
        _fp.write(json.dumps(asdict(collback_col), sort_keys=True))


def do_execution_time_sampling_by_given_txt(callback_names_txt, elf_path_must_contain="", ignore_cache=False):
    """
    Given a txt file with each line corresponding to a demangled callback function name,
    sample the execution time of those functions.

    The output is a json file marked with the sampling time, see test_data.json for an example.
    """
    signal.signal(signal.SIGINT, _ebpf_sigint_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, _ebpf_sigint_handler)

    cb_locs = locate_callbacks_by_txt(callback_names_txt, elf_path_must_contain, ignore_cache)

    bpf = create_bpf(cb_locs)
    _insert_probes(cb_locs, bpf)
    _create_loaded_status_file()

    with io.open(_FUNC_LOC_CACHE_FILENAME, "w", encoding="utf-8") as _fp:
        jdata = {key: asdict(obj) for key, obj in cb_locs.items()}
        _fp.write(json.dumps(jdata, sort_keys=True))

    logging.info("Collection process stops when hitting Ctrl+C or |samples| reaches maximum")

    while (not _ebpf_got_sigint()) and _still_sampling(bpf, cb_locs):
        time.sleep(1)

    collback_col = _post_process(cb_locs, bpf)
    _write_ets_to_json(collback_col)
    _delete_loaded_status_file()

