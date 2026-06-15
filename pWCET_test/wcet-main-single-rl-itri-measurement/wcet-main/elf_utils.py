"""
Utility functions working with ELFs.
"""
import io
import logging
import multiprocessing
import os
import subprocess
from dataclasses import dataclass


@dataclass
class FuncLocation:
    index: int = 0
    demangled_name: str = ""
    mangled_name: str = ""
    fullpath: str = ""


def is_elf(fullpath):
    if not os.path.isfile(fullpath):
        return False

    for disallowed_prefix in ["/sys/", "/var/", "/proc/"]:
        if fullpath.startswith(disallowed_prefix):
            logging.debug("No elf under %s: %s ", disallowed_prefix, fullpath)
            return False

    logging.info("Check elf for %s", fullpath)
    with io.open(fullpath, "rb") as _fp:
        # ELF header is \x7fELF (or equivalently, 0x7f454C46)
        header = _fp.read(4)
        if header == b'\x7fELF':
            return True
    return False

def _get_opened_elf_filenames():
    """
    Return a list of opened elf filenames in full paths.
    """
    logging.info("Use lsof to list elf files")
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
        if is_elf(fullpath) and _fd in ["mem", "txt"] and _type == "REG":
            elfs.add(fullpath)
    logging.info("Find %d opened ELF files", len(elfs))
    return list(elfs)


def _get_demangled_func_name(mangled_name):
    try:
        proc_output = subprocess.check_output(["c++filt", mangled_name], encoding="utf-8")
        return proc_output.split("(", maxsplit=1)[0].strip()
    except subprocess.CalledProcessError:
        return ""


def locate_callbacks(demangled_names, elfs=None, elf_path_must_contain=""):
    """
    Find where callback functions are defined.
    demangled_names(list) -- A list of demangled function names
    elfs(list) -- A list of FuncLocation objects.
    """
    if elfs is None:
        elfs = _get_opened_elf_filenames()
    res = {_: None for _ in demangled_names}
    num_found = 0
    for elf_path in sorted(elfs):
        if num_found == len(res):
            break
        if elf_path_must_contain and (elf_path_must_contain not in elf_path):
            continue
        logging.warning("looking symbols at %s", elf_path)
        try:
            output = subprocess.check_output(["readelf", "-s", "--wide", elf_path], encoding="utf-8")
        except subprocess.CalledProcessError:
            output = ""
        except UnicodeDecodeError:
            output = ""

        mangled_names = []
        for line in output.splitlines():
            # Expect the following line format:
            #   2509: 00000000000ffec0   667 FUNC    GLOBAL DEFAULT   16 tilde_expand_word
            fields = line.split()
            # ['2509:', '00000000000ffec0', '667', 'FUNC', 'GLOBAL', 'DEFAULT', '16', 'tilde_expand_word']
            if (len(fields) != 8 or
                (not fields[2].isdigit()) or
                fields[3] != "FUNC" or
                fields[4] != "GLOBAL" or
                fields[5] != "DEFAULT" or
                (not fields[6].isdigit())):
                continue

            mangled_names.append(fields[-1].strip())

        demangled_names = [_get_demangled_func_name(_) for _ in mangled_names]
        for idx, demangled_name in enumerate(demangled_names):
            if demangled_name in res and res[demangled_name] is None:
                logging.warning("Find %s in %s", demangled_name, elf_path)
                num_found += 1
                res[demangled_name] = FuncLocation(demangled_name=demangled_name,
                                                   mangled_name=mangled_names[idx],
                                                   fullpath=elf_path)
    # Remove the entries if no mangled function is found
    removed_keys = []
    for name in res.keys():
        if not res[name]:
            logging.warning("Cannot find function definition for %s", name)
            removed_keys.append(name)
    for name in removed_keys:
        res.pop(name, None) # remove without trigger exception

    return res
