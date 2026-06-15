"""
Compare the effects with and without LD_PRELOAD=libmimalloc.so
"""
import argparse
import io
import json
from dataclasses import dataclass

@dataclass
class _Diff:
    name: str = ""
    max_ms_before: float = 0
    max_ms_after: float = 0
    stdev_before: float = 0
    stdev_after: float = 0
    iesta_ppf_99_6_before: float = 0
    iesta_ppf_99_6_after: float = 0

    def csv_header(self):
        return ("name,max_ms_before,max_ms_after,stdev_before,stdev_after,"
                "iesta_ppf_99_6_before,iesta_ppf_99_6_after")

    def csv_row(self):
        return (f"{self.name},{self.max_ms_before},{self.max_ms_after},"
                f"{self.stdev_before},{self.stdev_after},"
                f"{self.iesta_ppf_99_6_before},{self.iesta_ppf_99_6_after}")

def _read_json(jfn):
    with io.open(jfn, encoding="utf-8") as _fp:
        jdata = json.loads(_fp.read())
    res = {}
    for doc in jdata:
        res[doc["name"]] = doc
    return res


def _compare(mimalloc_jfn, no_mimalloc_jfn, output_csv):
    mimalloc_dict = _read_json(mimalloc_jfn)
    no_mimalloc_dict = _read_json(no_mimalloc_jfn)

    objs = []
    for name, doc_before in no_mimalloc_dict.items():
        if name not in mimalloc_dict:
            continue
        if doc_before["max_ms"] == 0:
            continue
        doc_after = mimalloc_dict[name]
        obj = _Diff(name=name,
                    max_ms_before=doc_before["max_ms"], max_ms_after=doc_after["max_ms"],
                    iesta_ppf_99_6_before=doc_before["iesta_ppf_99_6"],
                    iesta_ppf_99_6_after=doc_after["iesta_ppf_99_6"],
                    stdev_before=doc_before["stdev"], stdev_after=doc_after["stdev"])
        print(obj)
        objs.append(obj)

    # Write csv file
    if objs:
        print(f"Write {output_csv}")
        with io.open(output_csv, "w", encoding="utf-8") as _fp:
            _fp.write(objs[0].csv_header())
            _fp.write("\n")
            for obj in objs:
                _fp.write(obj.csv_row())
                _fp.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-with-mimalloc", default="measured_results/x86_report_mimalloc.json")
    parser.add_argument("--json-no-mimalloc", default="measured_results/x86_report_no_mimalloc.json")
    parser.add_argument("--output-csv", default="out.csv")
    args = parser.parse_args()
    _compare(args.json_with_mimalloc, args.json_no_mimalloc, args.output_csv)
