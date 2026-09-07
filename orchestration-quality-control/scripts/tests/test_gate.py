import unittest
from dataclasses import FrozenInstanceError
from types import MappingProxyType

from gate import (
    AWAITING_USER_INPUT,
    BLOCKED_STATE,
    FAILED,
    PASSED,
    RETRY,
    GateVerdict,
    RetryDecision,
    decide_failure,
    gate_result,
    retry_or_block,
    AnswerDecision,
    approve_answer,
)
from kernel_specs import Envelope, GENESIS_HASH
from run_state import RunState
from qc_lib import Blocked
from run_state import PHASES, reduce


def _request(task_id, *, envelope_id, run_id="run-1", attempt=1):
    # attempt defaults to 1: run_state now requires every task-dispatching
    # request envelope to carry one (round-3 follow-up to FIX 4), and every
    # caller of this helper is building the first (and typically only)
    # request for a given task_id in an otherwise-empty reduce, so 1 is
    # always the correct next attempt.
    return Envelope.from_dict({
        "schema_version": 2,
        "previous_hash": GENESIS_HASH,
        "envelope_id": envelope_id,
        "run_id": run_id,
        "sender": "orchestrator",
        "recipient": "agent:worker-1",
        "kind": "request",
        "payload": {"task_id": task_id, "attempt": attempt},
        "created_at": "2026-09-05T12:00:00Z",
    })


def _worker_result(task_id, outcome, *, envelope_id, run_id="run-1", attempt=1):
    return Envelope.from_dict({
        "schema_version": 2,
        "previous_hash": GENESIS_HASH,
        "envelope_id": envelope_id,
        "run_id": run_id,
        "sender": "agent:worker-1",
        "recipient": "orchestrator",
        "kind": "result",
        "payload": {"task_id": task_id, "attempt": attempt, "outcome": outcome},
        "created_at": "2026-09-05T12:00:01Z",
    })


def _state_with_task_status(task_id, outcome, *, attempt=1):
    envelopes = []
    for current_attempt in range(1, attempt + 1):
        envelopes.extend([
            _request(task_id, envelope_id=f"env-request-{current_attempt}", attempt=current_attempt),
            _worker_result(task_id, outcome, envelope_id=f"env-result-{current_attempt}", attempt=current_attempt),
        ])
    return reduce(envelopes)


class GateResultPassedTest(unittest.TestCase):
    def test_passed_result_has_no_critique(self):
        verdict = gate_result({"task_id": "task-1", "attempt": 1, "outcome": "passed"})
        self.assertEqual(verdict.task_id, "task-1")
        self.assertEqual(verdict.outcome, PASSED)
        self.assertIsNone(verdict.critique)


