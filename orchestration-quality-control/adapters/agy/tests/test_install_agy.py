import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ADAPTER = Path(__file__).resolve().parents[1]
INSTALLER_PATH = ADAPTER / "install_agy.py"


def _load_installer():
    spec = importlib.util.spec_from_file_location("agy_install", INSTALLER_PATH)
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
        self.source = self.root / "plugin"
        (self.source / "skills" / "example").mkdir(parents=True)
        (self.source / "skills" / "example" / "SKILL.md").write_text("# Example\n", encoding="utf-8")
        (self.source / "plugin.json").write_text("{}\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def _args(self, **overrides):
        values = {
            "scope": "user",
            "agy_home": str(self.root / "agy-home"),
            "workspace": str(self.root / "workspace"),
            "dry_run": False,
            "uninstall": False,
        }
        values.update(overrides)
        return types.SimpleNamespace(**values)

    def test_install_user_scope_is_idempotent(self):
        args = self._args()
        with mock.patch.object(INSTALLER, "_plugin_source", return_value=self.source), mock.patch.object(
            INSTALLER, "_run_build", return_value=0
        ):
            self.assertEqual(INSTALLER.install(args), 0)
            self.assertEqual(INSTALLER.install(args), 0)
        destination = self.root / "agy-home" / "plugins" / INSTALLER.PLUGIN_NAME
        self.assertTrue((destination / "skills/example/SKILL.md").is_file())

    def test_install_workspace_scope(self):
        args = self._args(scope="workspace")
        with mock.patch.object(INSTALLER, "_plugin_source", return_value=self.source), mock.patch.object(
            INSTALLER, "_run_build", return_value=0
        ):
            self.assertEqual(INSTALLER.install(args), 0)
        destination = self.root / "workspace" / ".agents" / "plugins" / INSTALLER.PLUGIN_NAME
        self.assertTrue((destination / "skills/example/SKILL.md").is_file())

    def test_unmanaged_collision_is_refused(self):
        args = self._args()
        destination = self.root / "agy-home" / "plugins" / INSTALLER.PLUGIN_NAME
        destination.mkdir(parents=True)
        (destination / "unmanaged.txt").write_text("keep\n", encoding="utf-8")
        with mock.patch.object(INSTALLER, "_plugin_source", return_value=self.source), mock.patch.object(
            INSTALLER, "_run_build", return_value=0
        ):
            self.assertEqual(INSTALLER.install(args), 2)
        self.assertEqual((destination / "unmanaged.txt").read_text(encoding="utf-8"), "keep\n")

    def test_uninstall_fails_closed_after_managed_change(self):
        args = self._args()
        with mock.patch.object(INSTALLER, "_plugin_source", return_value=self.source), mock.patch.object(
            INSTALLER, "_run_build", return_value=0
        ):
            self.assertEqual(INSTALLER.install(args), 0)
        destination = self.root / "agy-home" / "plugins" / INSTALLER.PLUGIN_NAME
        (destination / "skills/example/SKILL.md").write_text("changed\n", encoding="utf-8")
        self.assertEqual(INSTALLER.uninstall(args), 2)

    def test_uninstall_succeeds_when_unchanged(self):
        args = self._args()
        with mock.patch.object(INSTALLER, "_plugin_source", return_value=self.source), mock.patch.object(
            INSTALLER, "_run_build", return_value=0
        ):
            self.assertEqual(INSTALLER.install(args), 0)
            destination = self.root / "agy-home" / "plugins" / INSTALLER.PLUGIN_NAME
            self.assertTrue(destination.is_dir())
            self.assertEqual(INSTALLER.uninstall(args), 0)
            self.assertFalse(destination.exists())

    def test_pycache_does_not_block_reinstall(self):
        args = self._args()
        with mock.patch.object(INSTALLER, "_plugin_source", return_value=self.source), mock.patch.object(
            INSTALLER, "_run_build", return_value=0
        ):
            self.assertEqual(INSTALLER.install(args), 0)
        destination = self.root / "agy-home" / "plugins" / INSTALLER.PLUGIN_NAME
        cache = destination / "hooks" / "__pycache__"
        cache.mkdir(parents=True)
        (cache / "compiled.pyc").write_bytes(b"bytecode")
        with mock.patch.object(INSTALLER, "_plugin_source", return_value=self.source), mock.patch.object(
            INSTALLER, "_run_build", return_value=0
        ):
            self.assertEqual(INSTALLER.install(args), 0)

    def test_dry_run_writes_nothing(self):
        args = self._args(dry_run=True)
        with mock.patch.object(INSTALLER, "_plugin_source", return_value=self.source), mock.patch.object(
            INSTALLER, "_run_build", return_value=0
        ):
            self.assertEqual(INSTALLER.install(args), 0)
        self.assertFalse((self.root / "agy-home").exists())


if __name__ == "__main__":
    unittest.main()
