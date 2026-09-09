import hashlib
import importlib.util
import json
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ADAPTER = Path(__file__).resolve().parents[1]
BUILDER_PATH = ADAPTER / "build_plugin.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_plugin", BUILDER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BUILDER = _load_builder()


class BuildPluginTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output = self.root / "codex-marketplace"

    def tearDown(self):
        self.temp.cleanup()

    def test_build_has_expected_plugin_marketplace_skill_hook_and_agents(self):
        BUILDER.build(self.output)
        plugin = self.output / "plugins" / BUILDER.PLUGIN_NAME
        manifest = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        marketplace = json.loads((self.output / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], BUILDER.VERSION)
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertNotIn("hooks", manifest)
        self.assertEqual(marketplace["name"], BUILDER.MARKETPLACE_NAME)
        self.assertTrue((plugin / "hooks" / "hooks.json").is_file())
        self.assertTrue((self.output / "install_codex_adapter.py").is_file())
        self.assertTrue((self.output / "install_codex.py").is_file())
        self.assertTrue((self.output / "README.md").is_file())
        self.assertEqual(len(list((self.output / "agents").glob("*.toml"))), 6)
        self.assertTrue(
            (plugin / "skills" / "orchestration-upgrade" / "SKILL.md").is_file()
        )
        self.assertTrue(
            (plugin / "skills" / "orchestration-author" / "SKILL.md").is_file()
        )

    def test_build_injects_overlay_without_mutating_canonical_skill(self):
        canonical = BUILDER._package_root() / "SKILL.md"
        before = canonical.read_bytes()
        BUILDER.build(self.output)
        generated = self.output / "plugins" / BUILDER.PLUGIN_NAME / "skills" / BUILDER.PLUGIN_NAME / "SKILL.md"
        text = generated.read_text(encoding="utf-8")
        self.assertIn("\n# Codex adapter execution\n", text)
        self.assertIn("# Orchestration Quality Control", text)
        self.assertEqual(canonical.read_bytes(), before)

    def test_build_excludes_python_bytecode(self):
        BUILDER.build(self.output)
        self.assertFalse(any(path.name == "__pycache__" or path.suffix == ".pyc" for path in self.output.rglob("*")))

    def test_author_entrypoint_routes_to_canonical_sibling_skill_root(self):
        BUILDER.build(self.output)
        skills = self.output / "plugins" / BUILDER.PLUGIN_NAME / "skills"
        author = skills / "orchestration-author"
        canonical = skills / BUILDER.PLUGIN_NAME
        workflow = canonical / "references" / "workflows" / "workflows-root-session-interview.md"
        self.assertTrue(workflow.is_file())
        entrypoint = (author / "SKILL.md").read_text(encoding="utf-8")
        for resource_dir in ("references", "rules", "schemas", "scripts"):
            self.assertFalse((author / resource_dir).exists())
        self.assertIn(
            "../orchestration-quality-control/references/workflows/workflows-root-session-interview.md",
            entrypoint,
        )
        self.assertNotIn("`references/workflows/workflows-root-session-interview.md`", entrypoint)
        self.assertNotIn("`scripts/discover_workspace.py`", entrypoint)
        self.assertNotIn("`scripts/plan_interview.py`", entrypoint)
        resource_prefix = "../orchestration-quality-control/"
        resource_classes = ("references/", "rules/", "schemas/", "scripts/")
        for path in re.findall(r"`([^`\n]+)`", entrypoint):
            if any(resource in path for resource in resource_classes):
                self.assertTrue(path.startswith(resource_prefix), path)

    def test_validator_accepts_the_installed_upgrade_orchestrator_caller(self):
        BUILDER.build(self.output)
        validator = (
            self.output
            / "agents"
            / "oqc_codex_validator.toml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "Accept work only from oqc_codex_upgrade_orchestrator",
            validator,
        )
        self.assertNotIn(
            "Accept work only from oqc_codex_orchestrator",
            validator,
        )

    def test_build_manifest_hashes_every_other_file(self):
        BUILDER.build(self.output)
        manifest = json.loads((self.output / "BUILD-MANIFEST.json").read_text(encoding="utf-8"))["files"]
        actual = {}
        for path in sorted(item for item in self.output.rglob("*") if item.is_file()):
            relative = path.relative_to(self.output).as_posix()
            if relative != "BUILD-MANIFEST.json":
                actual[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(manifest, actual)

    def test_zip_is_reproducible_and_rooted(self):
        BUILDER.build(self.output)
        first = self.root / "first.zip"
        second = self.root / "second.zip"
        BUILDER.write_zip(self.output, first)
        BUILDER.write_zip(self.output, second)
        self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(), hashlib.sha256(second.read_bytes()).hexdigest())
        with zipfile.ZipFile(first) as archive:
            names = archive.namelist()
        self.assertTrue(names)
        self.assertTrue(all(name.startswith("codex-marketplace/") for name in names))


if __name__ == "__main__":
    unittest.main()
