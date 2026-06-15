# pylint: disable=invalid-name
import unittest
import sys
from os_utils import sanitize_filename, desanitize_filename


class OSUtilsTest(unittest.TestCase):
    def test_sanitize_filename(self):
        name = "behavior_path_planner::BehaviorPathPlannerNode::onAcceleration"
        res = sanitize_filename(name)
        self.assertTrue(":" not in res)
        self.assertEqual(desanitize_filename(res), name)

        name = "/etc/issue.net"
        res = sanitize_filename(name)
        self.assertEqual(res, name)
        self.assertEqual(desanitize_filename(res), name)

if __name__ == "__main__":
    try:
        unittest.main()
    except KeyboardInterrupt:
        sys.exit(127)
