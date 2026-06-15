# pylint: disable=invalid-name
"""
Generate a report, given measured execution time.
"""
import glob
import io
import json
import logging
import os
import shutil
import statistics
from dataclasses import asdict, dataclass, field

import matplotlib.pyplot as plt
import numpy as np
from jinja2 import Template
from scipy.stats import genextreme

from cv_manager import CVManager
from iesta import IESTA
from ljung_box import is_iid
from os_utils import sanitize_filename
from system_info import collect_system_info
from wcet_consts import DEFAULT_FIG_SIZE
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable

_DEFAULT_PPF = 0.996
_NUM_BINS = 100
_DEFAULT_BLOCKS_PER_RUN = 15  # how many blocks we split per JSON (per rosbag run)
DEFAULT_REPORT_DIR = "report"
DEFAULT_IMAGES_DIR = "images"
DEFAULT_CSV_DIR = "csv"
DEFAULT_HTML_TEMPLATE_DIR = "report_template"


def _load_callback_execution_time_measurements_from_json(json_filename):
    if not os.path.isfile(json_filename):
        return {}
    with io.open(json_filename, encoding="utf-8") as _fp:
        jdata = json.loads(_fp.read())
    res = {}
    for cb in jdata["callbacks"]:
        name = cb["name"]
        # To ensure every callback to have a record in the return value, we
        # assign the block maxima to 0 if we don't capture any execution of
        # the callback.
        # Let the caller of this function handle the case of block maxima = 0.
        res[name] = cb["samples"]
    return res

def _load_sample_unit_from_json(json_filename):
    unknown = "unknown_unit"
    if not os.path.isfile(json_filename):
        return unknown
    with io.open(json_filename, encoding="utf-8") as _fp:
        jdata = json.loads(_fp.read())
    return jdata.get("unit", unknown)

def _get_sampled_excution_time_json_filenames(json_dir):
    if not os.path.isdir(json_dir):
        return []
    res = []
    for fname in os.listdir(json_dir):
        if not fname.endswith(".json"):
            continue
        if len(fname) == 19 and fname[:-5].isdigit():
            # match the pattern like 20241016032634.json
            res.append(os.path.join(json_dir, fname))
    return res

def _split_into_block_maxima(measurements, num_blocks_per_run=_DEFAULT_BLOCKS_PER_RUN):
    n = len(measurements)
    if n == 0:
        return []

    # Too few samples: treat each sample as its own block
    if n <= num_blocks_per_run:
        return list(measurements)

    block_size = n // num_blocks_per_run
    if block_size <= 0:
        block_size = 1

    block_maxima = []
    for i in range(num_blocks_per_run):
        start = i * block_size
        end = (i + 1) * block_size if i < num_blocks_per_run - 1 else n
        if start >= n:
            break
        block = measurements[start:end]
        if not block:
            continue
        block_maxima.append(max(block))
    return block_maxima


def _collect_callback_execution_time_measurements(json_dir) -> dict:
    cb_ets: dict[str, CallbackExecutionTimeMeasures] = {}

    for jfn in _get_sampled_excution_time_json_filenames(json_dir):
        cb_measurements_dict = _load_callback_execution_time_measurements_from_json(jfn)

        for cb_name, measurements in cb_measurements_dict.items():
            if cb_name not in cb_ets:
                cb_ets[cb_name] = CallbackExecutionTimeMeasures(name=cb_name)
                cb_ets[cb_name].unit = _load_sample_unit_from_json(jfn)

            if not measurements:
                continue

            cb_ets[cb_name].add_measurements(measurements)

            for bm in _split_into_block_maxima(measurements):
                cb_ets[cb_name].add_block_maxima(bm)

    return cb_ets


def _savefig(output_filename):
    path, _ = os.path.split(output_filename)
    if not os.path.isdir(path):
        os.makedirs(path)
    logging.info("Write %s", output_filename)
    plt.savefig(output_filename)


