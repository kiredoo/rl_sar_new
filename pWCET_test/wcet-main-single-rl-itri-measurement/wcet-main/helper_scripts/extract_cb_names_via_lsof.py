"""
Extract demangled callback names via lsof:

Note:
Please launch autoware before running this script.
"""
import argparse
import io
import logging
import os
import subprocess
from dataclasses import dataclass


@dataclass
class FuncLoc:
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

def _get_opened_elf_filenames(path_must_contain):
    try:
        output = subprocess.check_output(["lsof"], encoding="utf-8")
    except subprocess.CalledProcessError:
        output = ""
    elfs = set()
    for line in output.splitlines():
        # line format:
        # xscreensa   10805                               chtseng  mem       REG                8,3    240936    7604323 /usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2
        fields = line.split()
        if len(fields) < 9:
            continue
        _fd = fields[3]
        _type = fields[4]
        _size = fields[6]
        fullpath = fields[-1]
        if not _size.isdigit():
            continue
        if path_must_contain not in fullpath:
            continue
        if _is_elf(fullpath) and _fd in ["mem", "txt"] and _type == "REG":
            elfs.add(fullpath)
    logging.info("Find %d opened ELF files", len(elfs))
    return list(elfs)

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

def _is_valid_entry(fields):
    return bool(len(fields) == 8 and fields[3] == "FUNC" and
                fields[2].isdigit() and
                fields[4] == "GLOBAL" and
                fields[5] == "DEFAULT" and
                fields[6].isdigit())

def _is_ctor(func_name):
    # constructor
    name = func_name.split("(")[0]
    fields = name.split("::")
    if len(fields) < 2:
        return False
    return bool(fields[-1] == fields[-2])
    #return bool(fields[-1].split("(")[0] == fields[-2])

def _is_dtor(func_name):
    # destructor
    fields = func_name.split("::")
    if len(fields) < 2:
        return False
    return bool(fields[-1][1:] == fields[-2] and fields[-1][0] == "~")

def _is_test_func(func_name):
    return bool("_test_" in func_name)

def _is_cuda_func(func_name):
    # Example: __device_stub__ZN8autoware17lidar_transfusion20shufflePoints_kernelEPKfPKjPfmmm
    return bool("__device_stub" in func_name)

def _is_malformed(demangled_name):
    for ch in " <>[]":
        if ch in demangled_name:
            return True
    return False

def _is_external_library(func_name):
    return bool(func_name.startswith("google::"))

def _is_cpp_builtin(func_name):
    return bool(func_name.startswith("std::"))

def _is_getter_or_setter(func_name):
    fields = func_name.split("::")
    return fields[-1].startswith("get") or fields[-1].startswith("set")

def _is_generated_func(func_name):
    for needle in ["__srv__", "::srv::", "__msg__", "::msg::", "_rosidl_"]:
        if needle in func_name:
            return True
    return False

def _look_symbol(elf_path):
    print(f"\rLook up {elf_path[-70:]:70s}", end="")
    try:
        output = subprocess.check_output(["readelf", "-s", "--wide", elf_path], encoding="utf-8")
    except subprocess.CalledProcessError:
        output = ""

    def _should_skip(demangled_name):
        return bool(_is_ctor(demangled_name) or
                    _is_dtor(demangled_name) or
                    _is_cuda_func(demangled_name) or
                    _is_test_func(demangled_name) or
                    _is_malformed(demangled_name) or
                    _is_getter_or_setter(demangled_name) or
                    _is_external_library(demangled_name) or
                    _is_cpp_builtin(demangled_name) or
                    _is_generated_func(demangled_name) or
                    demangled_name in ["main", "_start"])

    res = []
    for line in output.splitlines():
        fields = line.split()
        if not _is_valid_entry(fields):
            continue
        mangled_name = fields[-1].strip()
        demangled_name = _get_demangled_func_name(mangled_name)
        if _should_skip(demangled_name):
            continue
        obj = FuncLoc(demangled_name=demangled_name,
                      mangled_name=mangled_name,
                      elf_path=elf_path)
        res.append(obj)
    return res


def _find(path_must_contain):
    cbs = []
    seen_demangled_names = set()
    for elf_file in _get_opened_elf_filenames(path_must_contain):
        for cb in _look_symbol(elf_file):
            if cb.demangled_name not in seen_demangled_names:
                seen_demangled_names.add(cb.demangled_name)
                cbs.append(cb)
    print("")
    print("Write out.txt")
    with io.open("out.txt", "w", encoding="utf-8") as _fp:
        for cb in cbs:
            _fp.write(cb.demangled_name)
            _fp.write("\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--path-must-contain", default="autoware")
    args = parser.parse_args()
    _find(args.path_must_contain)
