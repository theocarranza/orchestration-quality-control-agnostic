import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ADAPTER = Path(__file__).resolve().parents[1]
HOOKS = ADAPTER / "hooks"
GUARD = HOOKS / "oqc_codex_guard.py"
AUTHORIZATION = HOOKS / "codex_authorization.py"


def _load_authorization():
    spec = importlib.util.spec_from_file_location("codex_authorization", AUTHORIZATION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


AUTH = _load_authorization()


class AuthorizationAndHookTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.state = self.workspace / ".orchestration-qc" / "state"
        self.state.mkdir(parents=True)
        self.target = self.workspace / "workflow.md"
        self.target.write_text("old value\n", encoding="utf-8")
        self.plugin = self.root / "plugin"
        (self.plugin / "hooks").mkdir(parents=True)
        scripts = self.plugin / "skills" / "orchestration-quality-control" / "scripts"
        scripts.mkdir(parents=True)
        for name in ("checkpoint_state.py", "reconcile_decision.py", "render_diff.py"):
            (scripts / name).write_text("", encoding="utf-8")
        self.checkpoint_path = self._write_checkpoint()

    def tearDown(self):
        self.temp.cleanup()

    def _write_checkpoint(self, status="pending_approval", report="report"):
        checkpoint = {
            "schema_version": 2,
            "run_id": "20260717-hook-test",
            "status": status,
            "targets": ["workflow.md"],
            "profile": "core",
            "language": "en",
            "findings": [
                {
                    "id": "W1-workflow-deadbeef01",
                    "kind": "core/workflow",
                    "rule": "rules-workflow-quality-control.md#W1",
                    "location": {"path": "workflow.md", "section": "Example"},
                    "anchor": "old value",
                    "violation": "The value is obsolete.",
                    "suggested_change": {"before": "old value", "after": "new value"},
                    "confidence": "high",
                }
            ],
            "plain_language_report": report,
            "created_at": "2026-07-17T00:00:00Z",
        }
        path = self.state / "checkpoint-20260717-hook-test.json"
        path.write_text(json.dumps(checkpoint), encoding="utf-8")
        return path

    def _run(self, payload, raw=None):
        env = os.environ.copy()
        env["PLUGIN_ROOT"] = str(self.plugin)
        return subprocess.run(
            [sys.executable, str(GUARD)],
            input=raw if raw is not None else json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
        )

    def _patch_payload(self, path="workflow.md", before="old value", after="new value"):
        patch = f"*** Begin Patch\n*** Update File: {path}\n@@\n-{before}\n+{after}\n*** End Patch"
        return {
            "cwd": str(self.workspace),
            "tool_name": "apply_patch",
            "tool_input": {"patch": patch},
        }

    def _permission(self, process):
        self.assertEqual(process.returncode, 0, process.stderr)
        return json.loads(process.stdout)["permissionDecision"]

    def test_authorization_contains_checkpoint_and_change_hashes(self):
        payload = AUTH.build_authorization(self.checkpoint_path, ["W1-workflow-deadbeef01"])
        self.assertEqual(payload["checkpoint_sha256"], hashlib.sha256(self.checkpoint_path.read_bytes()).hexdigest())
        self.assertEqual(
            payload["approved_changes"][0]["change_sha256"],
            AUTH.change_digest("workflow.md", "old value", "new value"),
        )

    def test_unknown_finding_is_rejected(self):
        with self.assertRaises(ValueError):
            AUTH.build_authorization(self.checkpoint_path, ["unknown"])

    def test_unapproved_target_patch_is_denied(self):
        self.assertEqual(self._permission(self._run(self._patch_payload())), "deny")

    def test_exact_authorized_patch_is_allowed(self):
        AUTH.create(self.checkpoint_path, ["W1-workflow-deadbeef01"])
        self.assertEqual(self._permission(self._run(self._patch_payload())), "allow")

    def test_freeform_string_patch_payload_is_supported(self):
        AUTH.create(self.checkpoint_path, ["W1-workflow-deadbeef01"])
        payload = self._patch_payload()
        payload["tool_input"] = payload["tool_input"]["patch"]
        self.assertEqual(self._permission(self._run(payload)), "allow")

    def test_authorization_does_not_allow_a_different_change(self):
        AUTH.create(self.checkpoint_path, ["W1-workflow-deadbeef01"])
        self.assertEqual(self._permission(self._run(self._patch_payload(after="other value"))), "deny")

    def test_stale_authorization_is_denied(self):
        AUTH.create(self.checkpoint_path, ["W1-workflow-deadbeef01"])
        self._write_checkpoint(report="changed after authorization")
        self.assertEqual(self._permission(self._run(self._patch_payload())), "deny")

    def test_unrelated_patch_is_allowed(self):
        (self.workspace / "unrelated.md").write_text("a\n", encoding="utf-8")
        self.assertEqual(self._permission(self._run(self._patch_payload("unrelated.md", "a", "b"))), "allow")

    def test_traversal_patch_is_denied(self):
        self.assertEqual(self._permission(self._run(self._patch_payload("../outside.md"))), "deny")

    def test_patch_with_context_is_denied(self):
        payload = self._patch_payload()
        payload["tool_input"]["patch"] = "*** Begin Patch\n*** Update File: workflow.md\n@@\n context\n-old value\n+new value\n*** End Patch"
        self.assertEqual(self._permission(self._run(payload)), "deny")

    def test_authorized_change_cannot_also_move_the_target(self):
        AUTH.create(self.checkpoint_path, ["W1-workflow-deadbeef01"])
        payload = self._patch_payload()
        payload["tool_input"]["patch"] = payload["tool_input"]["patch"].replace(
            "@@", "*** Move to: moved.md\n@@"
        )
        self.assertEqual(self._permission(self._run(payload)), "deny")

    def test_shell_is_denied_while_pending(self):
        payload = {"cwd": str(self.workspace), "tool_name": "Bash", "tool_input": {"command": "touch workflow.md"}}
        self.assertEqual(self._permission(self._run(payload)), "deny")

    def test_freeform_string_shell_payload_is_denied(self):
        payload = {"cwd": str(self.workspace), "tool_name": "Bash", "tool_input": "touch workflow.md"}
        self.assertEqual(self._permission(self._run(payload)), "deny")

    def test_allowlisted_script_is_allowed_without_shell_chaining(self):
        script = self.plugin / "skills" / "orchestration-quality-control" / "scripts" / "checkpoint_state.py"
        payload = {"cwd": str(self.workspace), "tool_name": "Bash", "tool_input": {"command": f"python3 {script} status --checkpoint {self.checkpoint_path}"}}
        self.assertEqual(self._permission(self._run(payload)), "allow")
        payload["tool_input"]["command"] += " && touch workflow.md"
        self.assertEqual(self._permission(self._run(payload)), "deny")

    def test_allowlisted_upgrade_scripts_are_allowed(self):
        scripts = self.plugin / "skills" / "orchestration-quality-control" / "scripts"
        for name in ("discover_structure.py", "upgrade_state.py", "apply_upgrade.py"):
            payload = {
                "cwd": str(self.workspace),
                "tool_name": "Bash",
                "tool_input": {"command": f"python3 {scripts / name} --help"},
            }
            self.assertEqual(self._permission(self._run(payload)), "allow", name)

    def test_consumed_and_aborted_checkpoints_allow_normal_tools(self):
        for status in ("consumed", "aborted"):
            self._write_checkpoint(status=status)
            self.assertEqual(self._permission(self._run(self._patch_payload())), "allow")

    def test_malformed_hook_payload_fails_closed(self):
        self.assertEqual(self._permission(self._run({}, raw="not-json")), "deny")

    def test_clear_removes_authorization(self):
        path = AUTH.create(self.checkpoint_path, ["W1-workflow-deadbeef01"])
        self.assertTrue(path.exists())
        AUTH.clear(self.checkpoint_path)
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
