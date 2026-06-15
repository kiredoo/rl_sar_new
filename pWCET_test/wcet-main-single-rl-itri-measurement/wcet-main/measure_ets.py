"""
Minimum example of finding the execution time of many callback functions
Usage:
    sudo python3 measure_ets.py -i callbacks.txt
where callbacks.txt is a text file with each line containing a demangled function name.
"""
import argparse
import logging
from measure_ets_utils import do_execution_time_sampling_by_given_txt


def main():
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--callback-names-txt", "-i", default="callbacks.txt",
                        help="txt file containing demangled function names")
    parser.add_argument("--elf-path-must-contain", default="autoware",
                        help="Only readelf the files matching the path, empty string means match all paths")
    parser.add_argument("--ignore-cache", action="store_true",
                        help="Force to scan opened ELF files and insert uprobe")
    args = parser.parse_args()
    do_execution_time_sampling_by_given_txt(args.callback_names_txt, args.elf_path_must_contain, args.ignore_cache)


if __name__ == "__main__":
    main()
