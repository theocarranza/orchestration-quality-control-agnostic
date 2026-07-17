import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ADAPTER = Path(__file__).resolve().parents[1]
HOOK = ADAPTER / "hooks" / "oqc_cursor_guard.py"
AUTH = ADAPTER / "hooks" / "cursor_authorization.py"


def _load_auth():
    spec = importlib.util.spec_from_file_location("cursor_authorization_test", AUTH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


AUTHORIZATION = _load_auth()


class CursorHookTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = self.root / ".orchestration-qc" / "state"
        self.state.mkdir(parents=True)
        self.checkpoint = self.state / "checkpoint-run.json"
        self.checkpoint.write_text(
            json.dumps(
                {
                    "run_id": "run",
                    "status": "pending_approval",
                    "targets": ["rules.md"],
                    "findings": [
                        {
                            "id": "F-1",
                            "location": {"path": "rules.md"},
                            "suggested_change": {"before": "old", "after": "new"},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def _run(self, payload):
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env={**os.environ, "CURSOR_PLUGIN_ROOT": str(ADAPTER)},
        )

    def _decision(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def _edit(self, path="rules.md", before="old", after="bad"):
        return {
            "hook_event_name": "preToolUse",
            "tool_name": "Edit",
            "tool_input": {"path": path, "old_string": before, "new_string": after},
            "workspace_roots": [str(self.root)],
        }

    def test_no_checkpoint_allows(self):
        self.checkpoint.unlink()
        result = self._run(self._edit())
        self.assertEqual(self._decision(result)["permission"], "allow")

    def test_pending_shell_is_denied(self):
        result = self._run(
            {
                "hook_event_name": "beforeShellExecution",
                "tool_input": {"command": "echo unsafe"},
                "workspace_roots": [str(self.root)],
            }
        )
        self.assertEqual(self._decision(result)["permission"], "deny")

    def test_pending_shell_allows_exact_deterministic_script(self):
        result = self._run(
            {
                "hook_event_name": "beforeShellExecution",
                "tool_input": {"command": f"python3 {AUTH}"},
                "workspace_roots": [str(self.root)],
            }
        )
        self.assertEqual(self._decision(result)["permission"], "allow")

    def test_pending_shell_allows_upgrade_deterministic_scripts(self):
        scripts = ADAPTER.parents[1] / "scripts"
        plugin_root = self.root / "plugin"
        plugin_scripts = plugin_root / "skills" / "orchestration-quality-control" / "scripts"
        plugin_scripts.mkdir(parents=True)
        for name in ("discover_structure.py", "upgrade_state.py", "apply_upgrade.py"):
            target = plugin_scripts / name
            target.write_text((scripts / name).read_text(encoding="utf-8"), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(HOOK)],
                input=json.dumps(
                    {
                        "hook_event_name": "beforeShellExecution",
                        "tool_input": {"command": f"python3 {target}"},
                        "workspace_roots": [str(self.root)],
                    }
                ),
                capture_output=True,
                text=True,
                env={**os.environ, "CURSOR_PLUGIN_ROOT": str(plugin_root)},
            )
            self.assertEqual(self._decision(result)["permission"], "allow", name)

    def test_unapproved_protected_edit_is_denied(self):
        result = self._run(self._edit())
        self.assertEqual(self._decision(result)["permission"], "deny")

    def test_unrelated_edit_is_allowed(self):
        result = self._run(self._edit(path="other.md"))
        self.assertEqual(self._decision(result)["permission"], "allow")

    def test_exact_authorized_edit_is_allowed(self):
        AUTHORIZATION.create(self.checkpoint, ["F-1"])
        result = self._run(self._edit(after="new"))
        self.assertEqual(self._decision(result)["permission"], "allow")

    def test_stale_authorization_is_denied(self):
        AUTHORIZATION.create(self.checkpoint, ["F-1"])
        self.checkpoint.write_text(self.checkpoint.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        result = self._run(self._edit(after="new"))
        self.assertEqual(self._decision(result)["permission"], "deny")

    def test_malformed_input_is_denied(self):
        result = subprocess.run(
            [sys.executable, str(HOOK)],
            input="not-json",
            capture_output=True,
            text=True,
        )
        self.assertEqual(self._decision(result)["permission"], "deny")


if __name__ == "__main__":
    unittest.main()
