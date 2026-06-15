# pylint: disable=invalid-name
import sys
import time
import unittest
import shlex

from system_info import collect_system_info


class SystemInfoTest(unittest.TestCase):
    def test_collect_system_info(self):
        info = collect_system_info()
        print(info)

if __name__ == "__main__":
    try:
        unittest.main()
    except KeyboardInterrupt:
        sys.exit(127)