def _export_block_maxima_and_iesta(block_maxima, iesta_vals, output_filename):
    path = os.path.dirname(output_filename)
    if not os.path.isdir(path):
        os.makedirs(path)
    if len(block_maxima) != len(iesta_vals):
        logging.error("Inconsistent length -- block_maxima: %d, iesta_vals: %d",
                      len(block_maxima), len(iesta_vals))
        return
    logging.info("Write %s", output_filename)
    with io.open(output_filename, "w", encoding="utf-8") as _fp:
        _fp.write("block_maxima,iesta\n")
        for idx, val in enumerate(block_maxima):
            _fp.write(f"{val:.6f},{iesta_vals[idx]:.6f}\n")


def _export_execution_time_measurements(measurements, output_filename):
    path = os.path.dirname(output_filename)
    if not os.path.isdir(path):
        os.makedirs(path)
    logging.info("Write %s", output_filename)
    with io.open(output_filename, "w", encoding="utf-8") as _fp:
        _fp.write("measurements\n")
        for val in measurements:
            _fp.write(f"{val:.6f}\n")


def _plot_gev_pdf(cb_name, shape, loc, scale, output_filename):
    """
    Plot the PDF for the GEV (Generalized Extreme Value) Distribution.
    """
    plt.figure(figsize=DEFAULT_FIG_SIZE)
    gev = genextreme(shape, loc=loc, scale=scale)
    lower_bound = gev.ppf(0.00001)
    upper_bound = gev.ppf(0.99999)
    x = np.linspace(lower_bound, upper_bound, 200)
    gev_pdf = gev.pdf(x)
    plt.plot(x, gev_pdf, color="blue", label=f"{cb_name}: shape {shape:.2f}, loc {loc:.2f}, scale {scale:.2f}")

    for ppf in [0.996]:
        et = gev.ppf(ppf)
        density = gev.pdf(et)
        percent = ppf * 100
        plt.annotate(text=f"PPF {percent:.1f}%: {et:.3f}", xy=(et, density))
        plt.plot(et, density, "o")

    # draw upper bound
    plt.annotate(text=f"{x[-1]:.2f}", xy=(x[-1], gev_pdf[-1]))
    plt.plot(x[-1], gev_pdf[-1], "o")

    plt.title(f"{cb_name} GEV PDF")
    plt.xlabel('Execution Time (ms)')
    plt.ylabel('Density')
    plt.grid(True)
    if output_filename:
        _savefig(output_filename)
    else:
        plt.show()
    plt.close()
    return 0

