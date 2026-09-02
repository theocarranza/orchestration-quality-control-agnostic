import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from qc_lib import Blocked

import apply_author
import author_state
import checkpoint_state


class AuthorStateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name)
        self.state_dir = self.workspace / ".orchestration-qc" / "state"
        self.state_dir.mkdir(parents=True)
        self.preview = self.workspace / ".orchestration-qc" / "preview" / "run-1"
        self.preview.mkdir(parents=True)
        (self.preview / "ARCHITECTURE.md").write_text("# Architecture\n", encoding="utf-8")
        rules = self.preview / "rules"
        rules.mkdir()
        (rules / "rules-ship.md").write_text("- Do not skip approval.\n", encoding="utf-8")
        self.brief = {
            "schema_version": 1,
            "languages": ["python"],
            "package_managers": [],
            "layout": ["src"],
            "test_trees": [],
            "ci": [],
            "existing_orchestration": [],
            "existing_mechanism": [],
            "doc_language_hints": ["en"],
            "profile_hints": [],
            "readme_present": True,
            "manifests": [],
        }
        self.brief_path = self.workspace / "brief.json"
        self.brief_path.write_text(json.dumps(self.brief), encoding="utf-8")
        self.findings_path = self.workspace / "findings.json"
        self.findings_path.write_text("[]\n", encoding="utf-8")
        self.report_path = self.workspace / "report.txt"
        self.report_path.write_text("all passed\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _create_args(self, **overrides):
        values = {
            "workspace": str(self.workspace),
            "state_dir": str(self.state_dir),
            "run_id": "author-run",
            "profile": "core",
            "language": "en",
            "output_root": "orchestration",
            "brief_json": str(self.brief_path),
            "findings_json": str(self.findings_path),
            "preview_dir": str(self.preview),
            "report": str(self.report_path),
        }
        values.update(overrides)
        return Namespace(**values)

    def test_create_blocks_when_findings_exist(self):
        self.findings_path.write_text('[{"id":"x"}]\n', encoding="utf-8")
        with self.assertRaises(Blocked) as ctx:
            author_state.create(self._create_args())
        self.assertEqual(ctx.exception.reason_code, "qc_not_clean")

    def test_create_blocks_non_empty_output_root(self):
        dest = self.workspace / "orchestration"
        dest.mkdir()
        (dest / "stale.md").write_text("no\n", encoding="utf-8")
        with self.assertRaises(Blocked) as ctx:
            author_state.create(self._create_args())
        self.assertEqual(ctx.exception.reason_code, "destination_exists")

    def test_create_blocks_when_qc_run_is_pending(self):
        checkpoint_state.create(
            str(self.state_dir),
            "qc-run",
            ["workflows/workflows-x.md"],
            "core",
            "en",
            [{"id": "f1", "rule_id": "r", "location": {"path": "workflows/workflows-x.md", "anchor": "a"}, "suggested_change": {"before": "a", "after": "b"}}],
            "report",
        )
        with self.assertRaises(Blocked) as ctx:
            author_state.create(self._create_args())
        self.assertEqual(ctx.exception.reason_code, "concurrent_run_active")

    def test_create_stores_brief_and_preview(self):
        result = author_state.create(self._create_args())
        payload = json.loads(Path(result["checkpoint_path"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["run_type"], "author")
        self.assertEqual(payload["status"], "pending_approval")
        self.assertEqual(payload["workspace_brief"]["languages"], ["python"])
        self.assertEqual(payload["preview_files"]["ARCHITECTURE.md"], "# Architecture\n")
        self.assertEqual(payload["preview_files"]["rules/rules-ship.md"], "- Do not skip approval.\n")

    def test_decline_writes_nothing(self):
        result = author_state.create(self._create_args())
        path = Path(result["checkpoint_path"])
        author_state.decide(path, "decline")
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "aborted")
        self.assertFalse((self.workspace / "orchestration").exists())

    def test_apply_writes_preview_into_empty_output_root(self):
        result = author_state.create(self._create_args())
        path = Path(result["checkpoint_path"])
        author_state.decide(path, "approve")
        applied = apply_author.apply(self.workspace, path)
        self.assertEqual(applied["status"], "consumed")
        root = self.workspace / "orchestration"
        self.assertEqual((root / "ARCHITECTURE.md").read_text(encoding="utf-8"), "# Architecture\n")
        self.assertEqual((root / "rules" / "rules-ship.md").read_text(encoding="utf-8"), "- Do not skip approval.\n")

    def test_apply_blocks_without_approval(self):
        result = author_state.create(self._create_args())
        with self.assertRaises(Blocked) as ctx:
            apply_author.apply(self.workspace, Path(result["checkpoint_path"]))
        self.assertEqual(ctx.exception.reason_code, "invalid_decision")

    def test_apply_blocks_if_output_root_is_no_longer_empty(self):
        result = author_state.create(self._create_args())
        path = Path(result["checkpoint_path"])
        author_state.decide(path, "approve")
        dest = self.workspace / "orchestration"
        dest.mkdir()
        (dest / "collision.md").write_text("x\n", encoding="utf-8")
        with self.assertRaises(Blocked) as ctx:
            apply_author.apply(self.workspace, path)
        self.assertEqual(ctx.exception.reason_code, "destination_exists")


if __name__ == "__main__":
    unittest.main()
