import unittest
from dataclasses import FrozenInstanceError
from types import MappingProxyType

from kernel_specs import Envelope
from qc_lib import Blocked

from run_state import PHASES, RunState, initial_state, reduce, status_of


def _status(phase, *, envelope_id="env-status", run_id="run-0001", extra=None):
    payload = {"phase": phase}
    if extra:
        payload.update(extra)
    return Envelope.from_dict({
        "schema_version": 1,
        "envelope_id": envelope_id,
        "run_id": run_id,
        "sender": "orchestrator",
        "recipient": "root",
        "kind": "status",
        "payload": payload,
        "created_at": "2026-09-04T12:00:00Z",
    })


def _non_status(kind, *, envelope_id="env-other", run_id="run-0001"):
    return Envelope.from_dict({
        "schema_version": 1,
        "envelope_id": envelope_id,
        "run_id": run_id,
        "sender": "orchestrator",
        "recipient": "agent:worker-1",
        "kind": kind,
        "payload": {"note": "irrelevant to phase"},
        "created_at": "2026-09-04T12:00:00Z",
    })


class ObservablePhasesTableTest(unittest.TestCase):
    # One table case per phase -- not a single happy path. Each case drives
    # `reduce` with its own short envelope sequence and checks the phase
    # this task claims is observable.

    def test_each_of_the_nine_phases_is_reachable(self):
        for phase in PHASES:
            with self.subTest(phase=phase):
                state = reduce([_status(phase)])
                self.assertEqual(state.phase, phase)

    def test_phase_sequence_reachable_through_a_multi_step_run(self):
        # A single fixture threading through several phases in order, to
        # prove reduce composes across steps rather than only handling one
        # status envelope at a time.
        sequence = [
            _status("discovery", envelope_id="env-1"),
            _status("interview", envelope_id="env-2"),
            _status("planning", envelope_id="env-3"),
            _status("orchestration", envelope_id="env-4"),
            _non_status("request", envelope_id="env-5"),
            _status("execution", envelope_id="env-6"),
            _non_status("result", envelope_id="env-7"),
            _status("verification", envelope_id="env-8"),
            _status("completed", envelope_id="env-9"),
        ]
        state = reduce(sequence)
        self.assertEqual(state.phase, "completed")
        self.assertEqual(
            state.history,
            (
                "discovery", "discovery", "interview", "planning",
                "orchestration", "execution", "verification", "completed",
            ),
        )
        self.assertEqual(state.envelope_count, len(sequence))

    def test_blocked_and_awaiting_user_input_are_reachable_after_a_retry(self):
        exhausted = reduce([
            _status("execution", envelope_id="env-1"),
            _status("blocked", envelope_id="env-2", extra={"reason": "retries exhausted"}),
        ])
        self.assertEqual(exhausted.phase, "blocked")
        self.assertEqual(exhausted.context["reason"], "retries exhausted")

        waiting = reduce([
            _status("execution", envelope_id="env-1"),
            _status("awaiting-user-input", envelope_id="env-2", extra={"question": "which target?"}),
        ])
        self.assertEqual(waiting.phase, "awaiting-user-input")
        self.assertEqual(waiting.context["question"], "which target?")

    def test_non_status_envelopes_do_not_change_phase_but_are_counted(self):
        state = reduce([
            _status("planning", envelope_id="env-1"),
            _non_status("request", envelope_id="env-2"),
            _non_status("question", envelope_id="env-3"),
            _non_status("answer", envelope_id="env-4"),
        ])
        self.assertEqual(state.phase, "planning")
        self.assertEqual(state.envelope_count, 4)

    def test_status_envelope_missing_phase_is_blocked(self):
        bad = Envelope.from_dict({
            "schema_version": 1,
            "envelope_id": "env-bad",
            "run_id": "run-0001",
            "sender": "orchestrator",
            "recipient": "root",
            "kind": "status",
            "payload": {"note": "no phase field"},
            "created_at": "2026-09-04T12:00:00Z",
        })
        with self.assertRaises(Blocked) as ctx:
            reduce([bad])
        self.assertIn("phase", ctx.exception.detail)

    def test_status_envelope_with_unknown_phase_is_blocked(self):
        with self.assertRaises(Blocked) as ctx:
            reduce([_status("nonexistent-phase")])
        self.assertIn("phase", ctx.exception.detail)

    def test_envelope_from_a_different_run_is_blocked(self):
        with self.assertRaises(Blocked) as ctx:
            reduce([
                _status("planning", envelope_id="env-1", run_id="run-0001"),
                _status("execution", envelope_id="env-2", run_id="run-9999"),
            ])
        self.assertIn("run_id", ctx.exception.detail)