def _plot_pdf(cb_name, block_maxima, output_filename, json_dir):
    jsons = _get_sampled_excution_time_json_filenames(json_dir)
    samples_list = []
    for jfn in sorted(jsons):
        d = _load_callback_execution_time_measurements_from_json(jfn)
        arr = d.get(cb_name, [])
        if arr:
            #samples_list.append(arr)
            ms_arr = [v / 1e6 for v in arr]
            samples_list.append(ms_arr)
    if not samples_list:
        plt.figure(figsize=DEFAULT_FIG_SIZE)
        #plt.hist(block_maxima, bins=_NUM_BINS, density=True)
        ms_bm = [v / 1e6 for v in block_maxima]
        plt.hist(ms_bm, bins=_NUM_BINS, density=True)
        plt.title(cb_name)
        plt.xlabel('Execution Time (ms)')
        plt.ylabel('Density')
        plt.grid(True)
        if output_filename: _savefig(output_filename)
        else: plt.show()
        plt.close()
        return

    plt.figure(figsize=DEFAULT_FIG_SIZE)
    norm = Normalize(vmin=0, vmax=len(samples_list)-1)
    cmap = plt.cm.jet
    for idx, series in enumerate(samples_list):
        x = np.arange(1, len(series)+1)
        plt.plot(x, series, color=cmap(norm(idx)), linewidth=0.8)

    sm = ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = plt.colorbar(sm)
    ticks = [0, (len(samples_list)-1)//2, len(samples_list)-1]
    cbar.set_ticks(ticks)
    cbar.set_ticklabels([str(t) for t in ticks])
    cbar.set_label('index')

    #plt.title(f"Raw Data Curves")
    plt.xlabel('Samples')
    plt.ylabel('execution time')
    plt.grid(True)

    if output_filename:
        _savefig(output_filename)
    else:
        plt.show()
    plt.close()


def _plot_cdf(cb_name, block_maxima, measurements, shape, loc, scale, output_filename):
    plt.figure(figsize=DEFAULT_FIG_SIZE)

    # plot block_maxima CDF
    # bin_edges is a list of _NUM_BINS + 1 values that represent _NUM_BINS intervals
    # densities is a list of _NUM_BINS values that represent the density in each bin
    densities, bin_edges = np.histogram(block_maxima, bins=_NUM_BINS, density=True)
    total_density = sum(densities)

    cdf = []
    cur = 0
    for density in densities:
        cur += density
        cdf.append(cur / total_density)

    plt.plot(bin_edges[1:], cdf, label="block maxima")

    # plot measurements CDF
    cdf = [0] * len(bin_edges)
    last_cdf_val = 0
    idx = 0
    count = 0
    for et in sorted(measurements):
        if et <= bin_edges[idx]:
            count += 1
        else:
            cdf[idx] = count / len(measurements)
            last_cdf_val = cdf[idx]
            idx += 1
            count += 1
    while idx < len(bin_edges):
        cdf[idx] = last_cdf_val
        idx += 1

    plt.plot(bin_edges, cdf, label="measurements")

    # plot GEV CDF
    xvals = list(bin_edges)
    gev = genextreme(shape, loc, scale)
    ppf_996 = gev.ppf(0.996)
    if xvals and ppf_996 > xvals[-1]:
        xvals.append(ppf_996)

    gev_vals = gev.cdf(xvals)
    label = (f"GEV (shape {shape:.2f}, "
             f"loc {loc:.2f}, "
             f"scale {scale:.2f})")
    plt.plot(xvals, gev_vals, label=label)

    plt.xlabel('Execution Time (ms)')
    plt.ylabel('Cumulative Probability')
    plt.title(cb_name)
    plt.grid(True)
    plt.legend()
    if output_filename:
        _savefig(output_filename)
    else:
        plt.show()
    plt.close()


def copy_css_js(dest_dir):
    if not os.path.isdir(dest_dir):
        os.makedirs(dest_dir)
    for fn in glob.glob(DEFAULT_HTML_TEMPLATE_DIR + "/*.js"):
        shutil.copy2(fn, dest_dir)
    for fn in glob.glob(DEFAULT_HTML_TEMPLATE_DIR + "/*.css"):
        shutil.copy2(fn, dest_dir)

def _gen_html(cb_wcets):
    html_template = os.path.join(DEFAULT_HTML_TEMPLATE_DIR, "index.html")
    with io.open(html_template, encoding="utf-8") as _fp:
        template = Template(_fp.read())

    html_fn = os.path.join(DEFAULT_REPORT_DIR, "index.html")

    system_info = collect_system_info()
    html = template.render(cb_wcets=cb_wcets, system_info=system_info)
    logging.warning("Write %s", html_fn)
    with io.open(html_fn, "w", encoding="utf-8") as _fp:
        _fp.write(html)

def _gen_report_json(cb_wcets):
    output_filename = os.path.join(DEFAULT_REPORT_DIR, "report.json")
    logging.warning("Write %s", output_filename)
    jdata = [asdict(_) for _ in cb_wcets]
    with io.open(output_filename, "w", encoding="utf-8") as _fp:
        _fp.write(json.dumps(jdata, sort_keys=True))



@dataclass
class CallbackExecutionTimeMeasures:
    name: str = ""
    unit: str = "nanosecond"
    block_maxima: list = field(default_factory=list)
    measurements: list = field(default_factory=list) # measured execution time

    # shape, loc, scale are parameters regarding EVT
    gev_shape: float = 0
    gev_loc: float = 0
    gev_scale: float = 0

    def add_block_maxima(self, val):
        if val > 0:
            self.block_maxima.append(val)

    def add_measurements(self, measured_vals):
        self.measurements += [_ for _ in measured_vals if _ > 0]

    def _to_milliseconds(self):
        # When unit is nanosecond, block_maxima values are huge and can overflow when apply EVT.
        # Reduce the precision to ms to avoid this problem.
        if not self.block_maxima:
            logging.error("Unable to calculate extreme value for %s for empty block maxima",
                          self.name)
        if "nanosecond" in self.unit:
            self.block_maxima = [_ / 1e6 for _ in self.block_maxima]
            self.measurements = [_ / 1e6 for _ in self.measurements]
        elif "microsecond" in self.unit:
            self.block_maxima = [_ / 1e3 for _ in self.block_maxima]
            self.measurements = [_ / 1e3 for _ in self.measurements]
        elif "millisecond" in self.unit:
            pass
        elif "second" in self.unit:
            self.block_maxima = [_ * 1000 for _ in self.block_maxima]
            self.measurements = [_ * 1000 for _ in self.measurements]
        else:
            logging.error("Unable to handle unit %s", self.unit)
        self.unit = "millisecond"

    def fit_gev(self):
        if self.gev_shape != 0 or self.gev_loc != 0 or self.gev_scale != 0:
            logging.debug("did fit_gev() before, skip")
            return
        self._to_milliseconds()
        if self.block_maxima:
            self.gev_shape, self.gev_loc, self.gev_scale = genextreme.fit(data=self.block_maxima)

    def check(self):
        # If all values of block maxima is 0, a warning will be triggered:
        #   RuntimeWarning: invalid value encountered in double_scalars,...
        # Use this function to notify users for the validity of the data
        if sum(self.block_maxima) == 0:
            logging.warning("%s: all execution time samples are 0", self.name)
            return 1
        return 0


@dataclass
class CallbackWCET:
    name: str = ""
    num_blocks: int = 0
    num_execution_time_measurements: int = 0
    measurements_min_ms: float = 0
    measurements_avg_ms: float = 0
    measurements_max_ms: float = 0
    measurements_stdev: float = 0
    measurements_cv: float = 0  # stdev / mean

    block_maxima_min_ms: float = 0
    block_maxima_avg_ms: float = 0
    block_maxima_max_ms: float = 0
    block_maxima_stdev: float = 0
    block_maxima_cv: float = 0

    min_ms: float = 0
    max_ms: float = 0
    raw_is_iid: bool = False
    raw_gev_shape: float = 0
    raw_gev_loc: float = 0
    raw_gev_scale: float = 0
    raw_ppf_95: float = 0  # 95% extreme
    raw_ppf_99: float = 0
    raw_ppf_99_6: float = 0  # 99.6% extreme
    raw_ppf_99_9: float = 0
    raw_ppf_99_99: float = 0
    raw_ppf_99_999: float = 0  # 99.999%

    iesta_is_iid: bool = False
    iesta_gev_shape: float = 0
    iesta_gev_loc: float = 0
    iesta_gev_scale: float = 0
    iesta_ppf_95: float = 0
    iesta_ppf_99: float = 0
    iesta_ppf_99_6: float = 0
    iesta_ppf_99_9: float = 0
    iesta_ppf_99_99: float = 0
    iesta_ppf_99_999: float = 0

    # Kolmogorov-Smirnov test for goodness of fit.
    # eject the null hypothesis in favor of the alternative if the p-value is less than 0.05.
    # That is, if pvalue >= 0.05, the GEV fitness is good.
    kstest_pvalue: float = 0

    cv_png_filename: str = ""
    cdf_png_filename: str = ""
    gev_pdf_png_filename: str = ""
    pdf_png_filename: str = ""
    block_maxima_filename: str = ""
    execution_time_measurements_filename: str = ""

    def calc_ppfs(self, cb_et):
        self.raw_is_iid = is_iid(cb_et.block_maxima)
        self.raw_gev_shape = cb_et.gev_shape
        self.raw_gev_loc = cb_et.gev_loc
        self.raw_gev_scale = cb_et.gev_scale
        gev = genextreme(self.raw_gev_shape, self.raw_gev_loc, self.raw_gev_scale)
        self.raw_ppf_95 = gev.ppf(0.95)
        self.raw_ppf_99 = gev.ppf(0.99)
        self.raw_ppf_99_6 = gev.ppf(0.996)
        self.raw_ppf_99_9 = gev.ppf(0.999)
        self.raw_ppf_99_99 = gev.ppf(0.9999)
        self.raw_ppf_99_999 = gev.ppf(0.99999)

        if len(cb_et.block_maxima) >= 5:
            iesta_obj = IESTA(cb_et.block_maxima)
            self.iesta_gev_shape = iesta_obj.gev_params[0]
            self.iesta_gev_loc = iesta_obj.gev_params[1]
            self.iesta_gev_scale = iesta_obj.gev_params[2]
            self.iesta_ppf_95 = iesta_obj.ppf(0.95)
            self.iesta_ppf_99 = iesta_obj.ppf(0.99)
            self.iesta_ppf_99_6 = iesta_obj.ppf(0.996)
            self.iesta_ppf_99_9 = iesta_obj.ppf(0.999)
            self.iesta_ppf_99_99 = iesta_obj.ppf(0.9999)
            self.iesta_ppf_99_999 = iesta_obj.ppf(0.99999)
            self.iesta_is_iid = is_iid(iesta_obj.iesta_vals)
            self.kstest_pvalue = iesta_obj.kstest_pvalue

            return iesta_obj
        return None

    def get_wcet_ms_by_ppf_str(self, ppf_str):
        if ppf_str == "0.95":
            return self.iesta_ppf_95
        elif ppf_str == "0.99":
            return self.iesta_ppf_99
        elif ppf_str == "0.996":
            return self.iesta_ppf_99_6
        elif ppf_str == "0.999":
            return self.iesta_ppf_99_9
        elif ppf_str == "0.9999":
            return self.iesta_ppf_99_99
        elif ppf_str == "0.99999":
            return self.iesta_ppf_99_999
        raise ValueError(f"Invalid ppf_str: {ppf_str}")

def calc_wcet_ms_by_block_maxima(json_dir) -> list:
    """
    Load json files from |json_dir| and calculate WCET for each callback.

    Return:
    A list with CallbackWCET objects
    """
    if not os.path.isdir(json_dir):
        logging.error("No such directory: %s", json_dir)
        return {}
    cb_ets = _collect_callback_execution_time_measurements(json_dir)
    res = []

    for cb_name, cb_et in cb_ets.items():
        all_measurements_are_0 = cb_et.check()
        cb_wcet = CallbackWCET(name=cb_name,
                               num_blocks=len(cb_et.block_maxima),
                               num_execution_time_measurements=len(cb_et.measurements))
        res.append(cb_wcet)

        if all_measurements_are_0:
            continue
        cb_et.fit_gev()  # goes first as it normalizes samples to ms
        iesta_obj = cb_wcet.calc_ppfs(cb_et)

        if cb_et.measurements:
            cb_wcet.measurements_min_ms = min(cb_et.measurements)
            cb_wcet.measurements_avg_ms = sum(cb_et.measurements) / len(cb_et.measurements)
            cb_wcet.measurements_max_ms = max(cb_et.measurements)
        if len(cb_et.measurements) >= 2:
            cb_wcet.measurements_stdev = statistics.stdev(cb_et.measurements)
        if cb_wcet.measurements_avg_ms > 0:
            cb_wcet.measurements_cv = cb_wcet.measurements_stdev / cb_wcet.measurements_avg_ms

        if cb_et.block_maxima:
            cb_wcet.block_maxima_min_ms = min(cb_et.block_maxima)
            cb_wcet.block_maxima_max_ms = max(cb_et.block_maxima)
            cb_wcet.block_maxima_avg_ms = sum(cb_et.block_maxima) / cb_wcet.num_blocks
        if len(cb_et.block_maxima) >= 2:
            cb_wcet.block_maxima_stdev = statistics.stdev(cb_et.block_maxima)
        if cb_wcet.block_maxima_avg_ms > 0:
            cb_wcet.block_maxima_cv = cb_wcet.block_maxima_stdev / cb_wcet.block_maxima_avg_ms

        cb_wcet.block_maxima_filename = os.path.join(DEFAULT_CSV_DIR, sanitize_filename(f"{cb_name}.csv"))
        dest_fn = os.path.join(DEFAULT_REPORT_DIR, cb_wcet.block_maxima_filename)
        if iesta_obj:
            # When cb_et.block_maxima is not IID
            _export_block_maxima_and_iesta(cb_et.block_maxima, iesta_obj.iesta_vals, dest_fn)
        else:
            # When cb_et.block_maxima is IID, IESTA-adjusted data = cb_et.block_maxima
            _export_block_maxima_and_iesta(cb_et.block_maxima, cb_et.block_maxima, dest_fn)

        cb_wcet.execution_time_measurements_filename = os.path.join(DEFAULT_CSV_DIR, sanitize_filename(f"{cb_name}_measurements.csv"))
        dest_fn = os.path.join(DEFAULT_REPORT_DIR, cb_wcet.execution_time_measurements_filename)
        _export_execution_time_measurements(cb_et.measurements, dest_fn)

        cb_wcet.pdf_png_filename = os.path.join(DEFAULT_IMAGES_DIR, sanitize_filename(f"{cb_name}_pdf.png"))
        dest_fn = os.path.join(DEFAULT_REPORT_DIR, cb_wcet.pdf_png_filename)
        _plot_pdf(cb_name, cb_et.block_maxima, dest_fn, json_dir)

        cb_wcet.cdf_png_filename = os.path.join(DEFAULT_IMAGES_DIR, sanitize_filename(f"{cb_name}_cdf.png"))
        dest_fn = os.path.join(DEFAULT_REPORT_DIR, cb_wcet.cdf_png_filename)
        if iesta_obj:
            shape, loc, scale = iesta_obj.gev_params
        else:
            shape, loc, scale = cb_wcet.raw_gev_shape, cb_wcet.raw_gev_loc, cb_wcet.raw_gev_scale
        _plot_cdf(cb_name, cb_et.block_maxima, cb_et.measurements, shape, loc, scale, dest_fn)

        # plot GEV PDF
        cb_wcet.gev_pdf_png_filename = os.path.join(DEFAULT_IMAGES_DIR, sanitize_filename(f"{cb_name}_gev_pdf.png"))
        dest_fn = os.path.join(DEFAULT_REPORT_DIR, cb_wcet.gev_pdf_png_filename)
        _plot_gev_pdf(cb_name, shape, loc, scale, dest_fn)

        # plot CV curve
        cb_wcet.cv_png_filename = os.path.join(DEFAULT_IMAGES_DIR, sanitize_filename(f"{cb_name}_cv.png"))
        dest_fn = os.path.join(DEFAULT_REPORT_DIR, cb_wcet.cv_png_filename)
        #cv_mgr = CVManager(cb_et.measurements)
        #cv_mgr.plot(dest_fn)
        CVManager.plot_from_json(cb_name, json_dir, dest_fn)


    res.sort(key=lambda x: x.name)
#    for cb_wcet in res:
#        print(cb_wcet)
    return res


def gen_report(cb_wcets: list):
    """
    Given a list of CallbackWCET, generate the corresponding report
    """
    if not os.path.isdir(DEFAULT_REPORT_DIR):
        os.makedirs(DEFAULT_REPORT_DIR)
    copy_css_js(DEFAULT_REPORT_DIR)
    _gen_html(cb_wcets)
    _gen_report_json(cb_wcets)
