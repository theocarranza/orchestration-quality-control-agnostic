import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from claude_adapter import ClaudeAdapter
from compile_workflow import compile_workflow
from gate import approve_answer
from mailbox import Mailbox
from oqc import drive, resume
from orchestrator_contract import compile_orchestrator
from qc_lib import Blocked


def _stream(session, worker, result, tool_id):
    return "\n".join(json.dumps(item) for item in (
        {"type": "system", "subtype": "init", "session_id": session},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": tool_id, "name": "Agent", "input": {"subagent_type": worker}}]}},
        {"type": "result", "session_id": session, "structured_output": result},
    ))


def _fixture():
    compiled = compile_workflow({"run_id": "capture-run", "created_at": "2026-09-08T12:00:00Z", "outcome": "capture", "shape": "isolated-workers", "named_inputs": ["one", "two"], "outcome_involves_test_tree": False, "profile": "core"})
    contract = compile_orchestrator(compiled, 2)
    tasks = [node.task_id for node in contract.task_dag.tasks]
    workers = {spec.agent_id: {"description": "generated", "prompt": "work", "model": "claude-opus-4-6", "effort": "medium", "tools": []} for spec in contract.agent_specs.values()}
    calls = []
    def runner(argv):
        calls.append(argv); index = len(calls); worker = argv[argv.index("--allowed-tools") + 1][6:-1]
        if index == 1:
            result = {"task_id": tasks[0], "attempt": 1, "outcome": "failed", "critique": "need approval", "question": {"question_id": "q-1", "prompt": "retry?"}, "artifact": "first artifact"}
        elif index == 2:
            result = {"task_id": tasks[0], "attempt": 2, "outcome": "passed", "artifact": "second artifact"}
        else:
            result = {"task_id": tasks[1], "attempt": 1, "outcome": "passed"}
        return 0, _stream("native-session", worker, result, f"tool-{index}"), ""
    return contract, workers, runner, tasks