class ReducePurityTest(unittest.TestCase):
    # These tests are written to FAIL if reduce stops being a pure fold --
    # e.g. if it read wall-clock time, consulted module-level mutable
    # state, or mutated its input in place. Verified during implementation
    # by temporarily introducing exactly such an impurity and watching
    # these tests go red (see the implementer report).

    SEQUENCE = None
    TASK_SEQUENCE = None

    @classmethod
    def setUpClass(cls):
        cls.SEQUENCE = [
            _status("discovery", envelope_id="env-1"),
            _status("interview", envelope_id="env-2"),
            _status("planning", envelope_id="env-3"),
            _non_status("request", envelope_id="env-4"),
            _status("orchestration", envelope_id="env-5"),
            _status("execution", envelope_id="env-6"),
            _status("verification", envelope_id="env-7"),
            _status("completed", envelope_id="env-8"),
        ]
        # Sequence with task status updates
        cls.TASK_SEQUENCE = [
            Envelope.from_dict({
                "schema_version": 1,
                "envelope_id": "env-1",
                "run_id": "run-1",
                "sender": "orchestrator",
                "recipient": "agent:worker-1",
                "kind": "request",
                "payload": {"task_id": "task-1"},
                "created_at": "2026-09-04T12:00:00Z",
            }),
            Envelope.from_dict({
                "schema_version": 1,
                "envelope_id": "env-2",
                "run_id": "run-1",
                "sender": "agent:worker-1",
                "recipient": "orchestrator",
                "kind": "result",
                "payload": {"task_id": "task-1", "outcome": "passed"},
                "created_at": "2026-09-04T12:00:01Z",
            }),
        ]

    def test_reducing_the_same_sequence_twice_yields_equal_states(self):
        first = reduce(self.SEQUENCE)
        second = reduce(self.SEQUENCE)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)

    def test_reducing_task_sequence_twice_yields_equal_task_status(self):
        # Verify purity still holds when task_status is involved
        first = reduce(self.TASK_SEQUENCE)
        second = reduce(self.TASK_SEQUENCE)
        self.assertEqual(first, second)
        self.assertEqual(first.task_status, second.task_status)
        self.assertIsNot(first, second)

    def test_reducing_does_not_mutate_its_input_sequence(self):
        sequence_copy = list(self.SEQUENCE)
        reduce(self.SEQUENCE)
        self.assertEqual(self.SEQUENCE, sequence_copy)

    def test_prefix_then_continuation_equals_reducing_everything_at_once(self):
        whole = reduce(self.SEQUENCE)
        for split in range(len(self.SEQUENCE) + 1):
            with self.subTest(split=split):
                prefix_state = reduce(self.SEQUENCE[:split])
                continued_state = reduce(self.SEQUENCE[split:], prefix_state)
                self.assertEqual(continued_state, whole)

    def test_reducing_an_empty_sequence_from_a_state_returns_that_state_unchanged(self):
        state = reduce(self.SEQUENCE[:3])
        self.assertEqual(reduce([], state), state)

    def test_reducing_from_scratch_twice_in_different_call_order_still_agrees(self):
        # Calling reduce() with no explicit starting state must be
        # equivalent to calling it with an explicit initial_state() --
        # there must be no hidden default that only kicks in "the first
        # time" a process happens to call it.
        explicit = reduce(self.SEQUENCE, initial_state())
        implicit = reduce(self.SEQUENCE)
        self.assertEqual(explicit, implicit)


