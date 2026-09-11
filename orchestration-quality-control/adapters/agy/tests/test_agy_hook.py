import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ADAPTER = Path(__file__).resolve().parents[1]
HOOK = ADAPTER / "hooks" / "oqc_agy_guard.py"
AUTH = ADAPTER / "hooks" / "agy_authorization.py"


def _load_auth():
    spec = importlib.util.spec_from_file_location("agy_authorization_test", AUTH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


AUTHORIZATION = _load_auth()


class AgyHookTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = self.root / ".orchestration-qc" / "state"
        self.state.mkdir(parents=True)
        self.checkpoint = self.state / "checkpoint-run.json"
        self.checkpoint.write_text(
            json.dumps(
                {
                    "run_id": "run-001",
                    "status": "pending_approval",
                    "targets": ["rules.md"],
                    "findings": [
                        {
                            "id": "F-1",
                            "location": {"path": "rules.md"},
                            "suggested_change": {"before": "old text", "after": "new text"},
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
            env={**os.environ, "AGY_PLUGIN_ROOT": str(ADAPTER)},
        )

    def _decision(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def _tool_call(self, tool_name, args):
        return {
            "conversationId": "conv-123",
            "workspacePaths": [str(self.root)],
            "toolCall": {
                "name": tool_name,
                "args": args,
            },
        }

    def test_no_checkpoint_allows(self):
        self.checkpoint.unlink()
        payload = self._tool_call("replace_file_content", {
            "TargetFile": str(self.root / "rules.md"),
            "TargetContent": "old text",
            "ReplacementContent": "new text",
        })
        result = self._run(payload)
        decision = self._decision(result)
        self.assertEqual(decision["decision"], "allow")
        self.assertTrue(decision["continue"])

    def test_unrelated_target_allows(self):
        payload = self._tool_call("replace_file_content", {
            "TargetFile": str(self.root / "other.md"),
            "TargetContent": "foo",
            "ReplacementContent": "bar",
        })
        result = self._run(payload)
        decision = self._decision(result)
        self.assertEqual(decision["decision"], "allow")

    def test_unauthorized_replace_content_denies(self):
        payload = self._tool_call("replace_file_content", {
            "TargetFile": str(self.root / "rules.md"),
            "TargetContent": "old text",
            "ReplacementContent": "unauthorized edit",
        })
        result = self._run(payload)
        decision = self._decision(result)
        self.assertEqual(decision["decision"], "deny")
        self.assertFalse(decision["continue"])

    def test_authorized_replace_content_allows(self):
        AUTHORIZATION.create(self.checkpoint, ["F-1"])
        payload = self._tool_call("replace_file_content", {
            "TargetFile": str(self.root / "rules.md"),
            "TargetContent": "old text",
            "ReplacementContent": "new text",
        })
        result = self._run(payload)
        decision = self._decision(result)
        self.assertEqual(decision["decision"], "allow")
        self.assertTrue(decision["continue"])

    def test_direct_write_to_protected_target_denies(self):
        payload = self._tool_call("write_to_file", {
            "TargetFile": str(self.root / "rules.md"),
            "CodeContent": "overwrite content",
        })
        result = self._run(payload)
        decision = self._decision(result)
        self.assertEqual(decision["decision"], "deny")
        self.assertIn("Direct write to protected target", decision["reason"])

    def test_direct_write_to_unrelated_target_allows(self):
        payload = self._tool_call("write_to_file", {
            "TargetFile": str(self.root / "new_file.txt"),
            "CodeContent": "new content",
        })
        result = self._run(payload)
        decision = self._decision(result)
        self.assertEqual(decision["decision"], "allow")

    def test_read_only_tool_allows(self):
        payload = self._tool_call("view_file", {
            "AbsolutePath": str(self.root / "rules.md"),
        })
        result = self._run(payload)
        decision = self._decision(result)
        self.assertEqual(decision["decision"], "allow")

    def test_unauthorized_shell_command_denies(self):
        payload = self._tool_call("run_command", {
            "CommandLine": "rm -rf rules.md",
            "Cwd": str(self.root),
        })
        result = self._run(payload)
        decision = self._decision(result)
        self.assertEqual(decision["decision"], "deny")
        self.assertIn("Shell commands are blocked", decision["reason"])

    def test_allowed_script_command_allows(self):
        script = ADAPTER / "hooks" / "agy_authorization.py"
        payload = self._tool_call("run_command", {
            "CommandLine": f"python3 {script} --checkpoint {self.checkpoint}",
            "Cwd": str(self.root),
        })
        result = self._run(payload)
        decision = self._decision(result)
        self.assertEqual(decision["decision"], "allow")

    def test_multiple_pending_checkpoints_denies(self):
        second = self.state / "checkpoint-second.json"
        second.write_text(self.checkpoint.read_text(encoding="utf-8"), encoding="utf-8")
        payload = self._tool_call("replace_file_content", {
            "TargetFile": str(self.root / "rules.md"),
            "TargetContent": "old text",
            "ReplacementContent": "new text",
        })
        result = self._run(payload)
        decision = self._decision(result)
        self.assertEqual(decision["decision"], "deny")
        self.assertIn("multiple pending", decision["reason"])

    def test_clear_authorization_removes_auth_file(self):
        auth_file = AUTHORIZATION.create(self.checkpoint, ["F-1"])
        self.assertTrue(auth_file.is_file())
        cleared = AUTHORIZATION.clear(self.checkpoint)
        self.assertEqual(auth_file, cleared)
        self.assertFalse(auth_file.exists())

    def test_authorization_validates_unknown_findings(self):
        with self.assertRaises(ValueError) as context:
            AUTHORIZATION.create(self.checkpoint, ["UNKNOWN_ID"])
        self.assertIn("unknown approved finding id", str(context.exception))


if __name__ == "__main__":
    unittest.main()
