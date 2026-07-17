import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ADAPTER = Path(__file__).resolve().parents[1]
INSTALLER_PATH = ADAPTER / "install_codex_adapter.py"


def _load_installer():
    spec = importlib.util.spec_from_file_location("install_codex_adapter", INSTALLER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


INSTALLER = _load_installer()


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.codex_home = self.root / "codex-home"

    def tearDown(self):
        self.temp.cleanup()

    def _run(self, *extra):
        return subprocess.run(
            [sys.executable, str(INSTALLER_PATH), "--codex-home", str(self.codex_home), *extra],
            capture_output=True,
            text=True,
        )

    def test_config_append_preserves_existing_contents(self):
        original = "model = \"example\"\n# keep this comment\n"
        edit = INSTALLER.plan_config_edit(original)
        self.assertTrue(edit.after.startswith(original))
        self.assertIn("[agents]\nmax_depth = 2", edit.after)

    def test_config_replaces_only_a_low_depth_value(self):
        original = "[agents]\nmax_threads = 4\nmax_depth = 1 # nested off\n\n[features]\nhooks = true\n"
        edit = INSTALLER.plan_config_edit(original)
        self.assertEqual(edit.action, "replace")
        self.assertEqual(edit.after, original.replace("max_depth = 1", "max_depth = 2"))

    def test_config_keeps_higher_depth(self):
        original = "[agents]\nmax_depth = 3\n"
        self.assertEqual(INSTALLER.plan_config_edit(original).action, "none")

    def test_unparseable_depth_fails_with_manual_recovery(self):
        with self.assertRaisesRegex(ValueError, "set it manually"):
            INSTALLER.plan_config_edit("[agents]\nmax_depth = \"two\"\n")

    def test_user_install_is_idempotent_and_uninstall_restores_config(self):
        self.codex_home.mkdir()
        config = self.codex_home / "config.toml"
        original = "model = \"example\"\n"
        config.write_text(original, encoding="utf-8")
        first = self._run()
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self._run()
        self.assertEqual(second.returncode, 0, second.stderr)
        for filename in INSTALLER.AGENT_FILENAMES:
            self.assertTrue((self.codex_home / "agents" / filename).is_file())
        self.assertIn("max_depth = 2", config.read_text(encoding="utf-8"))
        uninstall = self._run("--uninstall")
        self.assertEqual(uninstall.returncode, 0, uninstall.stderr)
        self.assertEqual(config.read_text(encoding="utf-8"), original)
        for filename in INSTALLER.AGENT_FILENAMES:
            self.assertFalse((self.codex_home / "agents" / filename).exists())

    def test_dry_run_writes_nothing(self):
        result = self._run("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.codex_home.exists())

    def test_conflicting_agent_is_refused_without_partial_writes(self):
        agents = self.codex_home / "agents"
        agents.mkdir(parents=True)
        conflict = agents / INSTALLER.AGENT_FILENAMES[0]
        conflict.write_text("unmanaged", encoding="utf-8")
        result = self._run()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(conflict.read_text(encoding="utf-8"), "unmanaged")
        self.assertFalse((self.codex_home / INSTALLER.RECORD_NAME).exists())

    def test_project_scope_uses_project_codex_directory(self):
        project = self.root / "project"
        project.mkdir()
        result = subprocess.run(
            [sys.executable, str(INSTALLER_PATH), "--scope", "project", "--project", str(project)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((project / ".codex" / "agents" / INSTALLER.AGENT_FILENAMES[0]).is_file())
        self.assertIn("max_depth = 2", (project / ".codex" / "config.toml").read_text(encoding="utf-8"))

    def test_uninstall_refuses_to_overwrite_later_config_changes(self):
        self.assertEqual(self._run().returncode, 0)
        config = self.codex_home / "config.toml"
        config.write_text(config.read_text(encoding="utf-8") + "# later edit\n", encoding="utf-8")
        result = self._run("--uninstall")
        self.assertEqual(result.returncode, 2)
        self.assertIn("refusing to overwrite", result.stderr)

    def test_install_record_contains_agent_hashes_and_config_edit(self):
        self.assertEqual(self._run().returncode, 0)
        record = json.loads((self.codex_home / INSTALLER.RECORD_NAME).read_text(encoding="utf-8"))
        self.assertEqual(set(record["agent_hashes"]), set(INSTALLER.AGENT_FILENAMES))
        self.assertEqual(record["config_edit"]["action"], "append")


if __name__ == "__main__":
    unittest.main()
