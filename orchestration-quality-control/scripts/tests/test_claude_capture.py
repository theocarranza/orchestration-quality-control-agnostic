import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claude_adapter import ClaudeAdapter
from claude_transport import ClaudeTransport
from compile_workflow import compile_workflow
from gate import approve_answer
from mailbox import Mailbox
from oqc import drive, resume
from orchestrator_contract import compile_orchestrator
from qc_lib import Blocked, thaw


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
            result = {"task_id": tasks[1], "attempt": 1, "outcome": "passed", "artifact": "third artifact"}
        return 0, _stream("native-session", worker, result, f"tool-{index}"), ""
    return contract, workers, runner, tasks


def _native_event_stream(*, worker, session_id, model, tool_use_id="toolu_agent_1",
                          structured_tool_id="toolu_structured_1", total_tool_use_count=0,
                          worker_text="Grounded analysis with no tool calls.",
                          orchestrator_extra_tool_use=None, structured_output=None,
                          hook_agent_outcome="success", hook_structured_outcome="success"):
    """Build one invocation's raw_stdout JSONL text.

    Event vocabulary (types, keys, tool_use/tool_use_result shapes, and the flat
    hook_name/hook_event/outcome/exit_code keys) is grounded in the real archived
    Claude Code 2.1.234 stream at
    AI_Codex/Agent_Evidence/2026-09-08-task5b-live/transport.jsonl, trimmed to the
    subset that drives parse_stream and _validate_native_live_evidence. That real
    stream is also where the two fabricated-tool-call markers this helper can
    inject ("<tool_use" and "<tool_result") were themselves observed: two of its
    three worker invocations hallucinated exactly this markup inside their own
    tool_use_result text instead of actually calling a tool.
    """
    structured_output = structured_output or {"task_id": "task-first", "attempt": 1, "outcome": "passed"}
    events = [
        {"type": "system", "subtype": "init", "session_id": session_id, "model": model},
        {"type": "assistant", "session_id": session_id, "message": {
            "role": "assistant", "model": model,
            "content": [{"type": "text", "text": "Dispatching to the worker."}],
        }},
    ]
    if orchestrator_extra_tool_use is not None:
        events.append({"type": "assistant", "session_id": session_id, "message": {
            "role": "assistant", "model": model, "content": [orchestrator_extra_tool_use],
        }})
    events += [
        {"type": "assistant", "session_id": session_id, "message": {
            "role": "assistant", "model": model,
            "content": [{"type": "tool_use", "id": tool_use_id, "name": "Agent",
                          "input": {"subagent_type": worker, "description": "Execute worker task", "prompt": "worker brief"}}],
        }},
        {"type": "system", "hook_name": "PreToolUse:Agent", "hook_event": "PreToolUse", "session_id": session_id, "subtype": "hook_started"},
        {"type": "system", "hook_name": "PreToolUse:Agent", "hook_event": "PreToolUse", "outcome": hook_agent_outcome, "exit_code": 0, "session_id": session_id, "subtype": "hook_response"},
        {"type": "user", "session_id": session_id, "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tool_use_id, "content": [{"type": "text", "text": worker_text}]},
        ]}, "tool_use_result": {
            "agentId": "worker-run-1", "agentType": worker, "status": "completed",
            "totalToolUseCount": total_tool_use_count,
            "content": [{"type": "text", "text": worker_text}],
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }},
        {"type": "assistant", "session_id": session_id, "message": {
            "role": "assistant", "model": model,
            "content": [{"type": "text", "text": "Worker completed with a grounded schema-valid result."}],
        }},
        {"type": "assistant", "session_id": session_id, "message": {
            "role": "assistant", "model": model,
            "content": [{"type": "tool_use", "id": structured_tool_id, "name": "StructuredOutput", "input": dict(structured_output)}],
        }},
        {"type": "system", "hook_name": "PreToolUse:StructuredOutput", "hook_event": "PreToolUse", "session_id": session_id, "subtype": "hook_started"},
        {"type": "system", "hook_name": "PreToolUse:StructuredOutput", "hook_event": "PreToolUse", "outcome": hook_structured_outcome, "exit_code": 0, "session_id": session_id, "subtype": "hook_response"},
        {"type": "user", "session_id": session_id, "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": structured_tool_id, "content": "Structured output provided successfully"},
        ]}, "tool_use_result": "Structured output provided successfully"},
        {"type": "result", "session_id": session_id, "structured_output": structured_output},
    ]
    return "\n".join(json.dumps(event, sort_keys=True) for event in events)


