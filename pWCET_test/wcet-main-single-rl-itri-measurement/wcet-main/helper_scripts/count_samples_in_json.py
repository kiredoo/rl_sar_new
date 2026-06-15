import argparse
import io
import json

def _count(jfn):
    with io.open(jfn, encoding="utf-8") as _fp:
        jdata = json.loads(_fp.read())

    counters = {}
    for doc in jdata["callbacks"]:
        counters[doc["name"]] = len(doc["samples"])

    for cb_name, freq in sorted(counters.items()):
        print(f"{cb_name} {freq}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-input", "-i", required=True)
    args = parser.parse_args()
    _count(args.json_input)
