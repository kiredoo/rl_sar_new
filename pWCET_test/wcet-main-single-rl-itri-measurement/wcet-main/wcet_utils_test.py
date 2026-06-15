# pylint: disable=invalid-name
import io
import os
import unittest

from scipy.stats import genextreme, kstest

from wcet_utils import calc_wcet_ms_by_block_maxima


class WCETUtilsTest(unittest.TestCase):
    def test_kstest(self):
        cur_dir = os.path.dirname(os.path.realpath(__file__))
        txt_fn = os.path.join(cur_dir, "test_data", "NDTScanMatcher_callback_sensor_points_block_maximas.txt")
        with io.open(txt_fn) as _fp:
            bm_vals = [float(line.strip()) for line in _fp.read().splitlines()]
        self.assertEqual(len(bm_vals), 758)
        shape, loc, scale = 0.0533089804, 41.0852747974, 8.9800295008
        res = kstest(bm_vals, "genextreme", args=(shape, loc, scale))
        self.assertTrue(res.pvalue < 0.05) # < 0.05: reject the null hypothesis that bm_vals are distributed as GEV


    def _test_calc_wcet(self):
        cur_dir = os.path.dirname(os.path.realpath(__file__))
        json_dir = os.path.join(cur_dir, "sampled_execution_time")
        if os.path.isdir(json_dir):
            res = calc_wcet_ms_by_block_maxima(json_dir)
            for cb_wcet in res:
                print(cb_wcet)


if __name__ == "__main__":
    unittest.main()
