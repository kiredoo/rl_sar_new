"""
Aggregate the resources consumed by callback functions to the module-level.
We do this by based on the coding standard of callback function names.

Usage:
    python3 aggreate_cb_to_module.py [args]
"""
import argparse
import io
import json
import logging
import os
from dataclasses import dataclass

from jinja2 import Template

from wcet_utils import DEFAULT_HTML_TEMPLATE_DIR, CallbackWCET, copy_css_js


@dataclass
class CBConsumedResource:
    name: str = ""
    hz: float = 0
    wcet_ms: int = 0
    avg_et_ms: float = 0
    period_ms: float = 0
    cpu_utility_avg: float = 0
    cpu_utility_wcet: float = 0

@dataclass
class ModuleConsumedResource:
    name: str = ""
    cpu_utility_avg: float = 0
    cpu_utility_wcet: float = 0


def _read_cb_hz_from_csv(csv_fn):
    # The csv file has two columns: cb_name,hz
    logging.info("Read %s", csv_fn)
    with io.open(csv_fn, encoding="utf-8") as _fp:
        lines = _fp.read().splitlines()
    res = {}
    for line in lines:
        cb_name, hz_str = line.split(",")
        try:
            hz = float(hz_str)
        except ValueError:
            logging.info("No Hz info for %s", cb_name)
            continue
        res[cb_name] = hz
    return res


def _read_cb_wcets(wcet_report_json):
    logging.info("Read %s", wcet_report_json)
    with io.open(wcet_report_json, encoding="utf-8") as _fp:
        jdata = json.loads(_fp.read())

    return {doc["name"]: CallbackWCET(**doc) for doc in jdata}


def _collect_cb_resources(wcet_report_json, callbacks_hz_spec_csv):
    cb_wcets = _read_cb_wcets(wcet_report_json)
    cb_hzs = _read_cb_hz_from_csv(callbacks_hz_spec_csv)
    cb_resources = []
    for cb_name, cb_wcet in cb_wcets.items():
        cb_resource = CBConsumedResource(name=cb_name)
        cb_resource.hz = cb_hzs.get(cb_name, 0)
        if cb_resource.hz == 0:
            continue
        elif cb_wcet.num_execution_time_measures == 0:
            continue

        cb_resource.period_ms = 1e3 / cb_resource.hz
        cb_resource.wcet_ms = cb_wcet.get_wcet_ms_by_ppf_str("0.996")
        cb_resource.avg_et_ms = cb_wcet.avg_ms
        cb_resource.cpu_utility_wcet = cb_resource.wcet_ms / cb_resource.period_ms
        cb_resource.cpu_utility_avg = cb_resource.avg_et_ms / cb_resource.period_ms
        cb_resources.append(cb_resource)
    cb_resources.sort(key=lambda x: x.name)
    return cb_resources


def _aggregate_cb_to_module(cb_resources):
    module_resources_dict = {}
    for cb_res in cb_resources:
        module_name = "::".join(cb_res.name.split("::")[:-1])
        if module_name not in module_resources_dict:
            module_resources_dict[module_name] = ModuleConsumedResource(name=module_name)
        module_resources_dict[module_name].cpu_utility_avg += cb_res.cpu_utility_avg
        module_resources_dict[module_name].cpu_utility_wcet += cb_res.cpu_utility_wcet
    module_resources = list(module_resources_dict.values())
    module_resources.sort(key=lambda x: x.name)
    return module_resources


def _aggregate(wcet_report_json, callbacks_hz_spec_csv, output_dir):
    cb_resources = _collect_cb_resources(wcet_report_json, callbacks_hz_spec_csv)
    module_resources = _aggregate_cb_to_module(cb_resources)
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)
    copy_css_js(output_dir)
    template_fn = os.path.join(DEFAULT_HTML_TEMPLATE_DIR, "aggregate_to_module.html")
    with io.open(template_fn, encoding="utf-8") as _fp:
        template = Template(_fp.read())
    html_contents = template.render(cb_resources=cb_resources,
                                    module_resources=module_resources)
    html_fn = os.path.join(output_dir, "index.html")
    print(f"Write {html_fn}")
    with io.open(html_fn, "w", encoding="utf-8") as _fp:
        _fp.write(html_contents)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wcet-report-json", "-i",
                        default="measured_results/jetson_orin64_report.json")
    parser.add_argument("--callbacks-hz-spec-csv", default="callbacks_hz_spec.csv")
    parser.add_argument("--output-dir", "-o", default="module_resource")
    args = parser.parse_args()

    _aggregate(args.wcet_report_json, args.callbacks_hz_spec_csv, args.output_dir)

if __name__ == "__main__":
    main()
