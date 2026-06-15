"""
Match the full callback function name for a given input.

Use case:
Given a callback function name like MapBasedPredictionNode::mapCallback,
we want to find its full name map_based_prediction::MapBasedPredictionNode::mapCallback
"""
import argparse
import io
import os
import subprocess

from dataclasses import dataclass

@dataclass
class FuncLoc:
    needle: str = ""  # Use |needle| to find exact mangled/demangled name
    mangled_name: str = ""
    demangled_name: str = ""
    elf_path: str = ""

def _is_elf(path):
    if not os.path.isfile(path):
        return False
    if path.endswith(".o"):
        return False
    with io.open(path, "rb") as _fp:
        # ELF header is \x7fELF (or equivalently, 0x7f454C46)
        if _fp.read(4) == b'\x7fELF':
            return True
    return False

def _get_elf_filenames(elf_dir):
    res = []
    for root, _dirs, files in os.walk(elf_dir):
        for filename in files:
            fpath = os.path.join(root, filename)
            if _is_elf(fpath):
                res.append(fpath)
    return res


def _get_demangled_func_name(mangled_name):
    try:
        proc_output = subprocess.check_output(["c++filt", mangled_name], encoding="utf-8")
        return proc_output.split("(", maxsplit=1)[0].strip()
    except subprocess.CalledProcessError:
        return ""

def _look_symbol(cb_names, elf_path):
    print(f"\rLook up {elf_path[-70:]:70s}", end="")
    try:
        output = subprocess.check_output(["readelf", "-s", "--wide", elf_path], encoding="utf-8")
    except subprocess.CalledProcessError:
        output = ""

    res = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 8 or fields[3] != "FUNC" or fields[4] != "GLOBAL":
            continue
        mangled_name = fields[-1].strip()
        demangled_name = _get_demangled_func_name(mangled_name)
        for cb_name in cb_names:
            if cb_name in demangled_name:
                obj = FuncLoc(needle=cb_name,
                              demangled_name=demangled_name,
                              mangled_name=mangled_name,
                              elf_path=elf_path)
                res.append(obj)
    return res


def _print_simplied_results(cb_names, func_locs):
    print("-" * 70)
    full_cb_name_dict = {}
    for loc in func_locs:
        if loc.needle not in full_cb_name_dict:
            full_cb_name_dict[loc.needle] = loc.demangled_name
    for cb_name in cb_names:
        print(f"{cb_name} -> {full_cb_name_dict.get(cb_name, '')}")


def _find_many(demangled_callback_name_file, elf_dir):
    res = []
    with io.open(demangled_callback_name_file, encoding="utf-8") as _fp:
        cb_names = _fp.read().splitlines()
    for elf_file in _get_elf_filenames(elf_dir):
        res += _look_symbol(cb_names, elf_file)
    print("\n")
    print("-" * 70)
    for obj in res:
        print(obj)
    _print_simplied_results(cb_names, res)

def _find(cb_name, elf_dir):
    res = []
    for elf_file in _get_elf_filenames(elf_dir):
        res += _look_symbol([cb_name], elf_file)
    print("\n")
    print("-" * 70)
    for obj in res:
        print(obj)
    _print_simplied_results([cb_name], res)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demangled-callback-name", "-n")
    parser.add_argument("--demangled-callback-name-file", "-f")
    default_elf_dir = os.path.join(os.environ["HOME"], "autoware", "install")
    parser.add_argument("--elf-dir", "-d", default=default_elf_dir)
    args = parser.parse_args()
    if args.demangled_callback_name:
        _find(args.demangled_callback_name, args.elf_dir)
    if args.demangled_callback_name_file:
        _find_many(args.demangled_callback_name_file, args.elf_dir)
