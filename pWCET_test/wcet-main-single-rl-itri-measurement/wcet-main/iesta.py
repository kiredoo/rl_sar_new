"""
Adjust non-IID data so that we can apply EVT.

See the paper entitled by
    Valid Application of EVT in Timing Analysis by Randomising Execution Time Measurements
"""
import logging

import numpy as np
from scipy.stats import genextreme, kstest

from ljung_box import is_iid

_MAX_NUM_TRIALS = 30

class IESTA:
    """
    Use normal distribution N(0, sigma^2) to make original inputs to IID.
    The initial sigma is (max - min) / 10.
    Let diff = N(0, sigma^2); we keep increasing sigma if we cannot make |diff + vals| IID.
    """
    def __init__(self, vals):
        if len(vals) < 5:
            logging.error("Input array size should be >= 5, got %d", len(vals))

        self._org_vals = np.array(vals)
        self._iesta_vals = np.zeros_like(self._org_vals)
        self._gev = None
        self._gev_params = (0, 0, 0)  # (shape, loc, scale)
        self._iesta_eq_org = True
        self._kstest_pvalue = 0

        self._make_iid()
        self._make_gev()

    @property
    def gev_params(self):
        return self._gev_params

    @property
    def org_vals(self):
        return self._org_vals

    @property
    def iesta_vals(self):
        return self._iesta_vals

    @iesta_vals.setter
    def iesta_vals(self, _new_val):
        logging.debug("iesta_vals is private")
        pass

    @property
    def kstest_pvalue(self):
        return self._kstest_pvalue

    def _make_iid(self):
        """
        Generate _iesta_vals conform to IID.

        If _org_vals is already IID, then _iesta_vals = _org_vals
        """
        if len(self._org_vals) < 5:
            return
        iesta_vals = self._org_vals
        sigma = 0
        num_trials = 0
        while not is_iid(iesta_vals):
            if num_trials % _MAX_NUM_TRIALS == 0:
                sigma += (max(self._org_vals) - min(self._org_vals)) / 10
            num_trials += 1
            iesta_vals += np.random.normal(0, sigma, size=len(self._org_vals)) # N(0, sigma^2)
            self._iesta_eq_org = False
        self._iesta_vals = iesta_vals
        logging.info("IESTA: use sigma %f to get IID", sigma)

    def _make_gev(self):
        if len(self._org_vals) < 5:
            return
        self._gev_params = genextreme.fit(data=self._iesta_vals)
        self._gev = genextreme(*self._gev_params)
        _statistic, self._kstest_pvalue = kstest(self._iesta_vals, "genextreme", args=self._gev_params)

    def ppf(self, thresh):
        if self._gev:
            offset = 0 if self._iesta_eq_org else min(self._iesta_vals)
            return self._gev.ppf(thresh) - offset
        else:
            return float("-inf")
