import tempfile
import unittest
from pathlib import Path

from tests import SCRIPTS_DIR

import render_diff
from qc_lib import Blocked


class RenderDiffTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, rel_path, content):
        path = self.workspace / rel_path
        path.write_text(content, encoding="utf-8")
        return rel_path

    def test_diff_is_literal_unified_diff(self):
        rel = self._write("workflow.md", "line one\nold text\nline three\n")
        result = render_diff.render(str(self.workspace), rel, "old text", "new text")
        self.assertIn("-old text", result["diff"])
        self.assertIn("+new text", result["diff"])
        self.assertEqual(result["updated_content"], "line one\nnew text\nline three\n")

    def test_before_not_found_is_blocked(self):
        rel = self._write("workflow.md", "line one\nline two\n")
        with self.assertRaises(Blocked) as ctx:
            render_diff.render(str(self.workspace), rel, "text that is not there", "new text")
        self.assertEqual(ctx.exception.reason_code, "anchor_not_found")

    def test_missing_target_is_blocked(self):
        with self.assertRaises(Blocked) as ctx:
            render_diff.render(str(self.workspace), "does-not-exist.md", "old", "new")
        self.assertEqual(ctx.exception.reason_code, "missing_target")

    def test_only_first_occurrence_replaced(self):
        rel = self._write("workflow.md", "dup\ndup\n")
        result = render_diff.render(str(self.workspace), rel, "dup", "fixed")
        self.assertEqual(result["updated_content"], "fixed\ndup\n")


if __name__ == "__main__":
    unittest.main()
