import json
import subprocess
import sys
import unittest

from claude_policy_hook import decide, generated_settings, local_cli_smoke


class ClaudePolicyHookTests(unittest.TestCase):
    def test_allows_exact_agent_worker_only(self):
        payload = {"tool_name": "Agent", "tool_input": {"subagent_type": "author"}, "tool_use_id": "u1"}
        self.assertEqual(decide(payload, "author")["hookSpecificOutput"]["permissionDecision"], "allow")

    def test_allows_documented_native_metadata_and_agent_fields(self):
        payload = {"hook_event_name": "PreToolUse", "session_id": "s1", "transcript_path": "/tmp/t",
                   "cwd": "/tmp", "permission_mode": "default", "tool_name": "Agent",
                   "tool_input": {"prompt": "do", "description": "worker", "subagent_type": "author", "model": "sonnet"},
                   "tool_use_id": "u1"}
        self.assertEqual(decide(payload, "author")["hookSpecificOutput"]["permissionDecision"], "allow")

    def test_denies_other_tools_workers_malformed_and_invalid_expected_identity(self):
        cases = [
            ({"tool_name": "Bash", "tool_input": {}}, "author"),
            ({"tool_name": "Agent", "tool_input": {"subagent_type": "reviewer"}}, "author"),
            ({"tool_name": "Agent", "tool_input": {"subagent_type": "author", "extra": 1}}, "author"),
            ({"tool_name": "Agent", "tool_input": {}}, "author"),
            (None, "author"),
            ({"tool_name": "Agent", "tool_input": {"subagent_type": "author"}}, ""),
            ({"tool_name": "Agent", "tool_input": {"subagent_type": "author"}}, "inherit"),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload, expected=expected):
                self.assertEqual(decide(payload, expected)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_settings_are_deterministic_direct_argv_and_match_every_tool(self):
        settings = generated_settings("author")
        hook = settings["hooks"]["PreToolUse"][0]
        self.assertEqual(hook["matcher"], "*")
        command = hook["hooks"][0]
        self.assertEqual(command["type"], "command")
        self.assertEqual(command["args"][-1], "author")
        self.assertGreater(command["timeout"], 0)
        self.assertEqual(settings, generated_settings("author"))
        self.assertNotIn(" ", command["command"])

    def test_command_entrypoint_emits_one_decision(self):
        payload = json.dumps({"tool_name": "Agent", "tool_input": {"subagent_type": "author"}, "tool_use_id": "u1"})
        proc = subprocess.run([sys.executable, "orchestration-quality-control/scripts/claude_policy_hook.py", "author"], input=payload, text=True, capture_output=True, check=True)
        output = json.loads(proc.stdout)
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "allow")
        self.assertEqual(len(proc.stdout.strip().splitlines()), 1)

    def test_local_cli_smoke_is_help_version_only_and_runs_real_hook_fixtures(self):
        result = local_cli_smoke()
        self.assertTrue(result["flags"])
        self.assertEqual(result["fixtures"], {"allow": "allow", "deny": "deny", "malformed": "deny"})
