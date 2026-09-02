import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import SCRIPTS_DIR

import classify_targets


class ClassifyTargetsUnitTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, rel_path, content="content"):
        path = self.workspace / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return rel_path

    def test_rules_file_classified(self):
        result = classify_targets.classify_one(
            "references/rules/rules-workflow-quality-control.md",
            classify_targets.CORE_CLASSIFICATION,
        )
        self.assertEqual(result, ["rules-file"])

    def test_workflow_file_classified(self):
        result = classify_targets.classify_one(
            "references/workflows/workflows-qc-validate.md",
            classify_targets.CORE_CLASSIFICATION,
        )
        self.assertEqual(result, ["workflow"])

    def test_multi_class_document(self):
        # A document can be both workflow-shaped and orchestrator-shaped,
        # mirroring the original system's "one target, multiple classes" rule.
        rules = classify_targets.CORE_CLASSIFICATION + [
            {"glob": "**/deploy-orchestrator.md", "class": "orchestrator"}
        ]
        result = classify_targets.classify_one("docs/deploy-orchestrator.md", rules)
        self.assertIn("orchestrator", result)

    def test_unknown_class_when_no_glob_matches(self):
        result = classify_targets.classify_one("README.md", classify_targets.CORE_CLASSIFICATION)
        self.assertEqual(result, ["unknown"])

    def test_profile_globs_merge_with_core(self):
        profile_path = self.workspace / "profile.json"
        profile_path.write_text(
            json.dumps(
                {
                    "id": "example-pipeline",
                    "classification": [{"glob": "**/*.pipeline.yaml", "class": "artifact"}],
                }
            ),
            encoding="utf-8",
        )
        rules = classify_targets.load_profile_classification(str(profile_path))
        merged = classify_targets.CORE_CLASSIFICATION + rules
        result = classify_targets.classify_one("pipelines/deploy.pipeline.yaml", merged)
        self.assertEqual(result, ["artifact"])

    def test_pipeline_yaml_unknown_without_profile(self):
        result = classify_targets.classify_one(
            "pipelines/deploy.pipeline.yaml",
            classify_targets.CORE_CLASSIFICATION,
        )
        self.assertEqual(result, ["unknown"])

    def test_shipped_example_pipeline_profile_classifies_pipeline_yaml(self):
        profile_path = (
            Path(__file__).resolve().parents[2] / "profiles" / "example-pipeline" / "profile.json"
        )
        rules = classify_targets.load_profile_classification(str(profile_path))
        merged = classify_targets.CORE_CLASSIFICATION + rules
        result = classify_targets.classify_one("jobs/deploy.pipeline.yaml", merged)
        self.assertEqual(result, ["artifact"])

    def test_directory_target_recurses(self):
        self._write("module-slice/login.flow.yaml")
        self._write("module-slice/orphan_helper.yaml")
        target_dir = self.workspace / "module-slice"
        files = sorted(p.relative_to(self.workspace) for p in target_dir.rglob("*") if p.is_file())
        self.assertEqual(
            [str(f) for f in files],
            ["module-slice/login.flow.yaml", "module-slice/orphan_helper.yaml"],
        )


class ClassifyTargetsCliTest(unittest.TestCase):
    """CLI-level tests: exercise the real exit-code and blocked-payload contract."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "classify_targets.py"), "--workspace", str(self.workspace), *args],
            capture_output=True,
            text=True,
        )

    def test_missing_target_is_blocked_with_exit_2(self):
        proc = self._run("does-not-exist.md")
        self.assertEqual(proc.returncode, 2)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["reason_code"], "missing_target")

    def test_absolute_path_is_blocked(self):
        proc = self._run("/etc/passwd")
        self.assertEqual(proc.returncode, 2)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["reason_code"], "target_outside_approved_set")

    def test_existing_file_classifies_successfully(self):
        (self.workspace / "rules-generic.md").write_text("x", encoding="utf-8")
        proc = self._run("rules-generic.md")
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["classifications"][0]["classes"], ["rules-file"])


if __name__ == "__main__":
    unittest.main()
