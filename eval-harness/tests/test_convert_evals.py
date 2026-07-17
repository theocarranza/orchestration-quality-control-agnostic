import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import convert_evals  # noqa: E402


class SlugifyTest(unittest.TestCase):
    def test_file_fixture(self):
        self.assertEqual(convert_evals.slugify(["fixtures/deploy-orchestrator.md"]), "deploy-orchestrator")

    def test_directory_fixture_trailing_slash(self):
        self.assertEqual(convert_evals.slugify(["fixtures/module-slice/"]), "module-slice")

    def test_yaml_fixture(self):
        self.assertEqual(convert_evals.slugify(["fixtures/flow-with-inline-env.yaml"]), "flow-with-inline-env")


class ConvertTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

        evals_dir = self.root / "evals"
        fixtures_dir = evals_dir / "fixtures"
        fixtures_dir.mkdir(parents=True)
        (fixtures_dir / "sample-one.md").write_text("first fixture\n")

        module_dir = fixtures_dir / "module-slice"
        module_dir.mkdir()
        (module_dir / "a.md").write_text("a\n")
        (module_dir / "b.md").write_text("b\n")

        self.evals_json = evals_dir / "evals.json"
        self.evals_json.write_text(json.dumps({
            "skill_name": "example",
            "evals": [
                {
                    "id": 1,
                    "prompt": "Check this file.",
                    "files": ["fixtures/sample-one.md"],
                    "assertions": [{"id": "a1", "text": "Flags the issue"}],
                },
                {
                    "id": 2,
                    "prompt": "Check this folder.",
                    "files": ["fixtures/module-slice/"],
                    "assertions": [{"id": "a1", "text": "Treats folder as target"}],
                },
            ],
        }))

    def test_stages_file_fixture_and_metadata(self):
        workspace = self.root / "workspace"
        eval_dirs = convert_evals.convert(self.evals_json, workspace)

        file_eval_dir = workspace / "eval-sample-one"
        self.assertIn(file_eval_dir, eval_dirs)
        self.assertTrue((file_eval_dir / "sandbox" / "sample-one.md").exists())

        metadata = json.loads((file_eval_dir / "eval_metadata.json").read_text())
        self.assertEqual(metadata["eval_id"], 1)
        self.assertEqual(metadata["eval_name"], "sample-one")
        self.assertEqual(metadata["assertions"], ["Flags the issue"])

    def test_stages_directory_fixture(self):
        workspace = self.root / "workspace"
        convert_evals.convert(self.evals_json, workspace)

        dir_eval_dir = workspace / "eval-module-slice"
        self.assertTrue((dir_eval_dir / "sandbox" / "module-slice" / "a.md").exists())
        self.assertTrue((dir_eval_dir / "sandbox" / "module-slice" / "b.md").exists())

    def test_does_not_modify_source_fixtures(self):
        workspace = self.root / "workspace"
        original = (self.evals_json.parent / "fixtures" / "sample-one.md").read_text()
        convert_evals.convert(self.evals_json, workspace)
        self.assertEqual((self.evals_json.parent / "fixtures" / "sample-one.md").read_text(), original)

    def test_missing_fixture_raises(self):
        broken = self.evals_json.parent / "broken.json"
        broken.write_text(json.dumps({
            "skill_name": "example",
            "evals": [{"id": 1, "prompt": "x", "files": ["fixtures/does-not-exist.md"], "assertions": []}],
        }))
        with self.assertRaises(FileNotFoundError):
            convert_evals.convert(broken, self.root / "workspace2")


if __name__ == "__main__":
    unittest.main()
