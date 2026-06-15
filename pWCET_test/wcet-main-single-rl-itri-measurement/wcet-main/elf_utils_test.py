import unittest
import io
from elf_utils import is_elf, locate_callbacks, _get_opened_elf_filenames

class WCETUtilsTest(unittest.TestCase):
    def test_is_elf(self):
        self.assertTrue(is_elf("/usr/bin/bash"))
        self.assertFalse(is_elf("/etc/passwd"))

    @unittest.skip("Only works when autoware is running")
    def _test__get_opened_elf_filenames(self):
        elfs = _get_opened_elf_filenames()
        found = False
        for elf in elfs:
            if "ndt_scan_matcher" in elf:
                found = True
        self.assertTrue(found)

    def test_locate_func_in_elf(self):
        cbs = ["tilde_expand_word"]
        elfs = ["/bin/ls", "/usr/bin/bash"]
        res = locate_callbacks(cbs, elfs)
        self.assertEqual(res["tilde_expand_word"].fullpath, "/usr/bin/bash")

    def test_locate_func_with_undefined_func_in_elf(self):
        cbs = ["tilde_expand_word", "you_cannot_find_me"]
        elfs = ["/bin/ls", "/usr/bin/bash"]
        res = locate_callbacks(cbs, elfs)
        self.assertEqual(res["tilde_expand_word"].fullpath, "/usr/bin/bash")
        self.assertTrue("you_cannot_find_me" not in res)

    @unittest.skip("Takes a lot of time")
    def test_locate_func_in_elf_2(self):
        cbs = ["tilde_expand_word"]
        res = locate_callbacks(cbs)
        self.assertTrue(res["tilde_expand_word"].fullpath)

    @unittest.skip("Takes a lot of time and only valid when autoware is running")
    def test_locate_func_in_elf_3(self):
        with io.open("callbacks.txt", encoding="utf-8") as _fp:
            cbs = _fp.read().splitlines()
        res = locate_callbacks(cbs, elf_path_must_contain="autoware")
        for _cb in cbs:
            self.assertTrue(res[_cb].fullpath)



if __name__ == "__main__":
    unittest.main()