class ApproveAnswerTest(unittest.TestCase):
    def _state(self, phase=AWAITING_USER_INPUT, remaining=2):
        return RunState("run-1", phase, 0, {"task_id": "task-1", "attempt": 1,
            "question_id": "q-1", "attempts_remaining": remaining,
            "critique": "wrong", "prompt": "Choose"}, (), {"task-1": "failed"}, {"task-1": 1})

    def _answer(self, decision="retry", **overrides):
        answer = {"run_id": "run-1", "task_id": "task-1", "attempt": 1,
                  "question_id": "q-1", "decision": decision, "text": "Proceed"}
        answer.update(overrides)
        return answer

    def test_approves_retry_and_stop_with_frozen_context(self):
        for decision, phase in (("retry", "execution"), ("stop", "blocked")):
            result = approve_answer(self._state(remaining=2), self._answer(decision))
            self.assertEqual(result.phase, phase)
            with self.assertRaises(FrozenInstanceError): result.phase = "blocked"

    def test_rejects_direct_answer_decision_as_raw_answer(self):
        raw = AnswerDecision("run-1", "task-1", 1, "q-1", "retry", "x", "execution", "wrong", "Choose", 2)
        with self.assertRaises(Blocked):
            approve_answer(self._state(), raw)

    def test_decision_carries_all_answer_and_waiting_fields(self):
        answer = self._answer("retry")
        answer["text"] = "Use the revised plan"
        result = approve_answer(self._state(), answer)
        self.assertEqual(result.run_id, answer["run_id"])
        self.assertEqual(result.task_id, answer["task_id"])
        self.assertEqual(result.attempt, answer["attempt"])
        self.assertEqual(result.question_id, answer["question_id"])
        self.assertEqual(result.decision, answer["decision"])
        self.assertEqual(result.text, answer["text"])
        self.assertEqual((result.phase, result.critique, result.prompt, result.attempts_remaining),
                         ("execution", "wrong", "Choose", 2))

    def test_approval_does_not_mutate_answer_or_state_and_decision_has_no_alias(self):
        state = self._state()
        before = state
        answer = self._answer()
        answer_before = dict(answer)
        result = approve_answer(state, answer)
        self.assertEqual(answer, answer_before)
        self.assertEqual(state, before)
        answer["text"] = "caller changed this"
        answer["decision"] = "stop"
        self.assertEqual(result.text, "Proceed")
        self.assertEqual(result.decision, "retry")

    def test_awaiting_state_with_absent_task_is_rejected_as_pending(self):
        state = RunState(
            "run-1", AWAITING_USER_INPUT, 0, self._state().context, (), {}, {}
        )
        with self.assertRaises(Blocked) as ctx:
            approve_answer(state, self._answer())
        self.assertIn("status", ctx.exception.detail)

    def test_wrong_phase_is_rejected(self):
        with self.assertRaises(Blocked):
            approve_answer(self._state(phase="execution"), self._answer())

    def test_mismatched_answer_identity_fields_are_rejected(self):
        for field, value in (("run_id", "other"), ("task_id", "other"),
                             ("attempt", 2), ("question_id", "other")):
            with self.subTest(field=field):
                with self.assertRaises(Blocked):
                    approve_answer(self._state(), self._answer(**{field: value}))

    def test_status_and_attempt_mismatches_are_rejected(self):
        for status, attempts in (("passed", {"task-1": 1}), ("failed", {"task-1": 2})):
            state = RunState("run-1", AWAITING_USER_INPUT, 0, self._state().context,
                             (), {"task-1": status}, attempts)
            with self.subTest(status=status, attempts=attempts), self.assertRaises(Blocked):
                approve_answer(state, self._answer())

    def test_each_waiting_context_field_is_required(self):
        fields = ("task_id", "attempt", "question_id", "attempts_remaining", "critique", "prompt")
        for field in fields:
            context = dict(self._state().context)
            del context[field]
            state = RunState("run-1", AWAITING_USER_INPUT, 0, context, (), {"task-1": "failed"}, {"task-1": 1})
            with self.subTest(field=field), self.assertRaises(Blocked):
                approve_answer(state, self._answer())

    def test_waiting_context_strings_and_integers_are_strict(self):
        for field in ("task_id", "question_id", "critique", "prompt"):
            context = dict(self._state().context)
            context[field] = " "
            state = RunState("run-1", AWAITING_USER_INPUT, 0, context, (), {"task-1": "failed"}, {"task-1": 1})
            with self.subTest(field=field), self.assertRaises(Blocked): approve_answer(state, self._answer())
        for field, values in (("attempt", (True, 0, "1")), ("attempts_remaining", (True, -1, "1"))):
            for value in values:
                context = dict(self._state().context); context[field] = value
                state = RunState("run-1", AWAITING_USER_INPUT, 0, context, (), {"task-1": "failed"}, {"task-1": 1})
                with self.subTest(field=field, value=value), self.assertRaises(Blocked): approve_answer(state, self._answer())

    def test_retry_zero_is_rejected_and_stop_zero_is_accepted(self):
        self.assertEqual(approve_answer(self._state(remaining=0), self._answer("stop")).phase, BLOCKED_STATE)
        with self.assertRaises(Blocked):
            approve_answer(self._state(remaining=0), self._answer("retry"))

    def test_passed_result_ignores_a_stray_critique_field(self):
        # A passed result carrying a critique anyway must not surface it --
        # critique is meaningful only for a failure.
        with self.assertRaises(Blocked):
            gate_result({"task_id": "task-1", "attempt": 1, "outcome": "passed", "critique": "unused"})

    def test_attempt_is_passed_through_when_present(self):
        verdict = gate_result({"task_id": "task-1", "outcome": "passed", "attempt": 2})
        self.assertEqual(verdict.attempt, 2)

    def test_attempt_defaults_to_none_when_absent(self):
        with self.assertRaises(Blocked):
            gate_result({"task_id": "task-1", "outcome": "passed"})