class RunStateImmutabilityTest(unittest.TestCase):
    # Mirrors the two failure modes called out for this task: (1) a proof
    # that is implemented but never exercised, and (2) a guarantee that
    # holds through one construction path but not another. Every case here
    # is written to fail if the corresponding guard is removed, and each
    # was confirmed red-then-green during implementation by temporarily
    # removing the guard (see the implementer report).

    def _derived_state(self):
        return reduce([
            _status("planning", envelope_id="env-1", extra={
                "targets": ["a.md", "b.md"],
                "nested": {"inner": "value"},
            }),
        ])

    def test_top_level_field_reassignment_raises_via_reduce(self):
        state = self._derived_state()
        with self.assertRaises(FrozenInstanceError):
            state.phase = "blocked"

    def test_history_tuple_item_assignment_raises_via_reduce(self):
        state = self._derived_state()
        with self.assertRaises(TypeError):
            state.history[0] = "tampered"

    def test_context_mapping_item_assignment_raises_via_reduce(self):
        state = self._derived_state()
        with self.assertRaises(TypeError):
            state.context["nested"] = "tampered"

    def test_nested_context_dict_mutation_raises_via_reduce(self):
        # A shallow freeze would leave the top-level context mapping
        # immutable while leaving a nested dict/list mutable -- prove the
        # freeze recurses, for both a nested mapping and a nested sequence.
        state = self._derived_state()
        with self.assertRaises(TypeError):
            state.context["nested"]["inner"] = "tampered"
        with self.assertRaises(TypeError):
            state.context["targets"][0] = "tampered"
        with self.assertRaises(AttributeError):
            state.context["targets"].append("c.md")

    def test_top_level_field_reassignment_raises_via_direct_construction(self):
        # RunState is a public frozen dataclass; nothing stops a caller (or
        # a future module) from constructing it directly instead of going
        # through reduce(). The guarantee must hold on that path too.
        state = RunState(
            run_id="run-0001",
            phase="planning",
            envelope_count=1,
            context={"nested": {"inner": "value"}, "targets": ["a.md"]},
            history=["discovery", "planning"],
            task_status={},
        )
        with self.assertRaises(FrozenInstanceError):
            state.phase = "blocked"

    def test_history_list_passed_directly_is_coerced_and_protected(self):
        mutable_history = ["discovery", "planning"]
        state = RunState(
            run_id="run-0001",
            phase="planning",
            envelope_count=1,
            context={},
            history=mutable_history,
            task_status={},
        )
        mutable_history.append("tampered-after-construction")
        self.assertEqual(state.history, ("discovery", "planning"))
        with self.assertRaises(TypeError):
            state.history[0] = "tampered"

    def test_nested_context_mutation_raises_via_direct_construction(self):
        state = RunState(
            run_id="run-0001",
            phase="planning",
            envelope_count=1,
            context={"nested": {"inner": "value"}, "targets": ["a.md", "b.md"]},
            history=["discovery", "planning"],
            task_status={},
        )
        with self.assertRaises(TypeError):
            state.context["nested"]["inner"] = "tampered"
        with self.assertRaises(TypeError):
            state.context["targets"][0] = "tampered"
        with self.assertRaises(AttributeError):
            state.context["targets"].append("c.md")

    def test_direct_construction_with_already_frozen_context_still_protects_nested_values(self):
        # If a caller hands the constructor an already-MappingProxyType
        # context whose nested dict/list are still plain, freezing must not
        # short-circuit on the already-frozen top level and skip recursing.
        context = MappingProxyType({"nested": {"inner": "value"}, "targets": ["a.md"]})
        state = RunState(
            run_id="run-0001",
            phase="planning",
            envelope_count=1,
            context=context,
            history=("discovery", "planning"),
            task_status={},
        )
        with self.assertRaises(TypeError):
            state.context["nested"]["inner"] = "tampered"
        with self.assertRaises(TypeError):
            state.context["targets"][0] = "tampered"

    def test_initial_state_is_also_immutable(self):
        state = initial_state()
        with self.assertRaises(FrozenInstanceError):
            state.phase = "blocked"


