import unittest
from dataclasses import FrozenInstanceError

from gate import (
    AWAITING_USER_INPUT,
    BLOCKED_STATE,
    FAILED,
    PASSED,
    RETRY,
    GateVerdict,
    RetryDecision,
    gate_result,
    retry_or_block,
)
from kernel_specs import Envelope
from qc_lib import Blocked
from run_state import PHASES, reduce


def _request(task_id, *, envelope_id, run_id="run-1", attempt=1):
    # attempt defaults to 1: run_state now requires every task-dispatching
    # request envelope to carry one (round-3 follow-up to FIX 4), and every
    # caller of this helper is building the first (and typically only)
    # request for a given task_id in an otherwise-empty reduce, so 1 is
    # always the correct next attempt.
    return Envelope.from_dict({
        "schema_version": 1,
        "envelope_id": envelope_id,
        "run_id": run_id,
        "sender": "orchestrator",
        "recipient": "agent:worker-1",
        "kind": "request",
        "payload": {"task_id": task_id, "attempt": attempt},
        "created_at": "2026-09-05T12:00:00Z",
    })


def _worker_result(task_id, outcome, *, envelope_id, run_id="run-1"):
    return Envelope.from_dict({
        "schema_version": 1,
        "envelope_id": envelope_id,
        "run_id": run_id,
        "sender": "agent:worker-1",
        "recipient": "orchestrator",
        "kind": "result",
        "payload": {"task_id": task_id, "attempt": 1, "outcome": outcome},
        "created_at": "2026-09-05T12:00:01Z",
    })


def _state_with_task_status(task_id, outcome):
    return reduce([
        _request(task_id, envelope_id="env-1"),
        _worker_result(task_id, outcome, envelope_id="env-2"),
    ])


class GateResultPassedTest(unittest.TestCase):
    def test_passed_result_has_no_critique(self):
        verdict = gate_result({"task_id": "task-1", "outcome": "passed"})
        self.assertEqual(verdict.task_id, "task-1")
        self.assertEqual(verdict.outcome, PASSED)
        self.assertIsNone(verdict.critique)

    def test_passed_result_ignores_a_stray_critique_field(self):
        # A passed result carrying a critique anyway must not surface it --
        # critique is meaningful only for a failure.
        verdict = gate_result({"task_id": "task-1", "outcome": "passed", "critique": "unused"})
        self.assertIsNone(verdict.critique)

    def test_attempt_is_passed_through_when_present(self):
        verdict = gate_result({"task_id": "task-1", "outcome": "passed", "attempt": 2})
        self.assertEqual(verdict.attempt, 2)

    def test_attempt_defaults_to_none_when_absent(self):
        verdict = gate_result({"task_id": "task-1", "outcome": "passed"})
        self.assertIsNone(verdict.attempt)


class GateResultFailedTest(unittest.TestCase):
    def test_failed_result_carries_its_critique(self):
        verdict = gate_result({
            "task_id": "task-1", "outcome": "failed", "critique": "off by one",
        })
        self.assertEqual(verdict.outcome, FAILED)
        self.assertEqual(verdict.critique, "off by one")

    def test_failed_result_without_critique_is_blocked(self):
        with self.assertRaises(Blocked) as ctx:
            gate_result({"task_id": "task-1", "outcome": "failed"})
        self.assertIn("critique", ctx.exception.detail.lower())

    def test_failed_result_with_empty_string_critique_is_blocked(self):
        # Presence, not truthiness: an empty string is technically present
        # but is not an explanation, and must be rejected exactly like a
        # missing critique (mirrors run_state's outcome-truthiness fix).
        with self.assertRaises(Blocked):
            gate_result({"task_id": "task-1", "outcome": "failed", "critique": ""})

    def test_failed_result_with_whitespace_only_critique_is_blocked(self):
        with self.assertRaises(Blocked):
            gate_result({"task_id": "task-1", "outcome": "failed", "critique": "   "})

    def test_failed_result_with_none_critique_is_blocked(self):
        with self.assertRaises(Blocked):
            gate_result({"task_id": "task-1", "outcome": "failed", "critique": None})


class GateResultMalformedInputTest(unittest.TestCase):
    def test_non_mapping_result_is_blocked(self):
        with self.assertRaises(Blocked):
            gate_result(["not", "a", "mapping"])

    def test_missing_task_id_is_blocked(self):
        with self.assertRaises(Blocked) as ctx:
            gate_result({"outcome": "passed"})
        self.assertIn("task_id", ctx.exception.detail)

    def test_empty_task_id_is_blocked(self):
        with self.assertRaises(Blocked):
            gate_result({"task_id": "", "outcome": "passed"})

    def test_unknown_outcome_is_blocked(self):
        with self.assertRaises(Blocked) as ctx:
            gate_result({"task_id": "task-1", "outcome": "maybe"})
        self.assertIn("outcome", ctx.exception.detail)

    def test_missing_outcome_is_blocked(self):
        with self.assertRaises(Blocked):
            gate_result({"task_id": "task-1"})


class GateVerdictImmutabilityTest(unittest.TestCase):
    def test_gate_verdict_fields_cannot_be_reassigned(self):
        verdict = gate_result({"task_id": "task-1", "outcome": "passed"})
        with self.assertRaises(FrozenInstanceError):
            verdict.outcome = "failed"


