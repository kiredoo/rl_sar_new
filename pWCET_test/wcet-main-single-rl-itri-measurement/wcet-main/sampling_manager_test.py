# pylint: disable=invalid-name
import shlex
import sys
import time
import unittest

from sampling_manager import (DEFAULT_AW_ROSBAG, DEFAULT_AW_cmd,
                              SamplingManager, do_aw_sampling,
                              wait_aw_fully_loaded)


def _wait_func(_log_fn):
    time.sleep(1)
    return 0

class SamplingManagerTest(unittest.TestCase):
    @unittest.skip("Takes a lot of time to finish, used only for debugging")
    def test_turtlesim(self):
        mgr = SamplingManager()
        mgr.ros2_launch_cmd = shlex.split("ros2 launch turtlesim multisim.launch.py")
        mgr.wait_ros2_proc_ready_func = _wait_func
        ret = mgr.sample_once()
        self.assertEqual(ret, 0)

    @unittest.skip("Takes a lot of time to finish, used only for debugging")
    def test_do_aw_sampling(self):
        do_aw_sampling(1, "callbacks.txt", 5, None)

    @unittest.skip("Takes a lot of time to finish, used only for debugging")
    def test_aw_behavior(self):
        mgr = SamplingManager(ros2_launch_cmd=DEFAULT_AW_cmd,
                              rosbag_fullpath=DEFAULT_AW_ROSBAG,
                              wait_ros2_func=wait_aw_fully_loaded)
        mgr.sample_many_times(1)

    @unittest.skip("Takes 130s to finish, used only for debugging")
    def test_itri_behavior(self):
        mgr = SamplingManager()

        mgr.ros2_launch_cmd = shlex.split("ros2 launch itri_launcher demo2.py")
        mgr.wait_ros2_proc_ready_func = lambda log_fn: time.sleep(3)

        mgr.sample_once()


if __name__ == "__main__":
    try:
        unittest.main()
    except KeyboardInterrupt:
        sys.exit(127)
