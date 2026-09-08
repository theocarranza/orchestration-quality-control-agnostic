import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from claude_adapter import ClaudeAdapter
from gate import AWAITING_USER_INPUT, RetryDecision, approve_answer
from mailbox import Mailbox
from qc_lib import Blocked
from oqc import drive
from compile_prompt import compile_brief
from kernel_specs import TaskDag, AgentSpec

def stream(session="s1", worker="author", result=None):
    result = result or {"task_id":"t1","attempt":1,"outcome":"passed"}
    return "\n".join(json.dumps(x) for x in ({"type":"system","subtype":"init","session_id":session},{"type":"assistant","message":{"content":[{"type":"tool_use","id":"u1","name":"Agent","input":{"subagent_type":worker}}]}},{"type":"result","session_id":session,"structured_output":result}))

class ClaudeAdapterTests(unittest.TestCase):
    def test_request_append_failure_restores_only_request_id(self):
        adapter = ClaudeAdapter(lambda argv: (0, stream(), ""), model="sonnet", effort="medium", worker_definitions={"author": {"description": "A", "prompt": "P"}})
        class RejectingBox:
            def read_all(self): return ()
            def append(self, value): raise Blocked(stage="x", reason_code="x", detail="reject", recovery_action="retry")
        with self.assertRaises(Blocked):
            adapter.spawn(RejectingBox(), run_id="r1", task_id="t1", attempt=1, agent_id="author", brief={})
        self.assertEqual(adapter._counter, 0)

    def test_transport_evidence_is_read_only_and_identity_metadata_is_authoritative(self):
        adapter = ClaudeAdapter(lambda argv: (0, stream(), ""), model="sonnet", effort="medium", worker_definitions={"author": {"description": "A", "prompt": "P"}})
        box = Mailbox()
        _, result = adapter.spawn(box, run_id="r1", task_id="t1", attempt=1, agent_id="author", brief={})
        self.assertEqual(result.sender, "agent:author")
        evidence = adapter.transport_evidence[0]
        self.assertEqual(evidence.native_session_id, "s1")
        self.assertEqual(evidence.worker_tool_use_id, "u1")
        self.assertEqual(evidence.adapter_identity, "claude-adapter")
        self.assertEqual(evidence.invocation, 1)
        with self.assertRaises(AttributeError):
            adapter.transport_evidence.append(None)

    def test_successful_result_adds_exact_engine_owned_execution_evidence(self):
        adapter = ClaudeAdapter(
            lambda argv: (0, stream(session="native-1"), ""), model="sonnet",
            effort="medium", worker_definitions={"author": {"description": "A", "prompt": "P"}},
        )
        _, result = adapter.spawn(Mailbox(), run_id="r1", task_id="t1", attempt=1,
                                 agent_id="author", brief={})
        self.assertEqual(result.payload["execution_evidence"], {
            "adapter_identity": "claude-adapter",
            "native_session_id": "native-1",
            "agent_id": "author",
            "agent_tool_use_id": "u1",
            "invocation_count": 1,
        })

    def test_runner_exception_evidence_is_a_frozen_value_snapshot(self):
        class MutableRunnerError(Exception):
            pass
        error = MutableRunnerError("runner failed")
        error.details = {"mutable": True}
        def runner(argv):
            raise error
        adapter = ClaudeAdapter(runner, model="sonnet", effort="medium",
                                worker_definitions={"author": {"description": "A", "prompt": "P"}})
        with self.assertRaises(Blocked):
            adapter.spawn(Mailbox(), run_id="r1", task_id="t1", attempt=1, agent_id="author", brief={})
        error.details["mutable"] = False
        snapshot = adapter.transport_evidence[-1].process_tuple
        self.assertEqual(dict(snapshot), {"exception_type": "MutableRunnerError", "message": "runner failed"})
        with self.assertRaises(TypeError):
            snapshot["message"] = "changed"

    def test_none_and_non_mapping_worker_definitions_are_blocked(self):
        for definitions in (None, (), [], "author"):
            with self.subTest(definitions=definitions), self.assertRaises(Blocked):
                ClaudeAdapter(lambda argv: (0, stream(), ""), model="sonnet", effort="medium",
                              worker_definitions=definitions)

    def test_worker_definition_mapping_is_isolated_from_caller_mutation(self):
        definitions = {"author": {"description": "A", "prompt": "P"}}
        adapter = ClaudeAdapter(lambda argv: (0, stream(), ""), model="sonnet", effort="medium",
                                worker_definitions=definitions)
        definitions.clear()
        _, result = adapter.spawn(Mailbox(), run_id="r1", task_id="t1", attempt=1,
                                 agent_id="author", brief={})
        self.assertEqual(result.payload["task_id"], "t1")

    def test_policy_requires_callable_mapping_and_freezes_nested_disclosure(self):
        with self.assertRaises(Blocked):
            ClaudeAdapter(lambda argv: (0, stream(), ""), model="sonnet", effort="medium", worker_definitions={"author": {}}, policy=object())
        adapter = ClaudeAdapter(lambda argv: (0, stream(), ""), model="sonnet", effort="medium", worker_definitions={"author": {}}, policy=lambda **kwargs: {"nested": {"ok": True}})
        disclosure = adapter.enforce_policy(run_id="r1", hook_name="pre-tool")
        with self.assertRaises(TypeError):
            disclosure["nested"]["ok"] = False

    def test_relay_question_requires_engine_waiting_state(self):
        from gate import RetryDecision, AWAITING_USER_INPUT
        adapter = ClaudeAdapter(lambda argv: (0, stream(), ""), model="sonnet", effort="medium", worker_definitions={"author": {}})
        decision = RetryDecision(action=AWAITING_USER_INPUT, task_id="t1", attempt=1, critique="bad", phase=AWAITING_USER_INPUT, attempts_remaining=1, question={"question_id": "q1", "prompt": "retry?"})
        with self.assertRaises(Blocked):
            adapter.relay_question(Mailbox(), run_id="r1", decision=decision)
    def test_composes_exact_request_session_and_stored_artifact(self):
        calls=[]
        def runner(argv):
            calls.append(argv); return 0, stream("s1" if len(calls)==1 else "s1", result={"task_id": "t1", "attempt": 1, "outcome": "passed", "artifact": "hello"}), ""
        with tempfile.TemporaryDirectory() as tmp:
            adapter=ClaudeAdapter(runner, model="sonnet", effort="medium", worker_definitions={"author":{"description":"A","prompt":"P"}}, artifact_dir=tmp)
            box=Mailbox(); out=adapter.spawn(box, run_id="r-artifact", task_id="t1", attempt=1, agent_id="author", brief={"z":1,"a":"x"})
            self.assertEqual(out[0].payload["brief_hash"], hashlib.sha256(b'{"a":"x","z":1}').hexdigest())
            self.assertEqual(Path(out[1].payload["artifact_path"]).read_bytes(), b"hello")
            self.assertEqual(out[1].payload["artifact_hash"], hashlib.sha256(b"hello").hexdigest())
            self.assertFalse(Path("r-artifact__t1__attempt-1.artifact").exists())
            self.assertNotIn("--resume", calls[0]); self.assertIsInstance(adapter.transport_evidence[0], object)

    def test_drive_accepts_adapter_artifact_metadata_and_stores_hashed_bytes(self):
        def runner(argv):
            return 0, stream(result={"task_id": "t1", "attempt": 1, "outcome": "passed", "artifact": "hello"}), ""
        dag = TaskDag.from_list([{"task_id": "t1", "role": "author", "depends_on": []}])
        specs = {"author": AgentSpec.from_dict({"schema_version": 1, "agent_id": "author", "role": "author", "capabilities": ["execute"], "tools": [], "output_schema": "schemas/worker-result.schema.json", "model_tier": "medium", "reasoning_effort": "medium"})}
        with tempfile.TemporaryDirectory() as artifact_dir:
            adapter = ClaudeAdapter(runner, model="sonnet", effort="medium", worker_definitions={"author": {"description": "A", "prompt": "P"}}, artifact_dir=artifact_dir)
            state = drive(dag, adapter, Mailbox(), specs, 1, run_id="r-artifact")
            path = Path(artifact_dir) / "r-artifact__t1__attempt-1.artifact"
            self.assertEqual(state.phase, "completed")
            self.assertEqual(path.read_bytes(), b"hello")
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), hashlib.sha256(b"hello").hexdigest())

    def test_result_append_rejection_rolls_back_new_artifact_and_result_id(self):
        class RejectResultBox:
            def __init__(self): self.entries = []
            def read_all(self): return tuple(self.entries)
            def append(self, value):
                if value.kind == "result":
                    raise Blocked(stage="test", reason_code="rejected", detail="reject result", recovery_action="retry")
                self.entries.append(value)
        with tempfile.TemporaryDirectory() as artifact_dir:
            adapter = ClaudeAdapter(lambda argv: (0, stream(result={"task_id": "t1", "attempt": 1, "outcome": "passed", "artifact": "hello"}), ""), model="sonnet", effort="medium", worker_definitions={"author": {"description": "A", "prompt": "P"}}, artifact_dir=artifact_dir)
            box = RejectResultBox()
            with self.assertRaises(Blocked):
                adapter.spawn(box, run_id="r1", task_id="t1", attempt=1, agent_id="author", brief={})
            self.assertEqual([entry.kind for entry in box.read_all()], ["request"])
            self.assertEqual(adapter._counter, 1)
            self.assertFalse((Path(artifact_dir) / "r1__t1__attempt-1.artifact").exists())

    def test_preexisting_artifact_path_is_never_overwritten_or_deleted(self):
        with tempfile.TemporaryDirectory() as artifact_dir:
            path = Path(artifact_dir) / "r1__t1__attempt-1.artifact"
            path.write_bytes(b"existing")
            adapter = ClaudeAdapter(lambda argv: (0, stream(result={"task_id": "t1", "attempt": 1, "outcome": "passed", "artifact": "new"}), ""), model="sonnet", effort="medium", worker_definitions={"author": {"description": "A", "prompt": "P"}}, artifact_dir=artifact_dir)
            box = Mailbox()
            with self.assertRaises(Blocked):
                adapter.spawn(box, run_id="r1", task_id="t1", attempt=1, agent_id="author", brief={})
            self.assertEqual(path.read_bytes(), b"existing")
            self.assertEqual([entry.kind for entry in box.read_all()], ["request"])
    def test_mismatch_appends_no_result_and_keeps_evidence(self):
        def runner(argv): return 0, stream(result={"task_id":"other","attempt":1,"outcome":"passed"}), "raw"
        adapter=ClaudeAdapter(runner, model="sonnet", effort="medium", worker_definitions={"author":{"description":"A","prompt":"P"}})
        box=Mailbox()
        with self.assertRaises(Blocked): adapter.spawn(box, run_id="r1", task_id="t1", attempt=1, agent_id="author", brief={})
        self.assertEqual([e.kind for e in box.read_all()], ["request"])
        self.assertTrue(adapter.transport_evidence)

    def test_wrong_worker_and_blank_tool_identity_leave_request_only_with_events(self):
        bad = stream(worker="other")
        bad = bad.replace('"id": "u1"', '"id": "   "')
        adapter = ClaudeAdapter(lambda argv: (0, bad, ""), model="sonnet", effort="medium", worker_definitions={"author":{"description":"A","prompt":"P"}})
        box = Mailbox()
        with self.assertRaises(Blocked):
            adapter.spawn(box, run_id="r1", task_id="t1", attempt=1, agent_id="author", brief={})
        self.assertEqual([entry.kind for entry in box.read_all()], ["request"])
        self.assertGreaterEqual(len(adapter.transport_evidence[-1].events), 2)

    def test_wrong_resumed_session_is_rejected_without_result(self):
        calls = []
        def runner(argv):
            calls.append(argv)
            return 0, stream("s1" if len(calls) == 1 else "s2"), "stderr"
        adapter = ClaudeAdapter(runner, model="sonnet", effort="medium", worker_definitions={"author":{"description":"A","prompt":"P"}})
        box = Mailbox()
        adapter.spawn(box, run_id="r1", task_id="t1", attempt=1, agent_id="author", brief={})
        with self.assertRaises(Blocked):
            adapter.spawn(box, run_id="r1", task_id="t1", attempt=2, agent_id="author", brief={})
        self.assertEqual([entry.kind for entry in box.read_all()], ["request", "result", "request"])
        self.assertIn("--resume", calls[1])
        self.assertEqual(adapter.transport_evidence[-1].raw_stderr, "stderr")

    def test_rejection_evidence_keeps_raw_process_tuple_and_is_immutable(self):
        raw = (1, stream(), "stderr")
        def runner(argv): return raw
        adapter=ClaudeAdapter(runner, model="sonnet", effort="medium", worker_definitions={"author":{"description":"A","prompt":"P"}})
        box=Mailbox()
        with self.assertRaises(Blocked): adapter.spawn(box, run_id="r1", task_id="t1", attempt=1, agent_id="author", brief={})
        evidence = adapter.transport_evidence[-1]
        self.assertEqual(evidence.process_tuple, raw)
        self.assertEqual(evidence.raw_stdout, raw[1]); self.assertEqual(evidence.raw_stderr, "stderr")
        self.assertEqual([e.kind for e in box.read_all()], ["request"])

    def test_append_failure_does_not_consume_counter(self):
        adapter=ClaudeAdapter(lambda argv: (0, stream(), ""), model="sonnet", effort="medium", worker_definitions={"author":{"description":"A","prompt":"P"}})
        box=Mailbox()
        class BadBox:
            def read_all(self): return box.read_all()
            def append(self, value): raise Blocked(stage="x", reason_code="x", detail="reject", recovery_action="retry")
        before=adapter._counter
        with self.assertRaises(Blocked): adapter.emit_status(BadBox(), run_id="r1", phase="working")
        self.assertEqual(adapter._counter, before)

    def test_drive_retry_uses_one_native_session_and_resume(self):
        calls=[]
        def runner(argv):
            calls.append(argv)
            attempt=1 if len(calls)==1 else 2
            return 0, stream(result={"task_id":"t1","attempt":attempt,"outcome":"failed" if attempt==1 else "passed", **({"critique":"retry"} if attempt==1 else {})}), ""
        from mailbox import Mailbox
        from oqc import drive
        dag=TaskDag.from_list([{"task_id":"t1","role":"author","depends_on":[]}])
        specs={"author": AgentSpec.from_dict({"schema_version":1,"agent_id":"author","role":"author","capabilities":["execute"],"tools":[],"output_schema":"schemas/worker-result.schema.json","model_tier":"medium","reasoning_effort":"medium"})}
        with tempfile.TemporaryDirectory() as artifact_dir:
            adapter=ClaudeAdapter(runner, model="sonnet", effort="medium", worker_definitions={"author":{"description":"A","prompt":"P"}}, artifact_dir=artifact_dir)
            state=drive(dag, adapter, Mailbox(), specs, 2, run_id="r-drive")
            self.assertEqual(state.phase, "completed")
            self.assertEqual(len(calls), 2)
            self.assertIn("--resume", calls[1])
            self.assertEqual(adapter.transport_evidence[0].response.session_id, adapter.transport_evidence[1].response.session_id)
            self.assertEqual(list(Path(artifact_dir).iterdir()), [])
            self.assertFalse(Path("r-drive__t1__attempt-1.artifact").exists())

    def test_all_port_operations_append_engine_bound_envelopes_and_freeze_policy(self):
        from run_state import reduce
        adapter = ClaudeAdapter(
            lambda argv: (0, stream(result={"task_id": "t1", "attempt": 1, "outcome": "failed", "critique": "need input"}), ""), model="sonnet", effort="medium",
            worker_definitions={"author": {"description": "A", "prompt": "P"}},
            policy=lambda **kwargs: {"native_enforcement": False, "context": {"run": kwargs["run_id"]}},
        )
        box = Mailbox()
        adapter.spawn(box, run_id="r1", task_id="t1", attempt=1, agent_id="author", brief={})
        status = adapter.emit_status(box, run_id="r1", phase=AWAITING_USER_INPUT, context={
            "task_id": "t1", "attempt": 1, "critique": "need input", "attempts_remaining": 1,
            "question_id": "q1", "prompt": "Continue?",
        })
        self.assertEqual((status.sender, status.recipient, status.kind, dict(status.payload)), (
            "orchestrator", "root", "status", {
                "task_id": "t1", "attempt": 1, "critique": "need input", "attempts_remaining": 1,
                "question_id": "q1", "prompt": "Continue?", "phase": AWAITING_USER_INPUT,
            },
        ))
        question_decision = RetryDecision(
            action=AWAITING_USER_INPUT, task_id="t1", attempt=1, critique="need input",
            phase=AWAITING_USER_INPUT, attempts_remaining=1,
            question={"question_id": "q1", "prompt": "Continue?"},
        )
        question = adapter.relay_question(box, run_id="r1", decision=question_decision)
        self.assertEqual((question.sender, question.recipient, question.kind, dict(question.payload)), (
            "orchestrator", "root", "question", {
                "task_id": "t1", "attempt": 1, "critique": "need input", "attempts_remaining": 1,
                "question_id": "q1", "prompt": "Continue?",
            },
        ))
        answer_raw = {"run_id": "r1", "task_id": "t1", "attempt": 1, "question_id": "q1", "decision": "retry", "text": "yes"}
        answer_decision = approve_answer(reduce(box.read_all()), answer_raw)
        answer = adapter.relay_answer(box, answer=answer_decision)
        self.assertEqual((answer.sender, answer.recipient, answer.kind, dict(answer.payload)), (
            "root", "orchestrator", "answer", answer_raw,
        ))
        disclosure = adapter.enforce_policy(run_id="r1", hook_name="PreToolUse", context={"tool": "Agent"})
        self.assertEqual(dict(disclosure), {"native_enforcement": False, "context": {"run": "r1"}})
        with self.assertRaises(TypeError):
            disclosure["context"]["run"] = "tampered"

    def test_runner_argv_is_exact_and_cannot_select_another_worker(self):
        calls = []
        workers = {
            "author": {"description": "Author definition", "prompt": "Write exactly."},
            "reviewer": {"description": "Reviewer definition", "prompt": "Review exactly."},
        }
        adapter = ClaudeAdapter(lambda argv: (calls.append(argv) or (0, stream(), "")), model="sonnet", effort="medium", worker_definitions=workers)
        box = Mailbox()
        request, _ = adapter.spawn(box, run_id="r1", task_id="t1", attempt=1, agent_id="author", brief={"z": 1, "a": "x"})
        argv = calls[0]
        self.assertEqual(argv[0:9], ("claude", "--print", "--model", "sonnet", "--effort", "medium", "--tools", "Agent", "--allowed-tools"))
        self.assertEqual(argv[9], "Agent(author)")
        self.assertEqual(argv[10:12], ("--agents", '{"author":{"description":"Author definition","prompt":"Write exactly."}}'))
        self.assertEqual(argv[12], "--json-schema")
        self.assertEqual(json.loads(argv[13])["required"], ["task_id", "attempt", "outcome"])
        self.assertEqual(argv[-1], '{"a":"x","z":1}')
        self.assertEqual((request.recipient, request.payload["brief"]), ("agent:author", {"z": 1, "a": "x"}))
        self.assertNotIn("reviewer", argv[11])

    def test_rejected_parseable_evidence_retains_immutable_native_identity_and_process_shape(self):
        raw = (1, stream(session="s1", worker="other"), "transport stderr")
        adapter = ClaudeAdapter(lambda argv: raw, model="sonnet", effort="medium", worker_definitions={"author": {"description": "A", "prompt": "P"}})
        with self.assertRaises(Blocked):
            adapter.spawn(Mailbox(), run_id="r1", task_id="t1", attempt=1, agent_id="author", brief={})
        evidence = adapter.transport_evidence
        self.assertIsInstance(evidence, tuple)
        self.assertEqual(evidence[-1].process_tuple, raw)
        self.assertEqual((evidence[-1].raw_stdout, evidence[-1].raw_stderr), (raw[1], raw[2]))
        self.assertEqual(evidence[-1].events[0]["session_id"], "s1")
        self.assertEqual(evidence[-1].events[1]["message"]["content"][0]["name"], "Agent")
        self.assertEqual(evidence[-1].events[1]["message"]["content"][0]["input"]["subagent_type"], "other")
        with self.assertRaises(TypeError):
            evidence[-1].process_tuple[0] = 0
        with self.assertRaises(TypeError):
            evidence[-1].events[1]["message"]["content"][0]["input"]["subagent_type"] = "author"
        with self.assertRaises(TypeError):
            evidence[0] = None

if __name__ == "__main__": unittest.main()
