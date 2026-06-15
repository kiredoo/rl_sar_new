"""
Calculate mean, stdev, and CV (=stdev/mean) in an efficient way.
"""
import os
import io
import json
import logging

import matplotlib.pyplot as plt
import numpy as np

from wcet_consts import DEFAULT_FIG_SIZE


class CVManager:
    def __init__(self, vals=None):
        self.cvs = []
        self._sum = 0            # x₁ + x₂ + … + xₙ
        self.square_sum = 0      # x₁² + x₂² + … + xₙ²
        self._mean = 0
        self._stdev = 0
        self._num_samples = 0

        if vals is not None:
            for val in vals:
                if val > 0:
                    self.add(val)

    def add(self, val):
        self._num_samples += 1
        self.square_sum += val * val
        self._sum += val

        self._mean = self._sum / self._num_samples

        variance = (
            self.square_sum
            - 2 * self._mean * self._sum
            + self._num_samples * (self._mean * self._mean)
        ) / self._num_samples

        if variance < 0:
            variance = 0.0

        self._stdev = variance**0.5

        if self._mean != 0:
            cv = self._stdev / self._mean
            self.cvs.append(cv)
        else:
            self.cvs.append(0)

    def plot(self, output_fn=None, label="CV Curve"):
        if not self.cvs:
            logging.warning("No CV data")
            return 1

        plt.figure(figsize=DEFAULT_FIG_SIZE)
        series = range(1, len(self.cvs) + 1)

        plt.plot(series, self.cvs, marker="o", color="b", label=label)
        plt.axhline(y=1, color="r", linestyle="--", label="CV = 1")

        plt.xlabel("Samples")
        plt.ylabel("CV")
        plt.legend(fontsize=8, loc="upper right", framealpha=0.8)
        plt.grid(True)
        plt.text(
            0.05, 0.95,
            f"mean = {self._mean:.2f}",
            fontsize=10,
            verticalalignment="top",
            bbox=dict(facecolor="yellow", alpha=0.7)
        )

        if output_fn:
            logging.warning("Save %s", output_fn)
            plt.savefig(output_fn)
        else:
            plt.show()
        plt.close()
        return 0

    @staticmethod
    def _get_json_filenames(json_dir):
        if not os.path.isdir(json_dir):
            return []
        res = []
        for fname in os.listdir(json_dir):
            if not fname.endswith(".json"):
                continue
            if len(fname) == 19 and fname[:-5].isdigit():
                res.append(os.path.join(json_dir, fname))
        return sorted(res)


    @staticmethod
    def _load_callback_samples_from_json(json_filename, target_callback):
        if not os.path.isfile(json_filename):
            return np.array([], dtype=float)

        with io.open(json_filename, "r", encoding="utf-8") as fp:
            data = json.loads(fp.read())

        unit = data.get("unit", "unknown_unit")
        samples = []
        for cb in data.get("callbacks", []):
            if cb.get("name", "") == target_callback:
                samples = cb.get("samples", [])
                break

        if not samples:
            return np.array([], dtype=float)

        if "nanosecond" in unit:
            conv = 1e-6    # ns → ms
        elif "microsecond" in unit:
            conv = 1e-3    # µs → ms
        elif "millisecond" in unit:
            conv = 1.0     # ms
        elif "second" in unit:
            conv = 1000.0  # s → ms
        else:
            conv = 1.0

        arr = np.array(samples, dtype=float) * conv
        arr = arr[arr > 0]
        return arr


    @staticmethod
    def plot_from_json(callback_name: str, json_dir: str, output_png: str):
        all_jsons = CVManager._get_json_filenames(json_dir)
        if not all_jsons:
            print(f"warning：in '{json_dir}' no YYYYMMDDhhmmss.json file")
            return

        valid_jsons = []
        for jfn in all_jsons:
            arr = CVManager._load_callback_samples_from_json(jfn, callback_name)
            if arr.size > 0:
                valid_jsons.append(jfn)

        num_valid = len(valid_jsons)
        if num_valid == 0:
            print(f"warning：in JSON no callback '{callback_name}'")
            return

        cmap = plt.get_cmap("turbo")

        plt.figure(figsize=DEFAULT_FIG_SIZE)
        plt.axhline(y=1.0, color="r", linestyle="--", linewidth=1)

        for idx_valid, jfn in enumerate(valid_jsons):
            arr = CVManager._load_callback_samples_from_json(jfn, callback_name)
            cv_mgr = CVManager(arr)
            cvs = cv_mgr.cvs
            x_vals = range(1, len(cvs) + 1)

            color = cmap(idx_valid / max(1, num_valid - 1))

            plt.plot(x_vals, cvs, color=color, linewidth=1)

        plt.xlabel("Samples")
        plt.ylabel("CV")
        plt.grid(True)

        sm = plt.cm.ScalarMappable(
            cmap=cmap,
            norm=plt.Normalize(vmin=0, vmax=num_valid - 1)
        )
        sm.set_array([])
        cbar = plt.colorbar(sm)

        ticks = [0, (num_valid-1)//2, num_valid-1]
        cbar.set_ticks(ticks)
        cbar.set_ticklabels([str(t) for t in ticks])
        cbar.set_label("index")

        plt.legend(["CV = 1"], fontsize=8, loc="upper right", framealpha=0.8)

        out_dir = os.path.dirname(output_png)
        if out_dir and not os.path.isdir(out_dir):
            os.makedirs(out_dir)

        plt.savefig(output_png)
        plt.close()
        print(f"save image in：{output_png}")