class CaptureArchiveTests(unittest.TestCase):
    def _rehash(self, root, name):
        manifest = json.loads((root / "manifest.json").read_text())
        manifest["files"][name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
        (root / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
    def _capture(self, directory):
        import claude_capture
        contract, workers, runner, tasks = _fixture()
        with tempfile.TemporaryDirectory() as artifact_dir:
            adapter = ClaudeAdapter(runner, model="claude-opus-4-6", effort="medium", worker_definitions=workers, artifact_dir=artifact_dir)
            mailbox = Mailbox()
            waiting = drive(contract.task_dag, adapter, mailbox, contract.agent_specs, contract.max_attempts, run_id=contract.run_spec.run_id)
            answer = {"run_id": "capture-run", "task_id": tasks[0], "attempt": 1, "question_id": "q-1", "decision": "retry", "text": "yes"}
            self.assertEqual(resume(contract.task_dag, adapter, mailbox, contract.agent_specs, contract.max_attempts, answer=answer).phase, "completed")
            return claude_capture.capture(contract, mailbox, adapter.transport_evidence, artifact_dir, Path(directory) / "capture", provenance=claude_capture.recorded_test_provenance())

    def test_recorded_task4_round_trip_and_live_rejection(self):
        import claude_capture
        with tempfile.TemporaryDirectory() as directory:
            root = self._capture(directory)
            self.assertEqual(claude_capture.verify_capture(root).state.phase, "completed")
            with self.assertRaises(Blocked): claude_capture.verify_capture(root, live_acceptance=True)

    def test_external_anchor_and_final_mailbox_tampering_are_blocked(self):
        import claude_capture
        with tempfile.TemporaryDirectory() as directory:
            root = self._capture(directory); (root / "mailbox-head.json").write_text('{"head_hash":"bad"}\n')
            with self.assertRaises(Blocked): claude_capture.verify_capture(root)
        with tempfile.TemporaryDirectory() as directory:
            root = self._capture(directory); lines = (root / "mailbox.jsonl").read_text().splitlines(); final = json.loads(lines[-1]); final["payload"] = {"phase": "blocked"}; lines[-1] = json.dumps(final, sort_keys=True, separators=(",", ":")); (root / "mailbox.jsonl").write_text("\n".join(lines) + "\n")
            with self.assertRaises(Blocked): claude_capture.verify_capture(root)

    def test_artifact_manifest_and_membership_tampering_are_blocked(self):
        import claude_capture
        with tempfile.TemporaryDirectory() as directory:
            root = self._capture(directory); next(root.glob("artifact-*.bin")).write_bytes(b"tampered")
            with self.assertRaises(Blocked): claude_capture.verify_capture(root)
        with tempfile.TemporaryDirectory() as directory:
            root = self._capture(directory); manifest = json.loads((root / "manifest.json").read_text()); manifest["files"]["contract.json"] = "0" * 64; (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaises(Blocked): claude_capture.verify_capture(root)
        with tempfile.TemporaryDirectory() as directory:
            root = self._capture(directory); (root / "unexpected").write_text("x")
            with self.assertRaises(Blocked): claude_capture.verify_capture(root)

    def test_transport_and_mailbox_identity_invariants_are_checked(self):
        import claude_capture
        cases = (("recipient", lambda record: record["response"].__setitem__("sender", "agent:wrong")), ("session", lambda record: record.__setitem__("native_session_id", "other")), ("tool", lambda record: record.__setitem__("worker_tool_use_id", "tool-1")), ("gap", lambda record: record.__setitem__("invocation", 9)))
        for label, alter in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = self._capture(directory); records = [json.loads(line) for line in (root / "transport.jsonl").read_text().splitlines()]; alter(records[-1]); (root / "transport.jsonl").write_text("\n".join(json.dumps(x) for x in records) + "\n")
                with self.assertRaises(Blocked): claude_capture.verify_capture(root)

    def test_root_boundary_and_complete_semantics_are_checked(self):
        import claude_capture
        with tempfile.TemporaryDirectory() as directory:
            root = self._capture(directory); lines = (root / "mailbox.jsonl").read_text().splitlines(); request = json.loads(lines[0]); request["sender"] = "root"; lines[0] = json.dumps(request, sort_keys=True, separators=(",", ":")); (root / "mailbox.jsonl").write_text("\n".join(lines) + "\n")
            with self.assertRaises(Blocked): claude_capture.verify_capture(root)
        with tempfile.TemporaryDirectory() as directory:
            root = self._capture(directory); (root / "COMPLETE").write_text("partial\n")
            with self.assertRaises(Blocked): claude_capture.verify_capture(root)

    def test_task5b_seam_is_not_invoked(self):
        import claude_capture
        calls = []; seam = claude_capture.compile_task_5b_seam(lambda argv: calls.append(argv))
        self.assertEqual(calls, []); self.assertEqual(len(seam.contract.task_dag.tasks), 2)
        self.assertTrue(all(spec.tools == () for spec in seam.contract.agent_specs.values()))
        self.assertEqual([step["outcome"] for step in seam.fixture], ["failed", "retry", "passed", "passed"])

    def test_missing_invalid_and_out_of_order_answers_are_blocked(self):
        import claude_capture
        for label, alter in (
            ("missing", lambda lines, index: lines.pop(index)),
            ("invalid", lambda item: item["payload"].__setitem__("text", "")),
            ("out-of-order", lambda item: item["payload"].__setitem__("question_id", "wrong")),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = self._capture(directory); lines = (root / "mailbox.jsonl").read_text().splitlines()
                index = next(i for i, line in enumerate(lines) if json.loads(line)["kind"] == "answer")
                if label == "missing": alter(lines, index)
                else:
                    item = json.loads(lines[index]); alter(item); lines[index] = json.dumps(item, sort_keys=True, separators=(",", ":"))
                (root / "mailbox.jsonl").write_text("\n".join(lines) + "\n"); self._rehash(root, "mailbox.jsonl")
                with self.assertRaises(Blocked): claude_capture.verify_capture(root)

    def test_transport_recipient_agent_and_artifact_payload_binding_are_blocked(self):
        import claude_capture
        cases = (
            ("request-recipient", lambda records: records[0]["request"].__setitem__("recipient", "agent:wrong")),
            ("agent-evidence", lambda records: records[0]["response"]["payload"]["execution_evidence"].__setitem__("agent_id", "wrong")),
            ("duplicate-agent", lambda records: records[-1].__setitem__("worker_tool_use_id", records[0]["worker_tool_use_id"])),
            ("artifact-hash", lambda records: records[0]["response"]["payload"].__setitem__("artifact_hash", "0" * 64)),
        )
        for label, alter in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = self._capture(directory); records = [json.loads(line) for line in (root / "transport.jsonl").read_text().splitlines()]
                alter(records); (root / "transport.jsonl").write_text("\n".join(json.dumps(record) for record in records) + "\n"); self._rehash(root, "transport.jsonl")
                with self.assertRaises(Blocked): claude_capture.verify_capture(root)

    def test_missing_required_files_manifest_field_and_complete_are_blocked(self):
        import claude_capture
        for label, alter in (
            ("file", lambda root: (root / "contract.json").unlink()),
            ("manifest", lambda root: (root / "manifest.json").write_text(json.dumps({key: value for key, value in json.loads((root / "manifest.json").read_text()).items() if key != "provenance"}))),
            ("complete", lambda root: (root / "COMPLETE").unlink()),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = self._capture(directory); alter(root)
                with self.assertRaises(Blocked): claude_capture.verify_capture(root)


if __name__ == "__main__":
    unittest.main()