def _native_record(raw_stdout, *, worker, model, effort, worker_definition):
    """Drive the real ClaudeTransport over a canned raw_stdout to get an internally
    consistent native-shaped transport record (argv/settings/schema and prompt
    hashes are all host-generated, not hand-typed, so they cannot silently drift
    from what _validate_native_live_evidence itself recomputes)."""
    def runner(argv):
        return 0, raw_stdout, ""
    result = ClaudeTransport(runner).invoke(
        json.dumps({"engine_brief": True}, sort_keys=True), model, effort, worker, worker_definition,
    )
    return {
        "request": {"recipient": f"agent:{worker}"},
        "argv": list(result.argv),
        "settings": thaw(result.settings),
        "worker_definition": thaw(result.worker_definition),
        "schema_sha256": result.schema_sha256,
        "prompt_sha256": result.prompt_sha256,
        "raw_stdout": result.raw_stdout,
        "raw_stderr": result.raw_stderr,
        "process_tuple": [0, result.raw_stdout, result.raw_stderr],
        "model": model,
        "effort": effort,
        "events": list(result.events),
    }


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

    def test_live_acceptance_rejects_empty_archived_artifact_bytes(self):
        import claude_capture
        with tempfile.TemporaryDirectory() as directory:
            root = self._capture(directory)
            manifest = json.loads((root / "manifest.json").read_text())
            manifest["provenance"] = "native"
            artifact = root / manifest["artifacts"][0]["path"]
            artifact.write_bytes(b"")
            manifest["files"][artifact.name] = hashlib.sha256(artifact.read_bytes()).hexdigest()
            (root / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
            with self.assertRaises(Blocked):
                claude_capture.verify_capture(root, live_acceptance=True)

    def test_live_acceptance_with_native_provenance_actually_invokes_native_evidence_validation(self):
        """Guard against _validate_native_live_evidence going unreachable again.

        A prior version of this function was pure dead code: every existing
        live_acceptance=True test was rejected earlier (provenance label or
        _validate_live_artifacts), so nothing ever called it. This spies on the
        real function (wraps=, not a stub) so it still runs its real checks and
        still blocks this non-native-shaped recorded fixture -- the point is
        proving the call happens at all, not what it decides.
        """
        import claude_capture
        with tempfile.TemporaryDirectory() as directory:
            root = self._capture(directory)
            manifest = json.loads((root / "manifest.json").read_text())
            manifest["provenance"] = "native"
            (root / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
            original = claude_capture._validate_native_live_evidence
            with patch("claude_capture._validate_native_live_evidence", wraps=original) as spy:
                with self.assertRaises(Blocked):
                    claude_capture.verify_capture(root, live_acceptance=True)
            self.assertEqual(spy.call_count, 1)

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
        self.assertEqual(seam.contract.task_dag.tasks[1].depends_on, (seam.contract.task_dag.tasks[0].task_id,))
        self.assertTrue(all(spec.tools == () for spec in seam.contract.agent_specs.values()))
        self.assertEqual([step["outcome"] for step in seam.fixture], ["failed", "retry", "passed", "passed"])

    def test_task5b_native_seam_binds_real_runner_and_artifact_directory(self):
        import claude_capture
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory) / "artifacts"
            seam = claude_capture.compile_task_5b_seam(artifact_dir=artifact_dir)
            self.assertEqual(seam.adapter._artifact_dir, artifact_dir)
            self.assertTrue(claude_capture._is_native_task_5b_seam(seam))

    def test_task5b_generated_worker_prompt_declares_observable_lifecycle(self):
        import claude_capture
        from mailbox import Mailbox
        from qc_lib import Blocked

        calls = []
        seam = claude_capture.compile_task_5b_seam(lambda argv: (calls.append(argv), (1, "", ""))[1])
        first_node, second_node = seam.contract.task_dag.tasks
        first, second = first_node.task_id, second_node.task_id
        worker = seam.contract.agent_specs[first_node.role].agent_id
        with self.assertRaises(Blocked):
            seam.adapter.spawn(Mailbox(), run_id=seam.contract.run_spec.run_id,
                               task_id=first, attempt=1, agent_id=worker,
                               brief={"task_id": first, "attempt": 1})
        self.assertEqual(len(calls), 1)
        agents = json.loads(calls[0][calls[0].index("--agents") + 1])
        prompt = agents[worker]["prompt"]
        self.assertIn(f"task_id {first}", prompt)
        self.assertIn("attempt 1 must return outcome 'failed'", prompt)
        self.assertIn("task5b-q1", prompt)
        self.assertIn("Retry first worker?", prompt)
        self.assertIn("attempt 2 must return outcome 'passed' only when answer_context contains the approved retry", prompt)
        self.assertIn("nonblank artifact string", prompt)
        self.assertEqual(agents[worker]["disallowedTools"], list(claude_capture._WORKER_DISALLOWED_TOOLS))
        second_worker = seam.contract.agent_specs[second_node.role].agent_id
        with self.assertRaises(Blocked):
            seam.adapter.spawn(Mailbox(), run_id=seam.contract.run_spec.run_id,
                               task_id=second, attempt=1, agent_id=second_worker,
                               brief={"task_id": second, "attempt": 1})
        second_agents = json.loads(calls[1][calls[1].index("--agents") + 1])
        second_prompt = second_agents[second_worker]["prompt"]
        self.assertIn(f"task_id {second}", second_prompt)
        self.assertIn(f"after task_id {first} has passed", second_prompt)
        self.assertIn("nonblank artifact string", second_prompt)

    def test_task5b_generated_worker_prompts_forbid_critique_and_question_on_passed_result(self):
        """gate.py's gate_result rejects any passed result that still carries
        'critique' or 'question' (gate.py:174-178). The real live run proved
        a compliant worker will carry both fields forward from a prior failed
        attempt unless the prompt explicitly tells it to drop them. Both
        generated worker prompts -- worker one, which fails then passes, and
        worker two, which always passes -- must state that a passing result
        contains only task_id, attempt, outcome, and artifact."""
        import claude_capture
        seam = claude_capture.compile_task_5b_seam(lambda argv: None)
        first_node, second_node = seam.contract.task_dag.tasks
        first_worker = seam.contract.agent_specs[first_node.role].agent_id
        second_worker = seam.contract.agent_specs[second_node.role].agent_id
        for worker in (first_worker, second_worker):
            prompt = seam.adapter._workers[worker]["prompt"]
            self.assertIn(
                "a passed result must include only task_id, attempt, outcome, "
                "and artifact, and must never include critique or question",
                prompt,
            )

    def test_task5b_generated_worker_prompts_forbid_fabricated_tool_call_markup(self):
        """Both generated worker prompts must explicitly forbid the exact
        hallucination the real archived capture caught two workers doing:
        fabricating tool-call/tool-output markup and narrating invented tool
        output instead of answering directly. The prompt text itself must
        never contain the literal '<tool_use' / '<tool_result' character
        sequences -- writing them into the prompt primes a compliant worker
        to echo the very substring the anti-fabrication check watches for."""
        import claude_capture
        seam = claude_capture.compile_task_5b_seam(lambda argv: None)
        first_node, second_node = seam.contract.task_dag.tasks
        first_worker = seam.contract.agent_specs[first_node.role].agent_id
        second_worker = seam.contract.agent_specs[second_node.role].agent_id
        for worker in (first_worker, second_worker):
            prompt = seam.adapter._workers[worker]["prompt"]
            self.assertIn("Never fabricate or transcribe any tool-call or tool-output markup", prompt)
            self.assertIn("never narrate, simulate, or invent a tool call or its output", prompt)
            self.assertIn("answer directly from this prompt with a schema-valid result", prompt)
            self.assertNotIn("<tool_use", prompt)
            self.assertNotIn("<tool_result", prompt)

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


class NativeLiveEvidenceTests(unittest.TestCase):
    """Direct coverage for _validate_native_live_evidence.

    Its only caller (verify_capture with live_acceptance=True) was never reached
    by any existing test: every prior fixture was rejected earlier, at the
    provenance-label check or inside _validate_live_artifacts. These tests call
    it directly with a realistic native-shaped record -- built by driving the
    real ClaudeTransport (so argv/settings/schema and prompt hashes are
    host-generated, not hand-typed) over a raw_stdout event stream modeled on
    the real archived capture -- so every branch actually executes.
    """

    WORKER = "agent-author-first"
    MODEL = "claude-opus-4-6"
    EFFORT = "medium"
    SESSION = "native-golden-session"

    def _contract(self):
        import claude_capture
        return claude_capture.compile_task_5b_seam(lambda argv: None).contract

    def _definition(self):
        import claude_capture
        return {
            "description": "generated isolated worker for the first task",
            "prompt": "Return only schema-valid output; do not read files or schemas.",
            "model": self.MODEL,
            "effort": self.EFFORT,
            "tools": [],
            "disallowedTools": list(claude_capture._WORKER_DISALLOWED_TOOLS),
        }

    def _record(self, **stream_overrides):
        stream_overrides.setdefault("worker", self.WORKER)
        stream_overrides.setdefault("session_id", self.SESSION)
        stream_overrides.setdefault("model", self.MODEL)
        raw_stdout = _native_event_stream(**stream_overrides)
        return _native_record(raw_stdout, worker=stream_overrides["worker"], model=self.MODEL,
                               effort=self.EFFORT, worker_definition=self._definition())

    def _clean_record(self):
        return self._record()

    def _validate(self, records):
        import claude_capture
        claude_capture._validate_native_live_evidence(records, self._contract())

    def test_accepts_a_realistic_grounded_native_record(self):
        self._validate([self._clean_record()])

    def test_rejects_non_list_argv_or_non_mapping_settings_or_definition(self):
        base = self._clean_record()
        cases = (
            ("argv-not-list", {"argv": tuple(base["argv"])}),
            ("settings-not-dict", {"settings": None}),
            ("worker-definition-not-dict", {"worker_definition": None}),
        )
        for label, override in cases:
            with self.subTest(label=label):
                with self.assertRaises(Blocked):
                    self._validate([{**base, **override}])

    def test_rejects_schema_or_prompt_hash_binding_mismatch(self):
        base = self._clean_record()
        cases = (
            ("wrong-schema-hash", {"schema_sha256": "0" * 64}),
            ("prompt-hash-wrong-length", {"prompt_sha256": "short"}),
            ("prompt-hash-not-string", {"prompt_sha256": 12345}),
        )
        for label, override in cases:
            with self.subTest(label=label):
                with self.assertRaises(Blocked):
                    self._validate([{**base, **override}])

    def test_rejects_argv_not_binding_the_exact_invocation_prompt(self):
        base = self._clean_record()
        argv_wrong_executable = list(base["argv"]); argv_wrong_executable[0] = "not-claude"
        argv_blank_prompt = list(base["argv"]); argv_blank_prompt[-1] = ""
        argv_unbound_prompt = list(base["argv"]); argv_unbound_prompt[-1] = "a prompt the hash was never computed from"
        cases = (
            ("too-short", {"argv": ["claude"]}),
            ("wrong-executable", {"argv": argv_wrong_executable}),
            ("blank-prompt", {"argv": argv_blank_prompt}),
            ("unbound-prompt", {"argv": argv_unbound_prompt}),
        )
        for label, override in cases:
            with self.subTest(label=label):
                with self.assertRaises(Blocked):
                    self._validate([{**base, **override}])

    def test_rejects_argv_not_binding_model_effort_or_agent_only_registration(self):
        base = self._clean_record()
        argv_wrong_model = list(base["argv"]); argv_wrong_model[argv_wrong_model.index("--model") + 1] = "wrong-model"
        argv_wrong_allowed = list(base["argv"]); argv_wrong_allowed[argv_wrong_allowed.index("--allowed-tools") + 1] = "Agent(someone-else)"
        cases = (
            ("model-flag", {"argv": argv_wrong_model}),
            ("allowed-tools-flag", {"argv": argv_wrong_allowed}),
        )
        for label, override in cases:
            with self.subTest(label=label):
                with self.assertRaises(Blocked):
                    self._validate([{**base, **override}])

    def test_rejects_worker_definition_that_is_not_host_effectively_tool_free(self):
        base = self._clean_record()
        definition_with_tools = dict(base["worker_definition"]); definition_with_tools["tools"] = ["Bash"]
        definition_wrong_disallowed = dict(base["worker_definition"]); definition_wrong_disallowed["disallowedTools"] = []
        cases = (
            ("tools-nonempty", {"worker_definition": definition_with_tools}),
            ("disallowedTools-wrong", {"worker_definition": definition_wrong_disallowed}),
        )
        for label, override in cases:
            with self.subTest(label=label):
                with self.assertRaises(Blocked):
                    self._validate([{**base, **override}])

    def test_rejects_agents_flag_that_differs_from_the_archived_definition(self):
        base = self._clean_record()
        definition = dict(base["worker_definition"]); definition["description"] = "never sent to the host"
        with self.assertRaises(Blocked):
            self._validate([{**base, "worker_definition": definition}])

    def test_rejects_agents_flag_that_is_missing_from_argv(self):
        base = self._clean_record()
        argv_missing_agents = list(base["argv"])
        index = argv_missing_agents.index("--agents"); del argv_missing_agents[index:index + 2]
        with self.assertRaises(Blocked):
            self._validate([{**base, "argv": argv_missing_agents}])

    def test_rejects_settings_flag_that_is_missing_or_differs_from_archived_settings(self):
        base = self._clean_record()
        drifted_settings = dict(base["settings"]); drifted_settings["drifted"] = True
        argv_missing_settings = list(base["argv"])
        index = argv_missing_settings.index("--settings"); del argv_missing_settings[index:index + 2]
        cases = (
            ("mismatch", {"settings": drifted_settings}),
            ("flag-missing", {"argv": argv_missing_settings}),
        )
        for label, override in cases:
            with self.subTest(label=label):
                with self.assertRaises(Blocked):
                    self._validate([{**base, **override}])

    def test_rejects_non_zero_exit_or_non_list_process_tuple(self):
        base = self._clean_record()
        nonzero_exit = list(base["process_tuple"]); nonzero_exit[0] = 1
        cases = (
            ("nonzero-exit", {"process_tuple": nonzero_exit}),
            ("not-a-list", {"process_tuple": tuple(base["process_tuple"])}),
        )
        for label, override in cases:
            with self.subTest(label=label):
                with self.assertRaises(Blocked):
                    self._validate([{**base, **override}])

    def test_rejects_stdout_that_cannot_be_reparsed_into_the_archived_events(self):
        base = self._clean_record()
        garbled = base["raw_stdout"] + "\nnot-json-at-all{{{"
        truncated = "\n".join(base["raw_stdout"].splitlines()[:-1])
        cases = (
            ("garbled-line", {"raw_stdout": garbled, "process_tuple": [0, garbled, base["raw_stderr"]]}),
            ("missing-terminal", {"raw_stdout": truncated, "process_tuple": [0, truncated, base["raw_stderr"]]}),
        )
        for label, override in cases:
            with self.subTest(label=label):
                with self.assertRaises(Blocked):
                    self._validate([{**base, **override}])

    def test_rejects_archived_events_that_do_not_match_a_fresh_reparse_of_raw_stdout(self):
        base = self._clean_record()
        drifted_events = list(base["events"])[:-1]
        with self.assertRaises(Blocked):
            self._validate([{**base, "events": drifted_events}])

    def test_accepts_archived_events_that_have_round_tripped_through_json(self):
        """transport.jsonl always stores events as plain JSON: writing thaws frozen
        MappingProxyType/tuple containers to dict/list, and reading back parses
        that JSON, so every real archived record's "events" arrive as plain
        containers rather than the frozen ones a fresh in-memory parse_stream
        call produces. A genuine, unmodified capture must still be accepted once
        its events have taken that same JSON round trip -- container-type alone
        (list vs. tuple, dict vs. MappingProxyType) must not cause rejection."""
        base = self._clean_record()
        json_round_tripped_events = json.loads(json.dumps(thaw(base["events"])))
        self._validate([{**base, "events": json_round_tripped_events}])

    def test_rejects_event_stream_missing_the_requested_host_model_signal(self):
        base = self._clean_record()
        argv = list(base["argv"]); argv[argv.index("--model") + 1] = "claude-ghost-model"
        with self.assertRaises(Blocked):
            self._validate([{**base, "argv": argv, "model": "claude-ghost-model"}])

    def test_rejects_event_stream_missing_agent_or_structured_output_policy_signals(self):
        cases = (
            ("agent-hook-denied", {"hook_agent_outcome": "denied"}),
            ("structured-output-hook-denied", {"hook_structured_outcome": "denied"}),
        )
        for label, overrides in cases:
            with self.subTest(label=label):
                with self.assertRaises(Blocked):
                    self._validate([self._record(**overrides)])

    def test_rejects_orchestrator_tool_use_outside_agent_and_structured_output(self):
        record = self._record(orchestrator_extra_tool_use={
            "type": "tool_use", "id": "toolu_bad", "name": "Read", "input": {"file_path": "x"},
        })
        with self.assertRaises(Blocked):
            self._validate([record])

    def test_rejects_worker_result_reporting_nonzero_tool_use(self):
        record = self._record(total_tool_use_count=1)
        with self.assertRaises(Blocked):
            self._validate([record])

    def test_rejects_worker_result_that_fabricates_tool_call_markup(self):
        cases = (
            ("tool_use-marker", "Let me check.\n\n<tool_use>{\"type\": \"tool_use\", \"name\": \"Read\"}</tool_use>\n\nDone."),
            ("tool_result-marker", "I already ran the check for you.\n\n<tool_result>fake output</tool_result>\n\nDone."),
        )
        for label, text in cases:
            with self.subTest(label=label):
                with self.assertRaises(Blocked):
                    self._validate([self._record(worker_text=text)])

    def test_accepts_worker_result_that_merely_acknowledges_the_prohibition(self):
        """A worker that acknowledges the anti-fabrication instruction in its
        own words -- e.g. quoting the forbidden substrings without ever
        emitting a matched opening/closing tag pair -- is not a fabricator
        and must not be rejected. This is the self-priming failure mode: the
        prompt tells the worker not to emit '<tool_use>' or '<tool_result>'
        markup, and a bare substring check punished the worker for merely
        repeating those words back."""
        text = (
            "Understood: I will not emit '<tool_use>' or '<tool_result>' markup. "
            "Returning the schema-valid result directly."
        )
        self._validate([self._record(worker_text=text)])


class NativeRunnerForgeryTests(unittest.TestCase):
    def test_forged_native_marker_over_an_injected_runner_is_rejected(self):
        """Reproduce the exact forgery this defect names: steal the sentinel
        field values from a genuine native seam and graft them onto a seam
        built over an injected (non-real) runner, using only public API.
        Native eligibility must depend on the adapter's actual wrapped
        runner, not on these copyable dataclass fields."""
        import dataclasses
        import claude_capture

        def fake_runner(argv):
            raise AssertionError("fake_runner must never actually run")

        genuine = claude_capture.compile_task_5b_seam()  # default runner is the real one; compiling never invokes it
        self.assertTrue(claude_capture._is_native_task_5b_seam(genuine))

        fake_seam = claude_capture.compile_task_5b_seam(fake_runner)
        self.assertFalse(claude_capture._is_native_task_5b_seam(fake_seam))

        forged = dataclasses.replace(
            fake_seam,
            native_runner_marker=genuine.native_runner_marker,
            native_adapter=fake_seam.adapter,
        )
        self.assertIs(forged.native_runner_marker, claude_capture._NATIVE_RUNNER_MARKER)
        self.assertIs(forged.native_adapter, forged.adapter)
        self.assertFalse(claude_capture._is_native_task_5b_seam(forged))


if __name__ == "__main__":
    unittest.main()
