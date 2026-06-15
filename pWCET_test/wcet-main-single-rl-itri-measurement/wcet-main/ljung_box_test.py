import random
import unittest

from ljung_box import is_iid


class LjungBoxTest(unittest.TestCase):
    def test_corner_case(self):
        for nelem in range(5):
            vals = list(range(nelem))
            self.assertFalse(is_iid(vals))

    def test_is_iid(self):
        vals = [_ % 6 for _ in range(100)]
        self.assertFalse(is_iid(vals))

        # simulate dice rolls. the following method does not always get IID,
        # so use a counter to verify ljung_box
        num_iid = 0
        for _ in range(100):
            vals = [random.randint(0, 5) for _ in range(1000)]
            if is_iid(vals):
                num_iid += 1
        self.assertTrue(num_iid > 75)


if __name__ == "__main__":
    unittest.main()
