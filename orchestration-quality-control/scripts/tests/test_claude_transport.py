import json
import unittest
from pathlib import Path

from claude_transport import ClaudeTransport, parse_stream
from qc_lib import Blocked


def _events(session_id="session-1", worker="author", result=None):
    return "\n".join(json.dumps(event) for event in (
        {"type": "system", "subtype": "init", "session_id": session_id},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "tool-1", "name": "Agent", "input": {"subagent_type": worker}}]}},
        {"type": "result", "session_id": session_id, "structured_output": result or {"task_id": "t1", "attempt": 1, "outcome": "passed"}},
    ))


def _schema():
    return json.loads((Path(__file__).resolve().parents[2] / "schemas" / "worker-result.schema.json").read_text())


class ClaudeTransportTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def runner(argv):
            self.calls.append(argv)
            return 0, _events(), ""

        self.transport = ClaudeTransport(runner, executable="claude")

    def test_initial_invocation_is_explicit_shell_free_and_canonical(self):
        result = self.transport.invoke(
            prompt="dispatch", model="sonnet", effort="medium", worker_name="author",
            worker_definition={"description": "Worker", "prompt": "Do work"},
            worker_schema=_schema(),
        )
        self.assertEqual(self.calls, [(
            "claude", "--print", "--model", "sonnet", "--effort", "medium",
            "--tools", "Agent", "--allowed-tools", "Agent(author)", "--agents",
            '{"author":{"description":"Worker","prompt":"Do work"}}', "--json-schema",
            json.dumps(_schema(), sort_keys=True, separators=(",", ":")), "--output-format", "stream-json", "--verbose",
            "--include-hook-events", "--permission-mode", "dontAsk", "dispatch",
        )])
        self.assertEqual(result.session_id, "session-1")
        self.assertEqual(result.worker_tool_use_id, "tool-1")
        self.assertEqual(result.structured_output["task_id"], "t1")
        self.assertEqual(result.raw_stdout, _events())
        with self.assertRaises(TypeError):
            result.events[0]["type"] = "changed"

    def test_resume_uses_explicit_session_and_rejects_changed_session(self):
        self.transport.invoke("first", "sonnet", "medium", "author", {"description": "W", "prompt": "P"}, _schema())
        self.transport.invoke("next", "sonnet", "medium", "author", {"description": "W", "prompt": "P"}, _schema(), session_id="session-1")
        self.assertIn("--resume", self.calls[1])
        self.assertEqual(self.calls[1][self.calls[1].index("--resume") + 1], "session-1")

        changed = ClaudeTransport(lambda argv: (0, _events("other"), ""))
        with self.assertRaises(Blocked):
            changed.invoke("next", "sonnet", "medium", "author", {"description": "W", "prompt": "P"}, _schema(), session_id="session-1")

    def test_boundaries_are_blocked_without_calling_subprocess(self):
        for model, effort in (("", "medium"), ("inherit", "medium"), ("sonnet", ""), ("sonnet", "inherit"), (True, "medium")):
            with self.subTest(model=model, effort=effort), self.assertRaises(Blocked):
                self.transport.invoke("p", model, effort, "author", {"description": "W", "prompt": "P"}, _schema())
        self.assertEqual(self.calls, [])

    def test_malformed_nonzero_missing_wrong_agent_and_invalid_output_are_blocked(self):
        cases = [
            (1, _events(), "bad"),
            (0, "not json", ""),
            (0, json.dumps({"type": "result", "session_id": "session-1", "structured_output": {"task_id": "t1", "attempt": 1, "outcome": "passed"}}), ""),
            (0, _events(worker="reviewer"), ""),
            (0, _events(result={"task_id": "t1", "attempt": True, "outcome": "passed"}), ""),
        ]
        for exit_code, stdout, stderr in cases:
            with self.subTest(exit_code=exit_code, stdout=stdout), self.assertRaises(Blocked):
                ClaudeTransport(lambda argv: (exit_code, stdout, stderr)).invoke(
                    "p", "sonnet", "medium", "author", {"description": "W", "prompt": "P"}, _schema())

    def test_parse_rejects_missing_init_separately_from_missing_final(self):
        missing_init = "\n".join(_events().splitlines()[1:])
        missing_final = "\n".join(_events().splitlines()[:2])
        for stdout, expected in ((missing_init, "missing native init"), (missing_final, "missing terminal result")):
            with self.subTest(expected=expected):
                parsed = parse_stream(stdout, "author")
                self.assertIsNotNone(parsed.error)
                self.assertIn(expected, parsed.error.detail)

    def test_parse_distinguishes_missing_and_duplicate_terminal_results(self):
        records = [json.loads(line) for line in _events().splitlines()]
        cases = ((records[:-1], "missing terminal result"),
                 (records + [records[-1]], "duplicate terminal result"))
        for events, expected in cases:
            with self.subTest(expected=expected):
                parsed = parse_stream("\n".join(json.dumps(event) for event in events), "author")
                self.assertIsNotNone(parsed.error)
                self.assertIn(expected, parsed.error.detail)

    def test_parse_preserves_immutable_rejected_evidence(self):
        stdout = _events() + "\n" + json.dumps({"type": "result", "session_id": "session-1", "structured_output": {"task_id": "t1", "attempt": 1, "outcome": "passed"}})
        parsed = parse_stream(stdout, "author", raw_stderr="captured stderr")
        self.assertIsNotNone(parsed.error)
        self.assertEqual(parsed.raw_stdout, stdout)
        self.assertEqual(parsed.raw_stderr, "captured stderr")
        self.assertEqual(len(parsed.events), 4)
        with self.assertRaises(TypeError):
            parsed.events[0]["session_id"] = "changed"

    def test_parse_rejection_evidence_is_archivable_for_representative_cases(self):
        records = [json.loads(line) for line in _events().splitlines()]
        missing_tool_id = records.copy()
        missing_tool_id[1] = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Agent", "input": {"subagent_type": "author"}}]}}
        bad_output = records.copy()
        bad_output[-1] = dict(bad_output[-1], structured_output={"task_id": "t1", "attempt": True, "outcome": "passed"})
        wrong_session = records.copy()
        wrong_session[-1] = dict(wrong_session[-1], session_id="other")
        cases = ((records[:1] + ["not-json"], 1, "malformed JSONL"),
                 (wrong_session, 3, "contradictory"), (missing_tool_id, 3, "native id"),
                 (bad_output, 3, "invalid structured_output"))
        for source, event_count, expected in cases:
            with self.subTest(expected=expected):
                stdout = "\n".join(item if isinstance(item, str) else json.dumps(item) for item in source)
                parsed = parse_stream(stdout, "author", raw_stderr=f"stderr-{expected}")
                self.assertIsNotNone(parsed.error)
                self.assertIn(expected, parsed.error.detail)
                self.assertEqual(parsed.raw_stdout, stdout)
                self.assertEqual(parsed.raw_stderr, f"stderr-{expected}")
                self.assertEqual(len(parsed.events), event_count)

    def test_duplicate_agent_wrong_session_missing_tool_id_and_bad_output_are_independent_blockers(self):
        records = [json.loads(line) for line in _events().splitlines()]
        duplicate_agent = records[:2] + [records[1]] + records[2:]
        wrong_session = records.copy()
        wrong_session[-1] = dict(wrong_session[-1], session_id="other")
        missing_tool_id = records.copy()
        missing_tool_id[1] = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Agent", "input": {"subagent_type": "author"}}]}}
        malformed_output = records.copy()
        malformed_output[-1] = dict(malformed_output[-1], structured_output={"task_id": "t1", "attempt": True, "outcome": "passed"})
        cases = ((duplicate_agent, "duplicate"), (wrong_session, "contradictory"),
                 (missing_tool_id, "native id"), (malformed_output, "invalid structured_output"))
        for events, expected in cases:
            with self.subTest(expected=expected):
                parsed = parse_stream("\n".join(json.dumps(event) for event in events), "author")
                self.assertIsNotNone(parsed.error)
                self.assertIn(expected, parsed.error.detail)

    def test_generated_agent_settings_reject_blank_or_inherit(self):
        for definition in ({"description": "W", "prompt": "P", "model": "inherit"},
                           {"description": "W", "prompt": "P", "effort": ""},
                           {"description": "W", "prompt": "P", "nested": {"model": " "}},
                           {"description": "W", "prompt": "P", "nested": {"model": ""}},
                           {"description": "W", "prompt": "P", "nested": {"effort": ""}},
                           {"description": "W", "prompt": "P", "nested": {"effort": "inherit"}}):
            with self.subTest(definition=definition), self.assertRaises(Blocked):
                self.transport.invoke("p", "sonnet", "medium", "author", definition, _schema())


if __name__ == "__main__":
    unittest.main()