class RetryOrBlockRetryTest(unittest.TestCase):
    def test_positive_attempts_remaining_returns_retry_carrying_the_critique_forward(self):
        state = _state_with_task_status("task-1", "failed")
        decision = retry_or_block(state, "task-1", "off by one", 2)
        self.assertEqual(decision.action, RETRY)
        self.assertEqual(decision.task_id, "task-1")
        self.assertEqual(decision.critique, "off by one")
        self.assertIsNone(decision.phase)

    def test_attempts_remaining_of_exactly_one_still_retries(self):
        state = _state_with_task_status("task-1", "failed")
        decision = retry_or_block(state, "task-1", "off by one", 1)
        self.assertEqual(decision.action, RETRY)

    def test_attempts_remaining_is_the_public_keyword_name(self):
        # Pins the exact parameter name: "budget" reads as "what has been
        # spent" when the value this function actually consumes is "what
        # remains" -- see gate.retry_or_block's docstring for the formula
        # (attempts_remaining = max_attempts - attempts_made_so_far) and
        # the failure mode a reversed reading causes. A revert of the
        # rename back to "budget" makes this keyword call raise TypeError.
        state = _state_with_task_status("task-1", "failed")
        decision = retry_or_block(state, "task-1", "off by one", attempts_remaining=2)
        self.assertEqual(decision.action, RETRY)


class RetryOrBlockExhaustedTest(unittest.TestCase):
    def test_zero_attempts_remaining_returns_a_terminal_decision_not_retry(self):
        state = _state_with_task_status("task-1", "failed")
        decision = retry_or_block(state, "task-1", "still wrong", 0)
        self.assertNotEqual(decision.action, RETRY)
        self.assertIn(decision.action, (BLOCKED_STATE, AWAITING_USER_INPUT))

    def test_zero_attempts_remaining_decision_is_specifically_blocked_state(self):
        # retry_or_block never produces AWAITING_USER_INPUT today (see the
        # reserved-state note beside that constant in gate.py): every
        # exhaustion is BLOCKED_STATE specifically, not merely "one of the
        # two terminal names".
        state = _state_with_task_status("task-1", "failed")
        decision = retry_or_block(state, "task-1", "still wrong", 0)
        self.assertEqual(decision.action, BLOCKED_STATE)

    def test_zero_attempts_remaining_decision_phase_is_a_valid_run_state_phase(self):
        # The terminal phase this module names must actually be one
        # run_state.reduce accepts -- proven directly, not just asserted
        # by import-time constant equality.
        state = _state_with_task_status("task-1", "failed")
        decision = retry_or_block(state, "task-1", "still wrong", 0)
        self.assertIn(decision.phase, PHASES)

    def test_zero_attempts_remaining_carries_the_final_critique_for_context(self):
        state = _state_with_task_status("task-1", "failed")
        decision = retry_or_block(state, "task-1", "final failure reason", 0)
        self.assertEqual(decision.critique, "final failure reason")


class RetryOrBlockValidationTest(unittest.TestCase):
    def test_negative_attempts_remaining_is_blocked_not_treated_as_exhausted(self):
        state = _state_with_task_status("task-1", "failed")
        with self.assertRaises(Blocked):
            retry_or_block(state, "task-1", "some critique", -1)

    def test_boolean_attempts_remaining_is_rejected(self):
        # bool is a subclass of int in Python; True/False must not silently
        # pass as 1/0, mirroring kernel_specs._require_const_int's guard.
        state = _state_with_task_status("task-1", "failed")
        with self.assertRaises(Blocked):
            retry_or_block(state, "task-1", "some critique", True)

    def test_non_integer_attempts_remaining_is_blocked(self):
        state = _state_with_task_status("task-1", "failed")
        with self.assertRaises(Blocked):
            retry_or_block(state, "task-1", "some critique", "3")

    def test_empty_critique_is_blocked(self):
        state = _state_with_task_status("task-1", "failed")
        with self.assertRaises(Blocked):
            retry_or_block(state, "task-1", "", 1)

    def test_none_critique_is_blocked(self):
        state = _state_with_task_status("task-1", "failed")
        with self.assertRaises(Blocked):
            retry_or_block(state, "task-1", None, 1)

    def test_task_not_actually_failed_in_state_is_blocked(self):
        # The mailbox-derived state is the source of truth: a caller
        # cannot get a retry decision for a task the state does not show
        # as failed, even if it claims a critique for it.
        state = _state_with_task_status("task-1", "passed")
        with self.assertRaises(Blocked) as ctx:
            retry_or_block(state, "task-1", "some critique", 1)
        self.assertIn("task-1", ctx.exception.detail)

    def test_task_still_pending_in_state_is_blocked(self):
        state = reduce([])
        with self.assertRaises(Blocked):
            retry_or_block(state, "never-requested", "some critique", 1)

    def test_task_still_running_in_state_is_blocked(self):
        state = reduce([_request("task-1", envelope_id="env-1")])
        with self.assertRaises(Blocked):
            retry_or_block(state, "task-1", "some critique", 1)


class RetryDecisionImmutabilityTest(unittest.TestCase):
    def test_retry_decision_fields_cannot_be_reassigned(self):
        state = _state_with_task_status("task-1", "failed")
        decision = retry_or_block(state, "task-1", "off by one", 1)
        with self.assertRaises(FrozenInstanceError):
            decision.action = BLOCKED_STATE


class GateNeverSilentlyStallsTest(unittest.TestCase):
    # Table test: for every attempts_remaining value from 0 up through a
    # small positive range, retry_or_block must land on exactly one of the
    # two named outcome families -- never return without deciding.
    def test_every_attempts_remaining_value_resolves_to_a_named_decision(self):
        state = _state_with_task_status("task-1", "failed")
        for attempts_remaining in range(0, 5):
            with self.subTest(attempts_remaining=attempts_remaining):
                decision = retry_or_block(state, "task-1", "some critique", attempts_remaining)
                self.assertIsInstance(decision, RetryDecision)
                self.assertIn(decision.action, (RETRY, BLOCKED_STATE, AWAITING_USER_INPUT))


if __name__ == "__main__":
    unittest.main()