class TaskStatusTest(unittest.TestCase):
    def test_task_status_contains_only_mentioned_tasks(self):
        # task_status only contains tasks that have been mentioned in envelopes
        request = Envelope.from_dict({
            "schema_version": 1,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "orchestrator",
            "recipient": "agent:worker-1",
            "kind": "request",
            "payload": {"task_id": "task-1"},
            "created_at": "2026-09-04T12:00:00Z",
        })
        state = reduce([request])
        self.assertIn("task-1", state.task_status)
        self.assertNotIn("task-2", state.task_status)

    def test_task_status_get_with_absent_key_returns_none(self):
        # The mapping contract must hold: get(key, None) returns None for missing keys
        state = reduce([])
        self.assertIsNone(state.task_status.get("absent", None))
        self.assertEqual(state.task_status.get("absent", "default"), "default")

    def test_status_of_returns_pending_for_absent_tasks(self):
        # status_of() provides the default "pending" explicitly
        state = reduce([])
        self.assertEqual(status_of(state, "task-1"), "pending")
        self.assertEqual(status_of(state, "unknown"), "pending")

    def test_request_envelope_marks_task_running(self):
        request = Envelope.from_dict({
            "schema_version": 1,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "orchestrator",
            "recipient": "agent:worker-1",
            "kind": "request",
            "payload": {"task_id": "analyze"},
            "created_at": "2026-09-04T12:00:00Z",
        })
        state = reduce([request])
        self.assertEqual(state.task_status["analyze"], "running")

    def test_result_envelope_with_passed_marks_passed(self):
        result = Envelope.from_dict({
            "schema_version": 1,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "agent:worker-1",
            "recipient": "orchestrator",
            "kind": "result",
            "payload": {"task_id": "analyze", "outcome": "passed"},
            "created_at": "2026-09-04T12:00:00Z",
        })
        state = reduce([result])
        self.assertEqual(state.task_status["analyze"], "passed")

    def test_result_envelope_with_failed_marks_failed(self):
        result = Envelope.from_dict({
            "schema_version": 1,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "agent:worker-1",
            "recipient": "orchestrator",
            "kind": "result",
            "payload": {"task_id": "analyze", "outcome": "failed"},
            "created_at": "2026-09-04T12:00:00Z",
        })
        state = reduce([result])
        self.assertEqual(state.task_status["analyze"], "failed")

    def test_unknown_outcome_is_rejected(self):
        result = Envelope.from_dict({
            "schema_version": 1,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "agent:worker-1",
            "recipient": "orchestrator",
            "kind": "result",
            "payload": {"task_id": "analyze", "outcome": "unknown"},
            "created_at": "2026-09-04T12:00:00Z",
        })
        with self.assertRaises(Blocked) as ctx:
            reduce([result])
        self.assertIn("outcome", ctx.exception.detail)

    def test_empty_string_outcome_is_rejected_not_silently_stranded(self):
        # Regression for the truthiness-guard deadlock: a present-but-falsy
        # outcome ("") used to short-circuit the `if task_id and outcome`
        # guard before the VALID_OUTCOMES check ever ran, silently leaving
        # the task "running" forever. Presence, not truthiness, must gate
        # validation.
        result = Envelope.from_dict({
            "schema_version": 1,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "agent:worker-1",
            "recipient": "orchestrator",
            "kind": "result",
            "payload": {"task_id": "analyze", "outcome": ""},
            "created_at": "2026-09-04T12:00:00Z",
        })
        with self.assertRaises(Blocked) as ctx:
            reduce([result])
        self.assertIn("outcome", ctx.exception.detail)

    def test_none_outcome_is_rejected(self):
        result = Envelope.from_dict({
            "schema_version": 1,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "agent:worker-1",
            "recipient": "orchestrator",
            "kind": "result",
            "payload": {"task_id": "analyze", "outcome": None},
            "created_at": "2026-09-04T12:00:00Z",
        })
        with self.assertRaises(Blocked) as ctx:
            reduce([result])
        self.assertIn("outcome", ctx.exception.detail)

    def test_empty_string_task_id_in_result_is_rejected(self):
        result = Envelope.from_dict({
            "schema_version": 1,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "agent:worker-1",
            "recipient": "orchestrator",
            "kind": "result",
            "payload": {"task_id": "", "outcome": "passed"},
            "created_at": "2026-09-04T12:00:00Z",
        })
        with self.assertRaises(Blocked) as ctx:
            reduce([result])
        self.assertIn("task_id", ctx.exception.detail)

    def test_request_then_falsy_outcome_result_raises_instead_of_deadlocking(self):
        # The exact deadlock sequence from the defect report: reducing
        # [request(t1), result(t1, outcome="")] must raise Blocked rather
        # than leave t1 stranded at "running" forever (which used to make
        # next_tasks return () for anything depending on t1, permanently).
        request = Envelope.from_dict({
            "schema_version": 1,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "orchestrator",
            "recipient": "agent:worker-1",
            "kind": "request",
            "payload": {"task_id": "t1"},
            "created_at": "2026-09-04T12:00:00Z",
        })
        result = Envelope.from_dict({
            "schema_version": 1,
            "envelope_id": "env-2",
            "run_id": "run-1",
            "sender": "agent:worker-1",
            "recipient": "orchestrator",
            "kind": "result",
            "payload": {"task_id": "t1", "outcome": ""},
            "created_at": "2026-09-04T12:00:01Z",
        })
        with self.assertRaises(Blocked):
            reduce([request, result])

    def test_task_status_progression_through_workflow(self):
        envelopes = [
            Envelope.from_dict({
                "schema_version": 1,
                "envelope_id": "env-1",
                "run_id": "run-1",
                "sender": "orchestrator",
                "recipient": "agent:worker-1",
                "kind": "request",
                "payload": {"task_id": "discover"},
                "created_at": "2026-09-04T12:00:00Z",
            }),
            Envelope.from_dict({
                "schema_version": 1,
                "envelope_id": "env-2",
                "run_id": "run-1",
                "sender": "agent:worker-1",
                "recipient": "orchestrator",
                "kind": "result",
                "payload": {"task_id": "discover", "outcome": "passed"},
                "created_at": "2026-09-04T12:00:01Z",
            }),
            Envelope.from_dict({
                "schema_version": 1,
                "envelope_id": "env-3",
                "run_id": "run-1",
                "sender": "orchestrator",
                "recipient": "agent:worker-2",
                "kind": "request",
                "payload": {"task_id": "analyze"},
                "created_at": "2026-09-04T12:00:02Z",
            }),
        ]
        state = reduce(envelopes)
        # Both tasks were mentioned in envelopes, so they're in task_status
        self.assertEqual(status_of(state, "discover"), "passed")
        self.assertEqual(status_of(state, "analyze"), "running")
        # Verify they're actually stored (not using default)
        self.assertIn("discover", state.task_status)
        self.assertIn("analyze", state.task_status)

    def test_task_status_immutable(self):
        state = reduce([])
        with self.assertRaises(TypeError):
            state.task_status["task-1"] = "running"

    def test_task_status_not_in_phase_progression(self):
        # Envelopes without task_id don't affect task_status
        request = Envelope.from_dict({
            "schema_version": 1,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "orchestrator",
            "recipient": "agent:worker-1",
            "kind": "question",
            "payload": {"text": "what is the target?"},
            "created_at": "2026-09-04T12:00:00Z",
        })
        state = reduce([request])
        self.assertNotIn("task-1", state.task_status)


class RunStateDerivationIsNeverStoredTest(unittest.TestCase):
    def test_run_state_module_exposes_no_persistence_or_setter_api(self):
        # RunState/reduce are the only public surface; there is no
        # save/load/store/set-style function that would let a caller treat
        # state as anything other than a derived, in-memory value.
        import run_state as run_state_module

        public_names = {
            name for name in dir(run_state_module) if not name.startswith("_")
        }
        forbidden_substrings = ("save", "store", "persist", "load", "write", "set_")
        for name in public_names:
            for forbidden in forbidden_substrings:
                self.assertNotIn(forbidden, name.lower())


if __name__ == "__main__":
    unittest.main()
