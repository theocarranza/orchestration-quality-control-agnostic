import subprocess
import sys
import unittest
from pathlib import Path


ADAPTER = Path(__file__).resolve().parents[1]
INSTALLER = ADAPTER / "install_codex.py"


class FrontDoorInstallerTest(unittest.TestCase):
    def test_dry_run_exposes_one_complete_install_sequence(self):
        result = subprocess.run(
            [sys.executable, str(INSTALLER), "--scope", "user", "--dry-run"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("build_plugin.py", result.stdout)
        self.assertIn("codex plugin marketplace add", result.stdout)
        self.assertIn("codex plugin add", result.stdout)
        self.assertIn("install_codex_adapter.py", result.stdout)

    def test_project_scope_is_forwarded_to_the_bootstrap(self):
        result = subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--scope",
                "project",
                "--project",
                "/trusted/project",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--scope project --project /trusted/project", result.stdout)

    def test_user_scope_rejects_project_argument(self):
        result = subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--scope",
                "user",
                "--project",
                "/ambiguous",
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--project is only valid", result.stderr)


if __name__ == "__main__":
    unittest.main()
