"""
Scan callback function names based on std::bind

Callback functions are registered in create_subscription or create_wall_timer with std::bind.
This script use this property to (heuristically) get callback function names.
"""
import argparse
import io
import os
import re

# std::bind(&UdpSenderNode::subscriber_callback
RGX = re.compile(r".*std::bind\((?P<cb_name>.[_a-zA-Z][:_a-zA-Z0-9]*),.*")

def _get_cb_name(line):
    match = RGX.match(line)
    if match:
        cb_name = match.expand(r"\g<cb_name>")
        if cb_name[0] == "&":
            cb_name = cb_name[1:]
        return cb_name
    return ""

def _find_std_bind(cpp):
    std_binds = set()
    with io.open(cpp, encoding="utf-8") as _fp:
        lines = _fp.read().splitlines()
    for idx, line in enumerate(lines):
        if "std::bind(" in line:
            cb_name = _get_cb_name(line)
            if cb_name:
                std_binds.add(cb_name)
    return std_binds

def _find(src_dir):
    if not os.path.isdir(src_dir):
        print(f"No such dir: {src_dir}")
        return
    std_binds = []
    for root, dirs, files in os.walk(src_dir):
        for filename in files:
            if filename.endswith(".cpp") and "test" not in filename:
                fullpath = os.path.join(root, filename)
                std_binds += _find_std_bind(fullpath)
    for line in sorted(std_binds):
        print(line)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--src-dir", "-d", default=os.path.join(os.environ["HOME"], "autoware"))
    args = parser.parse_args()
    _find(args.src_dir)
