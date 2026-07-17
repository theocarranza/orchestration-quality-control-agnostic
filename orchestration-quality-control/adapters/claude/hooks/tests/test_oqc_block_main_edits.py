import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "oqc-block-main-edits.py"


class BlockMainEditsHookTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name)
        self.state_dir = self.workspace / ".orchestration-qc" / "state"
        self.state_dir.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_checkpoint(self, run_id="20260716-test", status="pending_approval", targets=None):
        checkpoint = {
            "schema_version": 2,
            "run_id": run_id,
            "status": status,
            "targets": targets if targets is not None else ["workflow.md"],
            "profile": "core",
            "language": "en",
            "findings": [],
            "plain_language_report": "",
            "created_at": "1970-01-01T00:00:00Z",
        }
        path = self.state_dir / f"checkpoint-{run_id}.json"
        path.write_text(json.dumps(checkpoint), encoding="utf-8")
        return path

    def _run_hook(self, tool_name, file_path):
        payload = {
            "tool_name": tool_name,
            "tool_input": {"file_path": file_path},
            "cwd": str(self.workspace),
        }
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
        )

    def test_allows_edit_when_no_run_active(self):
        proc = self._run_hook("Edit", str(self.workspace / "workflow.md"))
        self.assertEqual(proc.returncode, 0)

    def test_blocks_edit_on_active_target(self):
        self._write_checkpoint(targets=["workflow.md"])
        proc = self._run_hook("Edit", str(self.workspace / "workflow.md"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("20260716-test", proc.stderr)

    def test_blocks_write_on_active_target(self):
        self._write_checkpoint(targets=["workflow.md"])
        proc = self._run_hook("Write", str(self.workspace / "workflow.md"))
        self.assertEqual(proc.returncode, 2)

    def test_allows_edit_on_file_outside_checkpoint_targets(self):
        self._write_checkpoint(targets=["workflow.md"])
        proc = self._run_hook("Edit", str(self.workspace / "unrelated.md"))
        self.assertEqual(proc.returncode, 0)

    def test_allows_non_edit_tools_unconditionally(self):
        self._write_checkpoint(targets=["workflow.md"])
        proc = self._run_hook("Read", str(self.workspace / "workflow.md"))
        self.assertEqual(proc.returncode, 0)

    def test_consumed_checkpoint_no_longer_blocks(self):
        self._write_checkpoint(status="consumed", targets=["workflow.md"])
        proc = self._run_hook("Edit", str(self.workspace / "workflow.md"))
        self.assertEqual(proc.returncode, 0)

    def test_aborted_checkpoint_no_longer_blocks(self):
        self._write_checkpoint(status="aborted", targets=["workflow.md"])
        proc = self._run_hook("Edit", str(self.workspace / "workflow.md"))
        self.assertEqual(proc.returncode, 0)

    def test_malformed_stdin_fails_open(self):
        proc = subprocess.run(
            [sys.executable, str(HOOK)],
            input="not json",
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
