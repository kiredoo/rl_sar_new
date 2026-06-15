"""
Compare the two reports using <report_dir>/report.json.

It can be useful when we apply a strategy to autoware and want to see its overall improvements.

Usage:
    python3 compare_two_reports.py --before <report_dir_before> --after <report_dir_after>
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
class _ETImprovement:
    name: str = ""
    num_measurements_before: int = 0
    min_ms_before: float = 0
    avg_ms_before: float = 0
    max_ms_before: float = 0
    stdev_before: float = 0
    cv_before: float = 0

    num_measurements_after: int = 0
    min_ms_after: float = 0
    avg_ms_after: float = 0
    max_ms_after: float = 0
    stdev_after: float = 0
    cv_after: float = 0

    min_ms_improve: float = 0
    avg_ms_improve: float = 0
    max_ms_improve: float = 0
    stdev_improve: float = 0
    cv_improve: float = 0


@dataclass
class _WeightedStat:
    num_measurements: int = 0
    avg_ms: float = 0
    stdev: float = 0
    cv: float = 0


def _read_cb_wcets(wcet_report_json):
    logging.info("Read %s", wcet_report_json)
    with io.open(wcet_report_json, encoding="utf-8") as _fp:
        jdata = json.loads(_fp.read())

    return {doc["name"]: CallbackWCET(**doc) for doc in jdata}


def _compare_two_reports(before_dir, after_dir, output_dir):
    cb_wcet_before = _read_cb_wcets(os.path.join(before_dir, "report.json"))
    cb_wcet_after = _read_cb_wcets(os.path.join(after_dir, "report.json"))
    cb_names = [name for name in cb_wcet_before if name in cb_wcet_after]

    cb_improvements = []

    weighted_stat_before = _WeightedStat()
    weighted_stat_after = _WeightedStat()
    for cb_name in cb_names:
        if cb_wcet_before[cb_name].num_execution_time_measurements == 0:
            continue

        obj = _ETImprovement(name=cb_name)
        obj.num_measurements_before = cb_wcet_before[cb_name].num_execution_time_measurements
        obj.min_ms_before = cb_wcet_before[cb_name].measurements_min_ms
        obj.avg_ms_before = cb_wcet_before[cb_name].measurements_avg_ms
        obj.max_ms_before = cb_wcet_before[cb_name].measurements_max_ms
        obj.stdev_before = cb_wcet_before[cb_name].measurements_stdev
        obj.cv_before = cb_wcet_before[cb_name].measurements_cv

        obj.num_measurements_after = cb_wcet_after[cb_name].num_execution_time_measurements
        obj.min_ms_after = cb_wcet_after[cb_name].measurements_min_ms
        obj.avg_ms_after = cb_wcet_after[cb_name].measurements_avg_ms
        obj.max_ms_after = cb_wcet_after[cb_name].measurements_max_ms
        obj.stdev_after = cb_wcet_after[cb_name].measurements_stdev
        obj.cv_after = cb_wcet_after[cb_name].measurements_cv


        if obj.avg_ms_before < 1:
            # When avg is near 0, CV is not a reliable indicator.
            continue
        if obj.min_ms_before != 0:
            obj.min_ms_improve = (obj.min_ms_before - obj.min_ms_after) / obj.min_ms_before
        if obj.max_ms_before != 0:
            obj.max_ms_improve = (obj.max_ms_before - obj.max_ms_after) / obj.max_ms_before
        if obj.avg_ms_before != 0:
            obj.avg_ms_improve = (obj.avg_ms_before - obj.avg_ms_after) / obj.avg_ms_before
        if obj.stdev_before != 0:
            obj.stdev_improve = (obj.stdev_before - obj.stdev_after) / obj.stdev_before
        if obj.cv_before != 0:
            obj.cv_improve = (obj.cv_before - obj.cv_after) / obj.cv_before
        cb_improvements.append(obj)

        weighted_stat_before.avg_ms += obj.avg_ms_before * obj.num_measurements_before
        weighted_stat_before.cv += obj.cv_before * obj.num_measurements_before
        weighted_stat_before.num_measurements += obj.num_measurements_before
        weighted_stat_after.avg_ms += obj.avg_ms_after * obj.num_measurements_after
        weighted_stat_after.cv += obj.cv_after * obj.num_measurements_after
        weighted_stat_after.num_measurements += obj.num_measurements_after

    if weighted_stat_before.num_measurements != 0:
        weighted_stat_before.avg_ms = weighted_stat_before.avg_ms / weighted_stat_before.num_measurements
        weighted_stat_before.cv = weighted_stat_before.cv / weighted_stat_before.num_measurements
        weighted_stat_after.avg_ms = weighted_stat_after.avg_ms / weighted_stat_after.num_measurements
        weighted_stat_after.cv = weighted_stat_after.cv / weighted_stat_after.num_measurements
    else:
        weighted_stat_before.avg_ms = 0
        weighted_stat_before.cv = 0
        weighted_stat_after.avg_ms = 0
        weighted_stat_after.cv = 0

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)
    copy_css_js(output_dir)
    template_fn = os.path.join(DEFAULT_HTML_TEMPLATE_DIR, "compare_two_reports.html")
    with io.open(template_fn, encoding="utf-8") as _fp:
        template = Template(_fp.read())
    html_contents = template.render(before_dir=before_dir, after_dir=after_dir,
                                    weighted_stat_before=weighted_stat_before,
                                    weighted_stat_after=weighted_stat_after,
                                    cbs=cb_improvements)
    html_fn = os.path.join(output_dir, "index.html")
    print(f"Write {html_fn}")
    with io.open(html_fn, "w", encoding="utf-8") as _fp:
        _fp.write(html_contents)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", "-b", default="report_dir_before")
    parser.add_argument("--after", "-a", default="report_dir_after")
    parser.add_argument("--output-dir", "-o", default="compared_reports")
    args = parser.parse_args()

    _compare_two_reports(args.before, args.after, args.output_dir)

if __name__ == "__main__":
    main()
