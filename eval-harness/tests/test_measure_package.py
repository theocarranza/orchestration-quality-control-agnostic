import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import measure_package as pkg  # noqa: E402


class SyntheticFixtureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.package = Path(self.tmp.name) / "package"
        self.package.mkdir()

        self._create_fixture()

    def _create_fixture(self):
        pycache_dir = self.package / "__pycache__"
        pycache_dir.mkdir()
        (pycache_dir / "file.pyc").write_text("cached")

        tests_dir = self.package / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_something.py").write_text("import unittest\n")

        changelog = self.package / "CHANGELOG.md"
        changelog.write_text("# Changelog\n" + "line\n" * 100)

        readme = self.package / "README.md"
        readme.write_text("# README\n" + "line\n" * 50)

        doc = self.package / "docs.md"
        doc.write_text("# Docs\n" + "line\n" * 75)

        skill = self.package / "SKILL.md"
        skill.write_text("# Skill\n" + "line\n" * 25)

        adapters = self.package / "adapters"
        adapters.mkdir()

        host1_agents = adapters / "host1" / "agents"
        host1_agents.mkdir(parents=True)
        (host1_agents / "agent1.md").write_text("agent")
        (host1_agents / "agent2.py").write_text("pass")

        host2_agents = adapters / "host2" / "agents"
        host2_agents.mkdir(parents=True)
        (host2_agents / "agent3.md").write_text("agent")

        host2_extra_agents = adapters / "host2" / "extra" / "agents"
        host2_extra_agents.mkdir(parents=True)
        (host2_extra_agents / "deep_agent.md").write_text("should_not_be_counted")

        scripts = self.package / "scripts"
        scripts.mkdir()
        (scripts / "script1.py").write_text("pass")
        (scripts / "script2.py").write_text("pass")
        (scripts / "script3.py").write_text("pass")

        nested_scripts = scripts / "nested"
        nested_scripts.mkdir()
        (nested_scripts / "nested_script.py").write_text("pass")

        schemas = self.package / "schemas"
        schemas.mkdir()

        schema_with_enum = {
            "properties": {
                "operation": {
                    "enum": ["op1", "op2"]
                }
            }
        }
        (schemas / "input.schema.json").write_text(json.dumps(schema_with_enum))

        schema_with_const = {
            "oneOf": [
                {
                    "properties": {
                        "operation": {
                            "const": "op3"
                        }
                    }
                }
            ]
        }
        (schemas / "other-input.schema.json").write_text(json.dumps(schema_with_const))

        regular_files = self.package / "data"
        regular_files.mkdir()
        (regular_files / "file1.txt").write_text("data")
        (regular_files / "file2.json").write_text("{}")

    def test_synthetic_fixture_measures_correctly(self):
        metrics = pkg.measure(self.package)

        expected_files = 16
        expected_markdown_lines = 156
        expected_skill_lines = 26
        expected_agents = 3
        expected_scripts = 3
        expected_operations = 3

        self.assertEqual(metrics.files, expected_files)
        self.assertEqual(metrics.markdown_lines, expected_markdown_lines)
        self.assertEqual(metrics.skill_lines, expected_skill_lines)
        self.assertEqual(metrics.agents, expected_agents)
        self.assertEqual(metrics.scripts, expected_scripts)
        self.assertEqual(metrics.operations, expected_operations)

    def test_render_table_includes_all_metrics(self):
        metrics = pkg.PackageMetrics(
            files=10,
            markdown_lines=100,
            skill_lines=50,
            agents=5,
            scripts=3,
            operations=2,
        )
        table = pkg.render_table(metrics)

        self.assertIn("files", table)
        self.assertIn("markdown_lines", table)
        self.assertIn("skill_lines", table)
        self.assertIn("agents", table)
        self.assertIn("scripts", table)
        self.assertIn("operations", table)
        self.assertIn("10", table)
        self.assertIn("100", table)
        self.assertIn("50", table)
        self.assertIn("5", table)
        self.assertIn("3", table)
        self.assertIn("2", table)


class RealPackageTest(unittest.TestCase):
    def test_measure_real_package_smoke_test(self):
        repo_root = Path(__file__).resolve().parent.parent.parent
        real_package = repo_root / "orchestration-quality-control"

        if not real_package.exists():
            self.skipTest(f"Real package not found at {real_package}")

        metrics = pkg.measure(real_package)

        self.assertIsInstance(metrics, pkg.PackageMetrics)
        self.assertGreater(metrics.files, 0)
        self.assertGreater(metrics.markdown_lines, 0)
        self.assertGreater(metrics.skill_lines, 0)
        self.assertGreater(metrics.agents, 0)
        self.assertGreater(metrics.scripts, 0)
        self.assertGreater(metrics.operations, 0)


class MissingRootTest(unittest.TestCase):
    def test_missing_package_root_returns_1_and_writes_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            nonexistent = Path(tmp) / "nonexistent"

            stderr_capture = io.StringIO()
            stdout_capture = io.StringIO()

            with contextlib.redirect_stderr(stderr_capture), contextlib.redirect_stdout(stdout_capture):
                result = pkg.main(["--package-root", str(nonexistent)])

            self.assertEqual(result, 1)
            self.assertEqual(stdout_capture.getvalue(), "")
            self.assertNotEqual(stderr_capture.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
