import json
import tempfile
import unittest
from pathlib import Path

from qc_lib import Blocked

import discover_workspace
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
    def test_never_asks_stack_layout_or_whether_tests_exist(self):
        plan = plan_interview.plan({
            "languages": ["python"],
            "package_managers": [],
            "layout": ["src", "tests"],
            "test_trees": ["tests"],
            "ci": [],
            "existing_orchestration": [],
            "existing_mechanism": [],
            "doc_language_hints": ["en"],
            "profile_hints": [],
            "readme_present": True,
        })
        asked = set(plan["always_ask"]) | set(plan["ask"])
        self.assertNotIn("languages", asked)
        self.assertNotIn("layout", asked)
        self.assertNotIn("tests_exist", asked)
        self.assertIn("outcome", plan["always_ask"])
        self.assertIn("output_root", plan["always_ask"])
        skipped = {item["field"]: item["value"] for item in plan["skip"]}
        self.assertEqual(skipped["language"], "en")
        self.assertEqual(skipped["profile"], "core")
        self.assertIsNone(plan["fork"])

    def test_forks_when_orchestration_exists(self):
        plan = plan_interview.plan({
            "languages": [],
            "package_managers": [],
            "layout": [],
            "test_trees": [],
            "ci": [],
            "existing_orchestration": ["workflows/workflows-ship.md"],
            "existing_mechanism": [],
            "doc_language_hints": [],
            "profile_hints": [],
            "readme_present": False,
        })
        self.assertEqual(plan["fork"], "author_vs_upgrade")

    def test_asks_profile_when_pipeline_artifacts_present(self):
        plan = plan_interview.plan({
            "languages": [],
            "package_managers": [],
            "layout": [],
            "test_trees": [],
            "ci": [],
            "existing_orchestration": [],
            "existing_mechanism": [],
            "doc_language_hints": [],
            "profile_hints": ["example-pipeline"],
            "readme_present": False,
        })
        self.assertIn("profile", plan["ask"])
        self.assertNotIn("profile", {item["field"] for item in plan["skip"]})

    def test_asks_whether_outcome_involves_e2e_tree(self):
        plan = plan_interview.plan({
            "languages": [],
            "package_managers": [],
            "layout": ["e2e"],
            "test_trees": ["e2e"],
            "ci": [],
            "existing_orchestration": [],
            "existing_mechanism": [],
            "doc_language_hints": [],
            "profile_hints": [],
            "readme_present": False,
        })
        self.assertIn("outcome_involves_test_tree", plan["ask"])


if __name__ == "__main__":
    unittest.main()