class GateResultFailedTest(unittest.TestCase):
    def test_failed_result_carries_its_critique(self):
        verdict = gate_result({
            "task_id": "task-1", "attempt": 1, "outcome": "failed", "critique": "off by one",
        })
        self.assertEqual(verdict.outcome, FAILED)
        self.assertEqual(verdict.critique, "off by one")

    def test_failed_result_without_critique_is_blocked(self):
        with self.assertRaises(Blocked) as ctx:
            gate_result({"task_id": "task-1", "attempt": 1, "outcome": "failed"})
        self.assertIn("critique", ctx.exception.detail.lower())

    def test_failed_result_with_empty_string_critique_is_blocked(self):
        # Presence, not truthiness: an empty string is technically present
        # but is not an explanation, and must be rejected exactly like a
        # missing critique (mirrors run_state's outcome-truthiness fix).
        with self.assertRaises(Blocked):
            gate_result({"task_id": "task-1", "attempt": 1, "outcome": "failed", "critique": ""})

    def test_failed_result_with_whitespace_only_critique_is_blocked(self):
        with self.assertRaises(Blocked):
            gate_result({"task_id": "task-1", "attempt": 1, "outcome": "failed", "critique": "   "})

    def test_failed_result_with_none_critique_is_blocked(self):
        with self.assertRaises(Blocked):
            gate_result({"task_id": "task-1", "attempt": 1, "outcome": "failed", "critique": None})

    def test_question_is_accepted_from_a_mapping_proxy(self):
        verdict = gate_result({
            "task_id": "task-1", "attempt": 1, "outcome": "failed", "critique": "why",
            "question": MappingProxyType({"question_id": "q-1", "prompt": "Choose"}),
        })
        self.assertEqual(verdict.question["question_id"], "q-1")

    def test_question_rejects_whitespace_only_identity_and_prompt(self):
        for field in ("question_id", "prompt"):
            question = {"question_id": "q-1", "prompt": "Choose"}
            question[field] = "   "
            with self.subTest(field=field), self.assertRaises(Blocked):
                gate_result({
                    "task_id": "task-1", "attempt": 1,
                    "outcome": "failed", "critique": "why",
                    "question": question,
                })

    def test_passed_result_with_question_is_blocked(self):
        with self.assertRaises(Blocked):
            gate_result({
                "task_id": "task-1", "attempt": 1, "outcome": "passed",
                "question": {"question_id": "q-1", "prompt": "Choose"},
            })

    def test_question_is_frozen_against_source_and_nested_mutation(self):
        question = {"question_id": "q-1", "prompt": "Choose"}
        verdict = gate_result({
            "task_id": "task-1", "attempt": 1, "outcome": "failed", "critique": "why",
            "question": question,
        })
        question["prompt"] = "changed"
        self.assertEqual(verdict.question["prompt"], "Choose")
        with self.assertRaises(TypeError):
            verdict.question["prompt"] = "changed"


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
            gate_result({"task_id": "", "attempt": 1, "outcome": "passed"})

    def test_unknown_outcome_is_blocked(self):
        with self.assertRaises(Blocked) as ctx:
            gate_result({"task_id": "task-1", "attempt": 1, "outcome": "maybe"})
        self.assertIn("outcome", ctx.exception.detail)

    def test_missing_outcome_is_blocked(self):
        with self.assertRaises(Blocked):
            gate_result({"task_id": "task-1"})


class GateVerdictImmutabilityTest(unittest.TestCase):
    def test_gate_verdict_fields_cannot_be_reassigned(self):
        verdict = gate_result({"task_id": "task-1", "attempt": 1, "outcome": "passed"})
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


class DecideFailureTest(unittest.TestCase):
    def _failed_verdict(self, *, attempt=1, question=None):
        result = {"task_id": "task-1", "attempt": attempt, "outcome": "failed", "critique": "off by one"}
        if question is not None:
            result["question"] = question
        return gate_result(result)

    def test_question_always_awaits_user_even_with_remaining_budget(self):
        state = _state_with_task_status("task-1", "failed")
        decision = decide_failure(state, self._failed_verdict(question={"question_id": "q-1", "prompt": "Choose"}), 3)
        self.assertEqual(decision.action, AWAITING_USER_INPUT)
        self.assertEqual(decision.attempts_remaining, 2)

    def test_question_awaits_user_when_budget_is_exhausted(self):
        state = _state_with_task_status("task-1", "failed")
        decision = decide_failure(state, self._failed_verdict(question={"question_id": "q-1", "prompt": "Choose"}), 1)
        self.assertEqual(decision.action, AWAITING_USER_INPUT)
        self.assertEqual(decision.attempts_remaining, 0)

    def test_ordinary_failure_retries_or_blocks_from_derived_remaining(self):
        state = _state_with_task_status("task-1", "failed")
        self.assertEqual(decide_failure(state, self._failed_verdict(), 3).action, RETRY)
        self.assertEqual(decide_failure(state, self._failed_verdict(), 1).action, BLOCKED_STATE)

    def test_rejects_non_verdict_and_nonfailed_verdict(self):
        state = _state_with_task_status("task-1", "failed")
        with self.assertRaises(Blocked):
            decide_failure(state, {"task_id": "task-1"}, 3)
        with self.assertRaises(Blocked):
            decide_failure(state, gate_result({"task_id": "task-1", "attempt": 1, "outcome": "passed"}), 3)

    def test_rejects_mismatched_attempt_and_fabricated_contradiction(self):
        state = _state_with_task_status("task-1", "failed", attempt=2)
        with self.assertRaises(Blocked):
            decide_failure(state, self._failed_verdict(attempt=1), 3)
        with self.assertRaises(Blocked):
            decide_failure(state, GateVerdict("task-1", 2, FAILED, "", None), 3)

    def test_rejects_bad_max_attempts_and_budget_below_actual_attempt(self):
        state = _state_with_task_status("task-1", "failed", attempt=2)
        verdict = self._failed_verdict(attempt=2)
        for maximum in (True, False, 0, -1, "3", 1):
            with self.subTest(max_attempts=maximum), self.assertRaises(Blocked):
                decide_failure(state, verdict, maximum)

    def test_decision_is_frozen(self):
        state = _state_with_task_status("task-1", "failed")
        decision = decide_failure(state, self._failed_verdict(), 3)
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
