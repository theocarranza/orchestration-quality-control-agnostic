import json
import tempfile
import unittest
from pathlib import Path

from qc_lib import Blocked

import discover_workspace
import gate_defaults
import plan_interview


class DiscoverWorkspaceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_blocks_missing_workspace(self):
        with self.assertRaises(Blocked) as ctx:
            discover_workspace.discover(self.workspace / "missing")
        self.assertEqual(ctx.exception.reason_code, "missing_target")

    def test_records_lockfiles_layout_tests_ci_and_manifests(self):
        (self.workspace / "package.json").write_text('{"name":"x"}\n', encoding="utf-8")
        (self.workspace / "package-lock.json").write_text("{}\n", encoding="utf-8")
        (self.workspace / "src").mkdir()
        (self.workspace / "e2e").mkdir()
        (self.workspace / "README.md").write_text("# Hello\n", encoding="utf-8")
        github = self.workspace / ".github" / "workflows"
        github.mkdir(parents=True)
        (github / "ci.yml").write_text("name: ci\n", encoding="utf-8")
        brief = discover_workspace.discover(self.workspace)
        self.assertIn("javascript", brief["languages"])
        self.assertIn("npm", brief["package_managers"])
        self.assertIn("src", brief["layout"])
        self.assertIn("e2e", brief["test_trees"])
        self.assertEqual(brief["ci"], [".github/workflows"])
        self.assertTrue(brief["readme_present"])
        self.assertEqual(brief["existing_orchestration"], [])
        self.assertEqual(brief["existing_mechanism"], [])
        self.assertEqual(brief["profile_hints"], [])

    def test_finds_orchestration_and_mechanism_markers(self):
        workflows = self.workspace / "workflows"
        workflows.mkdir()
        (workflows / "workflows-ship.md").write_text("# Workflow\n", encoding="utf-8")
        agents = self.workspace / ".claude" / "agents"
        agents.mkdir(parents=True)
        (agents / "worker.md").write_text("# agent\n", encoding="utf-8")
        brief = discover_workspace.discover(self.workspace)
        self.assertEqual(brief["existing_orchestration"], ["workflows/workflows-ship.md"])
        self.assertEqual(brief["existing_mechanism"], [".claude/agents"])

    def test_pipeline_yaml_hints_example_pipeline(self):
        (self.workspace / "build.pipeline.yaml").write_text("jobs: []\n", encoding="utf-8")
        brief = discover_workspace.discover(self.workspace)
        self.assertEqual(brief["profile_hints"], ["example-pipeline"])

    def test_pt_br_path_is_a_doc_language_hint(self):
        (self.workspace / "docs-pt-br").mkdir()
        brief = discover_workspace.discover(self.workspace)
        self.assertIn("pt-br", brief["doc_language_hints"])


class PlanInterviewTest(unittest.TestCase):
    def _brief(self, **overrides):
        base = {
            "languages": [],
            "package_managers": [],
            "layout": [],
            "test_trees": [],
            "ci": [],
            "existing_orchestration": [],
            "existing_mechanism": [],
            "doc_language_hints": ["en"],
            "profile_hints": [],
            "readme_present": False,
        }
        base.update(overrides)
        return base

    def test_never_asks_stack_layout_or_whether_tests_exist(self):
        plan = plan_interview.plan(self._brief(
            languages=["python"],
            layout=["src", "tests"],
            test_trees=["tests"],
        ))
        asked = set(plan["always_ask"]) | set(plan["ask"])
        self.assertNotIn("languages", asked)
        self.assertNotIn("layout", asked)
        self.assertNotIn("tests_exist", asked)
        self.assertEqual(plan["always_ask"], ["outcome"])
        self.assertEqual(plan["ask"], [])
        skipped = {item["field"]: item["value"] for item in plan["skip"]}
        self.assertEqual(skipped["language"], "en")
        self.assertEqual(skipped["profile"], "core")
        self.assertEqual(skipped["output_root"], "authored-orchestration")
        self.assertIsNone(plan["fork"])

    def test_does_not_fork_when_orchestration_exists(self):
        plan = plan_interview.plan(self._brief(
            existing_orchestration=["workflows/workflows-ship.md"],
        ))
        self.assertIsNone(plan["fork"])
        skipped = {item["field"]: item["value"] for item in plan["skip"]}
        self.assertEqual(skipped["intent"], "author")

    def test_packaged_profile_when_pipeline_artifacts_present(self):
        plan = plan_interview.plan(self._brief(profile_hints=["example-pipeline"]))
        skipped = {item["field"]: item["value"] for item in plan["skip"]}
        self.assertEqual(skipped["profile"], "example-pipeline")

    def test_defaults_confirmation_lists_packaged_fields(self):
        plan = plan_interview.plan(self._brief())
        confirmation = plan["defaults_confirmation"]
        self.assertEqual(confirmation["scope"], "author")
        self.assertIn("output_root", confirmation["fields"])
        self.assertNotIn("outcome", confirmation["fields"])


class GateDefaultsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_infer_validate_targets_from_orchestration(self):
        brief = {"existing_orchestration": ["workflows/a.md"], "existing_mechanism": []}
        targets = gate_defaults.infer_validate_targets(brief, workspace=self.workspace)
        self.assertEqual(targets, ["workflows/a.md"])

    def test_infer_validate_targets_from_workspace_defaults(self):
        config_dir = self.workspace / ".orchestration-qc"
        config_dir.mkdir(parents=True)
        (config_dir / "defaults.json").write_text(
            json.dumps({"validate": {"targets": ["rules/x.md"]}}),
            encoding="utf-8",
        )
        brief = {"existing_orchestration": [], "existing_mechanism": []}
        targets = gate_defaults.infer_validate_targets(brief, workspace=self.workspace)
        self.assertEqual(targets, ["rules/x.md"])

    def test_upgrade_fields_side_by_side_default(self):
        brief = {"existing_mechanism": [".claude/agents"], "profile_hints": [], "doc_language_hints": []}
        fields = gate_defaults.upgrade_fields(brief)
        self.assertEqual(fields["apply_mode"], "side-by-side")
        self.assertEqual(fields["decision"], "approve")
        self.assertEqual(fields["output_root"], "agents-oqc-next")


if __name__ == "__main__":
    unittest.main()
