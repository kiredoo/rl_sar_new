# pylint: disable=invalid-name
import sys
import time
import unittest

import psutil

from proc_manager import ProcManager


def wait_until(predicate, timeout=5.0, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class ProcManagerTest(unittest.TestCase):
    def test_start_stop_sleep_process(self):
        mgr = ProcManager([sys.executable, "-c", "import time; time.sleep(60)"], silent=True)
        self.addCleanup(lambda: mgr.stop())

        self.assertFalse(mgr.is_alive())
        mgr.start()
        self.assertTrue(wait_until(mgr.is_alive, timeout=1.0))
        mgr.stop()
        self.assertFalse(mgr.is_alive())
        self.assertIsNone(mgr.pid)

    def test_natural_exit_updates_is_alive(self):
        mgr = ProcManager([sys.executable, "-c", "import time; time.sleep(1.0)"], silent=True)
        self.addCleanup(lambda: mgr.stop())

        mgr.start()
        self.assertTrue(wait_until(mgr.is_alive, timeout=1.0))
        self.assertTrue(wait_until(lambda: not mgr.is_alive(), timeout=8.0))
        mgr.stop()
        self.assertFalse(mgr.is_alive())

    def test_stop_is_idempotent(self):
        mgr = ProcManager([sys.executable, "-c", "import time; time.sleep(60)"], silent=True)
        self.addCleanup(lambda: mgr.stop())

        mgr.start()
        self.assertTrue(wait_until(mgr.is_alive, timeout=1.0))
        mgr.stop()
        mgr.stop()
        self.assertFalse(mgr.is_alive())

    def test_stop_kills_child_process_tree(self):
        code = (
            "import subprocess, sys, time; "
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
            "print(child.pid, flush=True); "
            "time.sleep(60)"
        )
        mgr = ProcManager([sys.executable, "-c", code], silent=True)
        self.addCleanup(lambda: mgr.stop())

        mgr.start()
        self.assertTrue(wait_until(mgr.is_alive, timeout=1.0))

        child_pids = []

        def has_child():
            try:
                parent = psutil.Process(mgr.pid)
                children = parent.children(recursive=True)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return False
            child_pids[:] = [child.pid for child in children]
            return len(child_pids) >= 1

        self.assertTrue(wait_until(has_child, timeout=5.0))

        mgr.stop()
        self.assertFalse(mgr.is_alive())
        self.assertTrue(wait_until(lambda: all(not psutil.pid_exists(pid) for pid in child_pids), timeout=5.0))


if __name__ == "__main__":
    unittest.main()
