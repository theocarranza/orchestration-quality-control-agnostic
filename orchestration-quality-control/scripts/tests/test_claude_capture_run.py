import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

from claude_adapter import ClaudeAdapter
from claude_capture import compile_task_5b_seam, recorded_test_provenance
from kernel_specs import TaskDag
from qc_lib import Blocked


def _stream(session, worker, result, tool_id):
    return "\n".join(
        json.dumps(item)
        for item in (
            {"type": "system", "subtype": "init", "session_id": session},
            {
                "type": "assistant",
                "message": {
                    "content": (
                        {
                            "type": "tool_use",
                            "id": tool_id,
                            "name": "Agent",
                            "input": {"subagent_type": worker},
                        },
                    )
                },
            },
            {"type": "result", "session_id": session, "structured_output": result},
        )
    )


class Task5bCaptureControllerTests(unittest.TestCase):
    def _seam(self, artifact_dir, fixture=None):
        template = compile_task_5b_seam(lambda argv: None)
        first, second = (node.task_id for node in template.contract.task_dag.tasks)
        calls = []

        def runner(argv):
            calls.append(argv)
            worker = argv[argv.index("--allowed-tools") + 1][6:-1]
            results = (
                {"task_id": first, "attempt": 1, "outcome": "failed", "critique": "need approved retry", "question": {"question_id": "task5b-q1", "prompt": "Retry first worker?"}, "artifact": "first artifact"},
                {"task_id": first, "attempt": 2, "outcome": "passed", "artifact": "second artifact"},
                {"task_id": second, "attempt": 1, "outcome": "passed", "artifact": "third artifact"},
            )
            return 0, _stream("native-task5b", worker, results[len(calls) - 1], f"tool-{len(calls)}"), ""

        adapter = ClaudeAdapter(runner, model="claude-opus-4-6", effort="medium", worker_definitions={spec.agent_id: {"description": "generated isolated worker", "prompt": "return only schema-valid output", "model": "claude-opus-4-6", "effort": "medium", "tools": []} for spec in template.contract.agent_specs.values()}, artifact_dir=artifact_dir)
        return replace(template, adapter=adapter, fixture=template.fixture if fixture is None else fixture), calls

    def test_drives_fixture_archives_once_and_verifies_without_rerun(self):
        from claude_capture_run import run_task_5b_capture

        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory) / "artifacts"
            seam, calls = self._seam(artifact_dir)
            observed = []
            from claude_capture import verify_capture
            def verifier(path, *, live_acceptance=False):
                before = len(calls)
                value = verify_capture(path, live_acceptance=live_acceptance)
                observed.append((before, len(calls), live_acceptance))
                return value
            with patch("claude_capture_run.verify_capture", side_effect=verifier):
                result = run_task_5b_capture(seam, artifact_dir, Path(directory) / "capture", provenance=recorded_test_provenance())

            self.assertEqual(len(calls), 3)
            self.assertEqual(result.capture_path, Path(directory) / "capture")
            self.assertEqual(result.verification.state.phase, "completed")
            self.assertEqual(len(calls), 3)
            self.assertEqual(observed, [(3, 3, False)])
            with self.assertRaises(FrozenInstanceError):
                result.capture_path = Path(directory) / "other"

    def test_rejects_malformed_fixture_before_running_a_worker(self):
        from claude_capture_run import run_task_5b_capture

        with tempfile.TemporaryDirectory() as directory:
            seam, calls = self._seam(Path(directory) / "artifacts", fixture=())
            with self.assertRaises(Blocked):
                run_task_5b_capture(seam, Path(directory) / "artifacts", Path(directory) / "capture", provenance=recorded_test_provenance())
            self.assertEqual(calls, [])

    def _assert_pre_dispatch_blocked(self, artifact_dir, fixture):
        from claude_capture_run import run_task_5b_capture

        seam, calls = self._seam(artifact_dir, fixture=fixture)
        capture_dir = artifact_dir.parent / "capture"
        with self.assertRaises(Blocked):
            run_task_5b_capture(seam, artifact_dir, capture_dir, provenance=recorded_test_provenance())
        self.assertEqual(calls, [])
        self.assertFalse(capture_dir.exists())

    def test_rejects_complete_fixture_boundary_table_before_running_a_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory) / "artifacts"
            seam, _ = self._seam(artifact_dir)
            failed, retry, first_passed, second_passed = seam.fixture
            question, answer = failed["question"], retry["answer"]
            fixtures = (
                ((), retry, first_passed, second_passed),
                (failed, (), first_passed, second_passed),
                (failed, retry, None, second_passed),
                (failed, retry, first_passed, None),
                ({"task_id": failed["task_id"], "attempt": 1, "outcome": "failed", "engine_authorized": True}, retry, first_passed, second_passed),
                ({**failed, "unexpected": "field"}, retry, first_passed, second_passed),
                ({**failed, "question": None}, retry, first_passed, second_passed),
                ({**failed, "question": ()}, retry, first_passed, second_passed),
                ({**failed, "question": {"question_id": question["question_id"]}}, retry, first_passed, second_passed),
                ({**failed, "question": {**question, "unexpected": "field"}}, retry, first_passed, second_passed),
                (failed, {**retry, "answer": None}, first_passed, second_passed),
                (failed, {**retry, "answer": ()}, first_passed, second_passed),
                (failed, {**retry, "answer": {"run_id": answer["run_id"]}}, first_passed, second_passed),
                (failed, {**retry, "answer": {**answer, "unexpected": "field"}}, first_passed, second_passed),
                (failed, {**retry, "answer": {**answer, "run_id": 0}}, first_passed, second_passed),
                (failed, {**retry, "answer": {**answer, "task_id": 0}}, first_passed, second_passed),
                (failed, {**retry, "answer": {**answer, "attempt": "one"}}, first_passed, second_passed),
                (failed, {**retry, "answer": {**answer, "question_id": 0}}, first_passed, second_passed),
                (failed, {**retry, "answer": {**answer, "decision": None}}, first_passed, second_passed),
                (failed, {**retry, "answer": {**answer, "text": 0}}, first_passed, second_passed),
                (failed, {**retry, "answer": {**answer, "text": "  "}}, first_passed, second_passed),
            )
            tuple(map(lambda fixture: self._assert_pre_dispatch_blocked(artifact_dir, fixture), fixtures))

    def _assert_caller_boundary_blocked(self, seam, calls, artifact_dir, capture_dir, publication_path, provenance):
        from claude_capture_run import run_task_5b_capture

        with self.assertRaises(Blocked):
            run_task_5b_capture(seam, artifact_dir, capture_dir, provenance=provenance)
        self.assertEqual(calls, [])
        self.assertFalse(publication_path.exists())

    def test_rejects_caller_boundary_before_running_a_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory) / "artifacts"
            seam, calls = self._seam(artifact_dir)
            marker = recorded_test_provenance()
            cases = (
                (replace(seam, contract=object()), artifact_dir, Path(directory) / "capture-contract", Path(directory) / "capture-contract", marker),
                (replace(seam, adapter=object()), artifact_dir, Path(directory) / "capture-adapter", Path(directory) / "capture-adapter", marker),
                (seam, Path(directory) / "mismatched-artifacts", Path(directory) / "capture-artifact", Path(directory) / "capture-artifact", marker),
                (seam, None, Path(directory) / "capture-null-artifact", Path(directory) / "capture-null-artifact", marker),
                (seam, artifact_dir, None, Path(directory) / "capture-null-capture", marker),
                (seam, artifact_dir, Path(directory) / "capture-provenance", Path(directory) / "capture-provenance", object()),
            )
            tuple(map(lambda case: self._assert_caller_boundary_blocked(case[0], calls, case[1], case[2], case[3], case[4]), cases))

    def test_rejects_non_task5b_dag_before_running_a_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory) / "artifacts"
            seam, calls = self._seam(artifact_dir)
            first, second = seam.contract.task_dag.tasks
            invalid_dags = (
                TaskDag.from_list([
                    {"task_id": second.task_id, "role": second.role, "depends_on": []},
                    {"task_id": first.task_id, "role": first.role, "depends_on": [second.task_id]},
                ]),
                TaskDag.from_list([
                    {"task_id": first.task_id, "role": first.role, "depends_on": []},
                    {"task_id": second.task_id, "role": second.role, "depends_on": []},
                ]),
            )
            for task_dag in invalid_dags:
                invalid_seam = replace(seam, contract=replace(seam.contract, task_dag=task_dag))
                self._assert_caller_boundary_blocked(
                    invalid_seam,
                    calls,
                    artifact_dir,
                    Path(directory) / f"capture-{len(calls)}",
                    Path(directory) / f"capture-{len(calls)}",
                    recorded_test_provenance(),
                )

    def test_cyclic_task_dag_is_rejected_by_its_constructor(self):
        with tempfile.TemporaryDirectory() as directory:
            seam, _ = self._seam(Path(directory) / "artifacts")
            first, second = seam.contract.task_dag.tasks
            with self.assertRaises(Blocked):
                TaskDag.from_list((
                    {"task_id": first.task_id, "role": first.role, "depends_on": [second.task_id]},
                    {"task_id": second.task_id, "role": second.role, "depends_on": [first.task_id]},
                ))

    def test_rejects_adapter_without_worker_configuration_before_running_a_worker(self):
        from claude_capture_run import run_task_5b_capture

        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory) / "artifacts"
            capture_dir = Path(directory) / "capture"
            seam, calls = self._seam(artifact_dir)
            del seam.adapter._workers

            with self.assertRaises(Blocked):
                run_task_5b_capture(seam, artifact_dir, capture_dir, provenance=recorded_test_provenance())

            self.assertEqual(calls, [])
            self.assertFalse(capture_dir.exists())

    def test_rejects_null_waiting_state_before_resume_or_capture(self):
        from claude_capture_run import run_task_5b_capture

        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory) / "artifacts"
            capture_dir = Path(directory) / "capture"
            seam, calls = self._seam(artifact_dir)

            with patch("claude_capture_run.drive", return_value=None), patch("claude_capture_run.resume") as resume_call:
                with self.assertRaises(Blocked):
                    run_task_5b_capture(seam, artifact_dir, capture_dir, provenance=recorded_test_provenance())

            self.assertEqual(calls, [])
            resume_call.assert_not_called()
            self.assertFalse(capture_dir.exists())

    def test_runtime_awaiting_binding_mismatch_blocks_after_first_worker_before_resume(self):
        from claude_capture_run import run_task_5b_capture
        from oqc import drive as actual_drive

        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory) / "artifacts"
            seam, calls = self._seam(artifact_dir)

            def altered_drive(*args, **kwargs):
                state = actual_drive(*args, **kwargs)
                return replace(state, context={**state.context, "question_id": "actual-question-id"})

            with patch("claude_capture_run.drive", side_effect=altered_drive), patch("claude_capture_run._derived_answer", wraps=__import__("claude_capture_run")._derived_answer) as derived_answer, patch("claude_capture_run.resume") as resume_call:
                with self.assertRaises(Blocked):
                    run_task_5b_capture(seam, artifact_dir, Path(directory) / "capture", provenance=recorded_test_provenance())

            self.assertEqual(len(calls), 1)
            self.assertEqual(derived_answer.call_args.args[1].context["question_id"], "actual-question-id")
            resume_call.assert_not_called()

    def test_rejects_null_failed_step_before_running_a_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory) / "artifacts"
            seam, _ = self._seam(artifact_dir)
            self._assert_pre_dispatch_blocked(artifact_dir, (None, *seam.fixture[1:]))

    def test_rejects_null_retry_step_before_running_a_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory) / "artifacts"
            seam, _ = self._seam(artifact_dir)
            self._assert_pre_dispatch_blocked(artifact_dir, (*seam.fixture[:1], None, *seam.fixture[2:]))

    def test_rejects_null_failed_question_before_running_a_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory) / "artifacts"
            seam, _ = self._seam(artifact_dir)
            self._assert_pre_dispatch_blocked(artifact_dir, ({**seam.fixture[0], "question": None}, *seam.fixture[1:]))

    def test_rejects_null_retry_answer_before_running_a_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory) / "artifacts"
            seam, _ = self._seam(artifact_dir)
            self._assert_pre_dispatch_blocked(artifact_dir, (*seam.fixture[:1], {**seam.fixture[1], "answer": None}, *seam.fixture[2:]))

    def test_rejects_non_mapping_failed_question_before_running_a_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory) / "artifacts"
            seam, _ = self._seam(artifact_dir)
            self._assert_pre_dispatch_blocked(artifact_dir, ({**seam.fixture[0], "question": ()}, *seam.fixture[1:]))

    def test_rejects_non_mapping_retry_answer_before_running_a_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory) / "artifacts"
            seam, _ = self._seam(artifact_dir)
            self._assert_pre_dispatch_blocked(artifact_dir, (*seam.fixture[:1], {**seam.fixture[1], "answer": ()}, *seam.fixture[2:]))

    def test_rejects_extra_fixture_lifecycle_fields_before_running_a_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory) / "artifacts"
            seam, _ = self._seam(artifact_dir)
            self._assert_pre_dispatch_blocked(artifact_dir, ({**seam.fixture[0], "unexpected": "field"}, *seam.fixture[1:]))

    def test_rejects_non_mapping_first_passed_step_before_running_a_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory) / "artifacts"
            seam, _ = self._seam(artifact_dir)
            self._assert_pre_dispatch_blocked(artifact_dir, (*seam.fixture[:2], (), seam.fixture[3]))

    def test_rejects_non_mapping_second_passed_step_before_running_a_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory) / "artifacts"
            seam, _ = self._seam(artifact_dir)
            self._assert_pre_dispatch_blocked(artifact_dir, (*seam.fixture[:3], ()))

    def test_rejects_mismatched_four_step_fixture_before_running_a_worker(self):
        from claude_capture_run import run_task_5b_capture

        with tempfile.TemporaryDirectory() as directory:
            seam, calls = self._seam(Path(directory) / "artifacts")
            fixture = list(seam.fixture)
            fixture[3] = {**fixture[3], "task_id": fixture[0]["task_id"]}
            with self.assertRaises(Blocked):
                run_task_5b_capture(replace(seam, fixture=tuple(fixture)), Path(directory) / "artifacts", Path(directory) / "capture", provenance=recorded_test_provenance())
            self.assertEqual(calls, [])

    def test_rejects_fixture_answer_not_bound_to_actual_awaiting_question(self):
        from claude_capture_run import run_task_5b_capture

        with tempfile.TemporaryDirectory() as directory:
            seam, calls = self._seam(Path(directory) / "artifacts")
            fixture = list(seam.fixture)
            fixture[1] = {**fixture[1], "answer": {**fixture[1]["answer"], "question_id": "wrong"}}
            with self.assertRaises(Blocked):
                run_task_5b_capture(replace(seam, fixture=tuple(fixture)), Path(directory) / "artifacts", Path(directory) / "capture", provenance=recorded_test_provenance())
            self.assertEqual(len(calls), 0)

    def test_injected_runner_fails_native_live_acceptance(self):
        from claude_capture_run import run_task_5b_capture

        with tempfile.TemporaryDirectory() as directory:
            seam, calls = self._seam(Path(directory) / "artifacts")
            from claude_capture import verify_capture
            observed = []

            def verifier(path, *, live_acceptance=False):
                observed.append(live_acceptance)
                return verify_capture(path, live_acceptance=live_acceptance)

            with patch("claude_capture_run.verify_capture", side_effect=verifier):
                with self.assertRaises(Blocked):
                    run_task_5b_capture(seam, Path(directory) / "artifacts", Path(directory) / "capture", provenance=None)

            self.assertEqual(len(calls), 0)
            self.assertEqual(observed, [])

    def test_replacing_an_injected_seam_cannot_select_native_acceptance(self):
        from claude_capture_run import run_task_5b_capture

        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory) / "artifacts"
            seam, calls = self._seam(artifact_dir)
            replaced = replace(seam, fixture=seam.fixture)
            with self.assertRaises(Blocked):
                run_task_5b_capture(replaced, artifact_dir, Path(directory) / "capture", provenance=None)
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
