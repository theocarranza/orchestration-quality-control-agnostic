import unittest

from tests import SCRIPTS_DIR

import qc_lib
from qc_lib import Blocked


class NormalizeTextTest(unittest.TestCase):
    def test_trailing_whitespace_stripped_per_line(self):
        self.assertEqual(qc_lib.normalize_text("hello   \nworld  "), "hello\nworld")

    def test_internal_whitespace_collapsed(self):
        self.assertEqual(qc_lib.normalize_text("a    b"), "a b")

    def test_blank_line_runs_collapsed(self):
        self.assertEqual(qc_lib.normalize_text("a\n\n\n\nb"), "a\n\nb")

    def test_unicode_nfc_normalized(self):
        # 'e' + combining acute (NFD) should normalize the same as precomposed é (NFC)
        nfd = "é"
        nfc = "é"
        self.assertEqual(qc_lib.normalize_text(nfd), qc_lib.normalize_text(nfc))


class NormalizePathTest(unittest.TestCase):
    def test_relative_path_accepted(self):
        self.assertEqual(qc_lib.normalize_path("references/rules/x.md", stage="test"), "references/rules/x.md")

    def test_absolute_path_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            qc_lib.normalize_path("/etc/passwd", stage="test")
        self.assertEqual(ctx.exception.reason_code, "target_outside_approved_set")

    def test_parent_traversal_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            qc_lib.normalize_path("../../etc/passwd", stage="test")
        self.assertEqual(ctx.exception.reason_code, "target_outside_approved_set")

    def test_backslash_path_normalized_to_forward_slash(self):
        self.assertEqual(qc_lib.normalize_path("a\\b\\c.md", stage="test"), "a/b/c.md")


if __name__ == "__main__":
    unittest.main()
