# pylint: disable=invalid-name
import unittest
import sys
import os
import io
import random
from scipy.stats import genextreme

from iesta import IESTA
from ljung_box import is_iid

class IESTATest(unittest.TestCase):
    def test_iesta_need_to_make_iid(self):
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        fn = os.path.join(cur_dir, "non_iid_samples.txt")
        vals = []
        with io.open(fn, encoding="utf-8") as _fp:
            for line in _fp.read().splitlines():
                vals.append(float(line))

        obj = IESTA(vals)
        self.assertTrue(obj.ppf(0.99) > sum(vals) / len(vals))
        gev = genextreme(*obj.gev_params)
        self.assertTrue(gev.ppf(0.99) != obj.ppf(0.99))

    def test_iesta_no_need_to_make_iid(self):
        vals = [random.randint(1, 6) for _ in range(30)]
        while not is_iid(vals):
            vals = [random.randint(1, 6) for _ in range(30)]
        obj = IESTA(vals)
        for idx, org in enumerate(obj.org_vals):
            self.assertEqual(org, obj.iesta_vals[idx])

        gev = genextreme(*obj.gev_params)
        self.assertEqual(gev.ppf(0.99), obj.ppf(0.99))

    def test_iesta_insufficient_data(self):
        vals = list(range(4))
        obj = IESTA(vals)
        self.assertEqual(obj.ppf(0.5), float("-inf"))

if __name__ == "__main__":
    try:
        unittest.main()
    except KeyboardInterrupt:
        sys.exit(127)
