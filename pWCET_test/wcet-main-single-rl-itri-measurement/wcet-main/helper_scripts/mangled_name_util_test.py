import unittest

from mangled_name_util import (demangle, does_arg_contain_msg,
                               get_func_argument_by_mangled_name)


class MangledNameUtilTest(unittest.TestCase):
    def test_demangle(self):
        mangled_name = "_ZN8autoware16ndt_scan_matcher14NDTScanMatcher27callback_sensor_points_mainESt10shared_ptrIKN11sensor_msgs3msg12PointCloud2_ISaIvEEEE"

        self.assertEqual(demangle(mangled_name),
            "autoware::ndt_scan_matcher::NDTScanMatcher::callback_sensor_points_main")


    def test_get_func_argument_by_mangled_name(self):
        mangled_name = "_ZN8autoware16ndt_scan_matcher14NDTScanMatcher27callback_sensor_points_mainESt10shared_ptrIKN11sensor_msgs3msg12PointCloud2_ISaIvEEEE"
        self.assertEqual(get_func_argument_by_mangled_name(mangled_name),
            "std::shared_ptr<sensor_msgs::msg::PointCloud2_<std::allocator<void> > const>")

    def test_does_arg_contain_msg(self):
        mangled_name = "_ZN8autoware16ndt_scan_matcher14NDTScanMatcher27callback_sensor_points_mainESt10shared_ptrIKN11sensor_msgs3msg12PointCloud2_ISaIvEEEE"
        self.assertTrue(does_arg_contain_msg(mangled_name))

        mangled_name = "_ZN6pclomp31calculate_weighted_mean_and_covERKSt6vectorIN5Eigen6MatrixIdLi2ELi1ELi0ELi2ELi1EEESaIS3_EERKS0_IdSaIdEE"
        self.assertFalse(does_arg_contain_msg(mangled_name))

if __name__ == "__main__":
    unittest.main()
