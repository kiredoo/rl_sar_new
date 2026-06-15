"""
Calculate the EDF (Earliest Deadline First) parameters (runtime, deadline, period) for each callback.
Each parameter uses nanosecond (int) as its unit.

There aret two inputs for this program.
One is callback's hz, which is used to decide the deadline/period parameter.
For now, we set deadline = period for the sake of simpilicity, but a more
sophisticated deadline is required if we need more find-tuned result.
The other input is WCET of each callback. Since we use EVT to estimate WCET,
we will list the SCHED_DEADLINE parameters under different PPF and corresponding CPU utility.
"""
import argparse
import io
import json
import os
import logging
from dataclasses import dataclass

from wcet_utils import CallbackWCET

@dataclass
class EDFParameter:
    name: str = ""
    hz: float = 0
    ppf_str: str = "0.95"
    runtime_ns: int = 0
    deadline_ns: int = 0
    period_ns: int = 0
    cpu_utility: float = 0
    remark: str = ""

    def csv_header(self):
        return "name,hz,ppf,runtime,deadline,period,cpu_utility,remark"

    def as_csv_row(self):
        return (f"{self.name},{self.hz},{self.ppf_str},"
                f"{self.runtime_ns},{self.deadline_ns},{self.period_ns},"
                f"{self.cpu_utility},{self.remark}")


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

def _dump_params_as_csv(params, csv_fn):
    if not params:
        logging.warning("No calculated EDF params")
        return
    logging.warning("Write %s", csv_fn)
    with io.open(csv_fn, "w", encoding="utf-8") as _fp:
        _fp.write(params[0].csv_header())
        _fp.write("\n")
        for param in params:
            _fp.write(param.as_csv_row())
            _fp.write("\n")


def _calc_edf_parameters(wcet_report_json, callbacks_hz_spec_csv, output_csv_fn):
    cb_wcets = _read_cb_wcets(wcet_report_json)
    cb_hzs = _read_cb_hz_from_csv(callbacks_hz_spec_csv)
    params = []
    ppf_strs = ["0.95", "0.99", "0.996", "0.999", "0.9999", "0.99999"]
    for cb_name, cb_wcet in cb_wcets.items():
        for ppf_str in ppf_strs:
            param = EDFParameter(name=cb_name, ppf_str=ppf_str)
            param.hz = cb_hzs.get(cb_name, 0)
            if param.hz == 0:
                param.remark = "No Hz data"
            elif cb_wcet.num_execution_time_measures == 0:
                param.remark = "No measured WCET"
            else:
                param.period_ns = int(1e9 / param.hz)
                param.deadline_ns = param.period_ns
                param.runtime_ns = int(cb_wcet.get_wcet_ms_by_ppf_str(ppf_str) * 1e6)
                param.cpu_utility = param.runtime_ns / param.period_ns

            if param.cpu_utility > 1:
                param.remark = "cpu overload"
            params.append(param)
    _dump_params_as_csv(params, output_csv_fn)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wcet-report-json", "-i",
                        default="measured_results/jetson_orin64_report.json")
    parser.add_argument("--callbacks-hz-spec-csv", default="callbacks_hz_spec.csv")
    parser.add_argument("--output", "-o", default="edf_params.csv")
    args = parser.parse_args()

    _calc_edf_parameters(args.wcet_report_json, args.callbacks_hz_spec_csv, args.output)

if __name__ == "__main__":
    main()
