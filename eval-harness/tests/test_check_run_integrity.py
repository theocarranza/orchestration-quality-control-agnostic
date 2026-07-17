import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_run_integrity as integrity  # noqa: E402


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sandbox = Path(self.tmp.name) / "sandbox"
        self.sandbox.mkdir()
        (self.sandbox / "fixture.md").write_text("original content\n")

    def test_snapshot_hashes_every_file(self):
        hashes = integrity.snapshot(self.sandbox)
        self.assertIn("fixture.md", hashes)
        self.assertEqual(len(hashes["fixture.md"]), 64)

    def test_unedited_run_diffs_clean(self):
        baseline = integrity.snapshot(self.sandbox)
        current = integrity.snapshot(self.sandbox)
        result = integrity.diff_snapshots(baseline, current)
        self.assertTrue(result["unedited"])
        self.assertEqual(result["changed_files"], [])

    def test_edited_file_is_flagged(self):
        baseline = integrity.snapshot(self.sandbox)
        (self.sandbox / "fixture.md").write_text("edited content\n")
        current = integrity.snapshot(self.sandbox)
        result = integrity.diff_snapshots(baseline, current)
        self.assertFalse(result["unedited"])
        self.assertEqual(result["changed_files"], ["fixture.md"])

    def test_added_file_is_flagged(self):
        baseline = integrity.snapshot(self.sandbox)
        (self.sandbox / "new.md").write_text("new\n")
        current = integrity.snapshot(self.sandbox)
        result = integrity.diff_snapshots(baseline, current)
        self.assertFalse(result["unedited"])
        self.assertEqual(result["added_files"], ["new.md"])

    def test_ignored_prefix_does_not_count_as_edit(self):
        baseline = integrity.snapshot(self.sandbox)
        state_dir = self.sandbox / ".orchestration-qc" / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "checkpoint-1.json").write_text("{}\n")
        current = integrity.snapshot(self.sandbox)
        result = integrity.diff_snapshots(baseline, current, ignore_prefixes=[".orchestration-qc/"])
        self.assertTrue(result["unedited"])
        self.assertEqual(result["added_files"], [])

    def test_ignored_prefix_does_not_hide_real_edits(self):
        baseline = integrity.snapshot(self.sandbox)
        (self.sandbox / "fixture.md").write_text("edited\n")
        (self.sandbox / ".orchestration-qc").mkdir()
        (self.sandbox / ".orchestration-qc" / "marker.json").write_text("{}\n")
        current = integrity.snapshot(self.sandbox)
        result = integrity.diff_snapshots(baseline, current, ignore_prefixes=[".orchestration-qc/"])
        self.assertFalse(result["unedited"])
        self.assertEqual(result["changed_files"], ["fixture.md"])


class IsolationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sandbox = Path(self.tmp.name) / "sandbox"
        self.sandbox.mkdir()
        (self.sandbox / "fixture.md").write_text("content\n")

    def test_clean_transcript_passes(self):
        transcript = "Read fixture.md and found the issue described in fixture.md."
        result = integrity.check_isolation(transcript, self.sandbox, allow_prefixes=[])
        self.assertTrue(result["isolation_ok"])
        self.assertEqual(result["paths_outside_sandbox"], [])

    def test_unrelated_path_is_flagged(self):
        transcript = "Read fixture.md, then also opened other-project/secret-config.json for context."
        result = integrity.check_isolation(transcript, self.sandbox, allow_prefixes=[])
        self.assertFalse(result["isolation_ok"])
        self.assertIn("other-project/secret-config.json", result["paths_outside_sandbox"])

    def test_allowed_prefix_is_not_flagged(self):
        transcript = "Consulted orchestration-quality-control/references/rules/generator-quality-control.md for the rule text."
        result = integrity.check_isolation(
            transcript, self.sandbox, allow_prefixes=["orchestration-quality-control/"]
        )
        self.assertTrue(result["isolation_ok"])


class VerifyIntegrationTest(unittest.TestCase):
    def test_snapshot_then_verify_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sandbox = root / "sandbox"
            sandbox.mkdir()
            (sandbox / "fixture.md").write_text("content\n")

            baseline_path = root / "hashes.json"
            baseline_path.write_text(json.dumps(integrity.snapshot(sandbox)))

            transcript_path = root / "transcript.md"
            transcript_path.write_text("Read fixture.md. Did not edit it. Asked before applying.")

            current = integrity.snapshot(sandbox)
            baseline = json.loads(baseline_path.read_text())
            result = integrity.diff_snapshots(baseline, current)
            result.update(integrity.check_isolation(transcript_path.read_text(), sandbox, []))

            self.assertTrue(result["unedited"])
            self.assertTrue(result["isolation_ok"])


if __name__ == "__main__":
    unittest.main()
