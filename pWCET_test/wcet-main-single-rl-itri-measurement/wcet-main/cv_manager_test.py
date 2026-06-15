# pylint: disable=invalid-name
import sys
import unittest

from cv_manager import CVManager


class CVManagerTest(unittest.TestCase):
    def test_cv_manager(self):
        mgr = CVManager()

        for val in range(1, 7):
            mgr.add(val)
        self.assertEqual(len(mgr.cvs), 6)
        gts = [0, 0.3333333333333333, 0.408248290463863,
               0.447213595499958, 0.47140452079103173, 0.48795003647426655]
        for actual, gt in zip(mgr.cvs, gts):
            self.assertTrue(abs(actual - gt) < 1e-9)

    def test_cv_manager2(self):
        mgr = CVManager(list(range(1, 7)))
        self.assertEqual(len(mgr.cvs), 6)
        gts = [0, 0.3333333333333333, 0.408248290463863,
               0.447213595499958, 0.47140452079103173, 0.48795003647426655]
        for actual, gt in zip(mgr.cvs, gts):
            self.assertTrue(abs(actual - gt) < 1e-9)

    def test_cv_plot(self):
        mgr = CVManager(list(range(1, 100)))
        mgr.plot("/tmp/cv.png")


if __name__ == "__main__":
    try:
        unittest.main()
    except KeyboardInterrupt:
        sys.exit(127)
