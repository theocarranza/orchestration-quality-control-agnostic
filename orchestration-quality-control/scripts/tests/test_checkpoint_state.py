import json
import tempfile
import unittest
from pathlib import Path

from tests import SCRIPTS_DIR

import checkpoint_state
from qc_lib import Blocked


class CheckpointStateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state_dir = str(Path(self._tmp.name) / "state")

    def tearDown(self):
        self._tmp.cleanup()

    def _create(self, run_id="20260716-test-run", findings=None):
        findings = findings if findings is not None else [
            {
                "id": "W6-workflow-authoring-0123456789",
                "kind": "core/workflow-authoring",
                "rule": "rules-workflow-quality-control.md#W6",
                "location": {"path": "workflow.md", "section": "Steps"},
                "anchor": "some text",
                "violation": "missing validation step",
                "suggested_change": {"before": "some text", "after": "some fixed text"},
                "confidence": "high",
            }
        ]
        return checkpoint_state.create(
            self.state_dir, run_id, ["workflow.md"], "core", "en", findings, "a plain-language report",
        )

    def test_create_then_status_is_pending_approval(self):
        self._create()
        result = checkpoint_state.status(self.state_dir, "20260716-test-run")
        self.assertEqual(result["status"], "pending_approval")

    def test_status_absent_when_no_checkpoint(self):
        result = checkpoint_state.status(self.state_dir, "nonexistent-run")
        self.assertEqual(result["status"], "absent")

    def test_is_run_active_true_when_pending(self):
        self._create()
        result = checkpoint_state.is_run_active(self.state_dir)
        self.assertTrue(result["active"])
        self.assertEqual(result["run_id"], "20260716-test-run")

    def test_is_run_active_false_when_absent(self):
        result = checkpoint_state.is_run_active(self.state_dir)
        self.assertFalse(result["active"])

    def test_second_create_is_blocked_concurrent_run_active(self):
        self._create(run_id="20260716-first-run")
        with self.assertRaises(Blocked) as ctx:
            self._create(run_id="20260716-second-run")
        self.assertEqual(ctx.exception.reason_code, "concurrent_run_active")

    def test_consume_moves_to_consumed_and_deactivates(self):
        self._create()
        resolution = [{"finding_id": "W6-workflow-authoring-0123456789", "outcome": "applied"}]
        result = checkpoint_state.consume(self.state_dir, "20260716-test-run", resolution)
        self.assertEqual(result["status"], "consumed")
        self.assertFalse(checkpoint_state.is_run_active(self.state_dir)["active"])
        self.assertEqual(checkpoint_state.status(self.state_dir, "20260716-test-run")["status"], "consumed")

    def test_consume_without_reason_on_skip_is_blocked(self):
        self._create()
        resolution = [{"finding_id": "W6-workflow-authoring-0123456789", "outcome": "skipped"}]
        with self.assertRaises(Blocked) as ctx:
            checkpoint_state.consume(self.state_dir, "20260716-test-run", resolution)
        self.assertEqual(ctx.exception.reason_code, "malformed_checkpoint")

    def test_double_consume_is_blocked(self):
        self._create()
        resolution = [{"finding_id": "W6-workflow-authoring-0123456789", "outcome": "applied"}]
        checkpoint_state.consume(self.state_dir, "20260716-test-run", resolution)
        with self.assertRaises(Blocked) as ctx:
            checkpoint_state.consume(self.state_dir, "20260716-test-run", resolution)
        self.assertEqual(ctx.exception.reason_code, "checkpoint_already_consumed")

    def test_abort_moves_to_aborted(self):
        self._create()
        result = checkpoint_state.abort(self.state_dir, "20260716-test-run", "user declined all findings")
        self.assertEqual(result["status"], "aborted")
        self.assertFalse(checkpoint_state.is_run_active(self.state_dir)["active"])

    def test_abort_after_consume_is_blocked(self):
        self._create()
        resolution = [{"finding_id": "W6-workflow-authoring-0123456789", "outcome": "applied"}]
        checkpoint_state.consume(self.state_dir, "20260716-test-run", resolution)
        with self.assertRaises(Blocked) as ctx:
            checkpoint_state.abort(self.state_dir, "20260716-test-run", "too late")
        self.assertEqual(ctx.exception.reason_code, "checkpoint_already_consumed")

    def test_absent_is_terminal_no_marker_file_exists(self):
        # There is no marker file in this design at all — confirm nothing
        # except checkpoint-*.json is ever written under state_dir.
        self._create()
        resolution = [{"finding_id": "W6-workflow-authoring-0123456789", "outcome": "applied"}]
        checkpoint_state.consume(self.state_dir, "20260716-test-run", resolution)
        written = sorted(p.name for p in Path(self.state_dir).iterdir())
        self.assertEqual(written, ["checkpoint-20260716-test-run.json"])

    def test_checkpoint_filename_convention(self):
        result = self._create(run_id="20260716-my-slug")
        self.assertTrue(result["checkpoint_path"].endswith("checkpoint-20260716-my-slug.json"))

    def test_schema_version_is_2(self):
        self._create()
        path = Path(self.state_dir) / "checkpoint-20260716-test-run.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 2)


if __name__ == "__main__":
    unittest.main()
