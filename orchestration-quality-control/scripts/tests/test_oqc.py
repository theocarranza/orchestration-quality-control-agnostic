"""Tests for oqc.py: the real orchestrator drive() loop, replay(), verify(),
the CLI, and the two findings carried forward from Outcome 2 Task 4's
quality review (a durable retry-decision trace, and composing
relay_question/enforce_policy into the loop).

The two-task dependent DAG and both scripts below are the same shape as
tests/test_replay.py's Fixture A (critiqued retry -> completed) and
Fixture B (exhausted retries -> a terminal state, task-b never runs),
driven through the real oqc.drive() loop instead of a hand-written test
loop -- this is the "through the real loop rather than a fixture"
evidence the brief for this task calls for.
"""

import contextlib
import importlib
import inspect
import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import oqc
from fake_adapter import FakeAdapter
from gate import gate_result, retry_or_block, approve_answer
from kernel_specs import AgentSpec, Envelope, GENESIS_HASH, TaskDag
from mailbox import Mailbox
from oqc import drive, replay, verify
from qc_lib import Blocked
from router import next_tasks, validate_pair
from run_state import attempts_of, reduce, status_of

RUN_ID = "run-oqc"
MAX_ATTEMPTS = 3

DAG = TaskDag.from_list([
    {"task_id": "task-a", "role": "role-a", "depends_on": []},
    {"task_id": "task-b", "role": "role-b", "depends_on": ["task-a"]},
])


def _agent_spec(agent_id, role):
    return AgentSpec.from_dict({
        "schema_version": 1,
        "agent_id": agent_id,
        "role": role,
        "capabilities": ["execute"],
        "tools": [],
        "output_schema": "schemas/worker-result.schema.json",
        "model_tier": "medium",
        "reasoning_effort": "medium",
    })


AGENT_SPECS = {
    "role-a": _agent_spec("worker-a", "role-a"),
    "role-b": _agent_spec("worker-b", "role-b"),
}

SCRIPT_A = {
    ("task-a", 1): {"outcome": "failed", "critique": "off-by-one in the boundary check"},
    ("task-a", 2): {"outcome": "passed"},
    ("task-b", 1): {"outcome": "passed"},
}

SCRIPT_B = {
    ("task-a", 1): {"outcome": "failed", "critique": "attempt 1: wrong output shape"},
    ("task-a", 2): {"outcome": "failed", "critique": "attempt 2: still wrong"},
    ("task-a", 3): {"outcome": "failed", "critique": "attempt 3: still wrong"},
}

SCRIPT_QUESTION = {
    ("task-a", 1): {"outcome": "failed", "critique": "needs a choice",
                    "question": {"question_id": "q-a-1", "prompt": "Retry task-a?"},
                    "artifact": "first"},
    ("task-a", 2): {"outcome": "passed", "artifact": "second"},
    ("task-b", 1): {"outcome": "passed"},
}

SCRIPT_REPEATED_QUESTION = {
    ("task-a", 1): {"outcome": "failed", "critique": "first failure",
                    "question": {"question_id": "q-a-1", "prompt": "Retry first?"}},
    ("task-a", 2): {"outcome": "failed", "critique": "second failure",
                    "question": {"question_id": "q-a-2", "prompt": "Retry second?"}},
    ("task-a", 3): {"outcome": "passed", "artifact": "final"},
    ("task-b", 1): {"outcome": "passed"},
}

SCRIPT_ZERO_BUDGET_QUESTION = {
    ("task-a", 1): {"outcome": "failed", "critique": "first failure"},
    ("task-a", 2): {"outcome": "failed", "critique": "second failure"},
    ("task-a", 3): {"outcome": "failed", "critique": "final choice",
                    "question": {"question_id": "q-a-3", "prompt": "Stop now?"}},
}


def _latest(mailbox, *, kind, task_id, attempt=None):
    matches = [
        envelope.payload
        for envelope in mailbox.read_all()
        if envelope.kind == kind
        and envelope.payload.get("task_id") == task_id
        and (attempt is None or envelope.payload.get("attempt") == attempt)
    ]
    if not matches:
        raise AssertionError(f"no {kind!r} envelope for task_id={task_id!r} attempt={attempt!r}")
    return matches[-1]


def _envelope_data(**overrides):
    data = {
        "schema_version": 2,
        "envelope_id": "env-1",
        "run_id": RUN_ID,
        "sender": "orchestrator",
        "recipient": "agent:worker-a",
        "kind": "request",
        "payload": {"task_id": "task-a", "attempt": 1, "brief": {}},
        "created_at": "2026-09-05T12:00:00Z",
        "previous_hash": GENESIS_HASH,
    }
    data.update(overrides)
    return data


def _envelope(**overrides):
    return Envelope.from_dict(_envelope_data(**overrides))


def _chain(*envelope_data_dicts):
    """Build a list of `Envelope` from plain data dicts (as `_envelope_data`
    produces), wiring each one's `previous_hash` to the real hash of the
    one immediately before it (`kernel_specs.GENESIS_HASH` for the first) --
    a genuine, untampered mailbox history, exactly what every verify()
    tamper test below needs *before* it corrupts one specific entry. Any
    `previous_hash` already present in a given dict is overridden, mirroring
    `adapter_port.AdapterPort._append` -- producers of the data dicts here
    are not expected to compute chaining themselves either.
    """
    chained = []
    previous_hash = GENESIS_HASH
    for data in envelope_data_dicts:
        envelope = Envelope.from_dict({**data, "previous_hash": previous_hash})
        chained.append(envelope)
        previous_hash = envelope.hash()
    return chained


def _corrupt_mailbox(envelopes):
    """Build a Mailbox holding exactly `envelopes`, bypassing the public
    constructor/append's own duplicate-id and type checks by writing
    directly to the private `_events` list.

    This is the only way to produce a Mailbox object shaped like tampered
    data (a duplicate id, a deleted or reordered envelope) that could
    never arise through the normal append-only API -- exactly the
    "unguarded construction path" the tampering tests below need to
    simulate.
    """
    mailbox = Mailbox()
    mailbox._events = list(envelopes)
    return mailbox


# ---------------------------------------------------------------------------
# drive(): reproduces Task 4's Fixture A outcome through the real loop.
# ---------------------------------------------------------------------------


class DriveCritiqueCarryingRetryTest(unittest.TestCase):
    def test_drive_reaches_completed_after_a_critiqued_retry(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_A)
        final_state = drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)

        self.assertEqual(final_state.phase, "completed")
        self.assertEqual(status_of(final_state, "task-a"), "passed")
        self.assertEqual(status_of(final_state, "task-b"), "passed")
        self.assertEqual(attempts_of(final_state, "task-a"), 2)
        self.assertEqual(attempts_of(final_state, "task-b"), 1)

    def test_the_second_attempts_brief_carries_the_first_failures_critique(self):
        # The load-bearing assertion carried over from Task 4's Fixture A,
        # now produced by the real loop rather than hand-copied by a test.
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_A)
        final_state = drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)

        request_2 = _latest(mailbox, kind="request", task_id="task-a", attempt=2)
        self.assertEqual(request_2["brief"]["critique"], "off-by-one in the boundary check")

    def test_drive_is_model_free_and_deterministic_across_two_runs(self):
        def _drive_fresh():
            mailbox = Mailbox()
            adapter = FakeAdapter(SCRIPT_A)
            drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)
            return mailbox

        mailbox_1 = _drive_fresh()
        mailbox_2 = _drive_fresh()
        self.assertEqual(mailbox_1.to_jsonl(), mailbox_2.to_jsonl())
        self.assertEqual(reduce(mailbox_1.read_all()), reduce(mailbox_2.read_all()))


# ---------------------------------------------------------------------------
# drive(): reproduces Task 4's Fixture B outcome (exhausted budget).
# ---------------------------------------------------------------------------


class DriveExhaustedBudgetTest(unittest.TestCase):
    def _drive(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_B)
        final_state = drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)
        return mailbox, final_state

    def test_reaches_a_named_terminal_state_never_completed(self):
        _, final_state = self._drive()
        self.assertIn(final_state.phase, ("blocked", "awaiting-user-input"))
        self.assertNotEqual(final_state.phase, "completed")
        self.assertEqual(status_of(final_state, "task-a"), "failed")

    def test_dependent_task_never_runs(self):
        mailbox, final_state = self._drive()
        self.assertEqual(status_of(final_state, "task-b"), "pending")
        for envelope in mailbox.read_all():
            self.assertNotEqual(envelope.payload.get("task_id"), "task-b")

    def test_attempts_are_bounded_at_exactly_max_attempts(self):
        mailbox, _ = self._drive()
        request_attempts = sorted(
            envelope.payload["attempt"]
            for envelope in mailbox.read_all()
            if envelope.kind == "request" and envelope.payload.get("task_id") == "task-a"
        )
        self.assertEqual(request_attempts, [1, 2, 3])

    def test_never_reaches_next_tasks_runnable_for_b(self):
        _, final_state = self._drive()
        self.assertEqual(next_tasks(DAG, final_state), ())

    def test_blocked_reentry_returns_existing_state_without_dispatching_sibling(self):
        independent_dag = TaskDag.from_list([
            {"task_id": "task-a", "role": "role-a", "depends_on": []},
            {"task_id": "task-b", "role": "role-b", "depends_on": []},
        ])
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_B)
        blocked = drive(
            independent_dag, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS,
            run_id=RUN_ID,
        )
        before = mailbox.to_jsonl()

        reentered = drive(
            independent_dag, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS,
            run_id=RUN_ID,
        )

        self.assertEqual(reentered, blocked)
        self.assertEqual(mailbox.to_jsonl(), before)
        self.assertEqual(status_of(reentered, "task-b"), "pending")


# ---------------------------------------------------------------------------
# Finding 1: a RETRY decision leaves a durable trace in the mailbox.
# ---------------------------------------------------------------------------


class RetryDecisionRecordedDurablyTest(unittest.TestCase):
    def _drive_and_find_retry_index(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_A)
        final_state = drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)
        envelopes = mailbox.read_all()
        index = next(
            i for i, e in enumerate(envelopes)
            if e.kind == "status" and e.payload.get("decision") == "retry"
        )
        return envelopes, index

    def test_a_retry_decision_is_recorded_exactly_once(self):
        envelopes, index = self._drive_and_find_retry_index()
        retries = [e for e in envelopes if e.kind == "status" and e.payload.get("decision") == "retry"]
        self.assertEqual(len(retries), 1)
        self.assertEqual(retries[0].payload["task_id"], "task-a")
        self.assertEqual(retries[0].payload["critique"], "off-by-one in the boundary check")
        self.assertEqual(retries[0].payload["attempt"], 1)
        self.assertEqual(retries[0].payload["attempts_remaining"], MAX_ATTEMPTS - 1)

    def test_the_retry_record_precedes_the_next_attempts_spawn(self):
        envelopes, retry_index = self._drive_and_find_retry_index()
        next_request_index = next(
            i for i, e in enumerate(envelopes)
            if e.kind == "request" and e.payload.get("task_id") == "task-a"
            and e.payload.get("attempt") == 2
        )
        self.assertLess(retry_index, next_request_index)

    def test_truncating_right_after_a_retry_decision_still_shows_it_was_decided(self):
        # Simulates a crash between recording the retry decision and
        # spawning the next attempt: keep only the envelopes up to and
        # including the retry-decision status envelope, and confirm
        # replaying that truncated mailbox shows a decided retry -- not a
        # task that merely looks abandoned at 'failed' with no further
        # information, which is what this finding exists to rule out.
        envelopes, retry_index = self._drive_and_find_retry_index()
        truncated = Mailbox(envelopes[: retry_index + 1])

        state = replay(truncated)
        self.assertEqual(status_of(state, "task-a"), "failed")
        self.assertEqual(state.context["decision"], "retry")
        self.assertEqual(state.context["task_id"], "task-a")
        self.assertIn("critique", state.context)
        self.assertEqual(state.context["critique"], "off-by-one in the boundary check")


# ---------------------------------------------------------------------------
# Finding 2: enforce_policy and relay_question composed into the loop.
# ---------------------------------------------------------------------------


class EnforcePolicyComposedWithSpawnTest(unittest.TestCase):
    def test_enforce_policy_is_called_once_per_attempt_before_spawn(self):
        calls = []

        class RecordingAdapter(FakeAdapter):
            def enforce_policy(self, *, run_id, hook_name, context=None):
                calls.append((hook_name, dict(context or {})))
                return super().enforce_policy(run_id=run_id, hook_name=hook_name, context=context)

        mailbox = Mailbox()
        adapter = RecordingAdapter(SCRIPT_A)
        drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)

        # task-a attempt 1 (fails), task-a attempt 2 (retry, passes),
        # task-b attempt 1 (passes): three spawns total.
        self.assertEqual([c[0] for c in calls], ["pre-spawn", "pre-spawn", "pre-spawn"])
        self.assertEqual([c[1]["task_id"] for c in calls], ["task-a", "task-a", "task-b"])
        self.assertEqual([c[1]["attempt"] for c in calls], [1, 2, 1])

    def test_enforce_policy_raising_blocked_stops_the_run_before_spawn(self):
        class RefusingAdapter(FakeAdapter):
            def enforce_policy(self, *, run_id, hook_name, context=None):
                raise Blocked(
                    stage="test", reason_code="malformed_checkpoint",
                    detail="policy refused", recovery_action="n/a",
                )

        mailbox = Mailbox()
        adapter = RefusingAdapter(SCRIPT_A)
        with self.assertRaises(Blocked):
            drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)
        self.assertEqual(mailbox.read_all(), ())


class RelayQuestionComposedWithTheGateTest(unittest.TestCase):
    def test_ordinary_exhaustion_is_blocked_without_a_question_envelope(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_B)
        final_state = drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)

        questions = [e for e in mailbox.read_all() if e.kind == "question"]
        self.assertEqual(questions, [])
        self.assertEqual(final_state.phase, "blocked")

    def test_relay_question_is_not_exercised_on_a_run_that_never_blocks(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_A)
        drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)
        questions = [e for e in mailbox.read_all() if e.kind == "question"]
        self.assertEqual(questions, [])


class OrdinaryFailureDoesNotAskRootTest(unittest.TestCase):
    # Only a schema-valid worker question lets decide_failure authorize
    # awaiting-user-input. Exhaustion without one remains terminal blocked.
    def test_ordinary_exhaustion_never_emits_awaiting_user_input(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_B)
        drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)
        phases = [e.payload.get("phase") for e in mailbox.read_all() if e.kind == "status"]
        self.assertIn("blocked", phases)
        self.assertNotIn("awaiting-user-input", phases)


class QuestionFlowTest(unittest.TestCase):
    @staticmethod
    def _answer(**overrides):
        answer = {
            "run_id": RUN_ID, "task_id": "task-a", "attempt": 1,
            "question_id": "q-a-1", "decision": "retry", "text": "retry with the artifact",
        }
        answer.update(overrides)
        return answer

    def test_passed_result_with_question_is_rejected_by_gate(self):
        with self.assertRaises(Blocked):
            gate_result({"task_id": "task-a", "attempt": 1,
                         "outcome": "passed", "question": {
                             "question_id": "q-1", "prompt": "Retry?"}})

    def test_drive_rejects_a_schema_invalid_worker_question(self):
        mailbox = Mailbox()
        adapter = FakeAdapter({
            ("task-a", 1): {
                "outcome": "failed", "critique": "needs a choice",
                "question": {"question_id": "q-a-1"},
            },
        })
        with self.assertRaises(Blocked):
            drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)
        self.assertEqual([e.kind for e in mailbox.read_all()], ["request", "result"])

    def test_drive_rejects_whitespace_question_before_waiting_or_relay_append(self):
        for field in ("question_id", "prompt"):
            question = {"question_id": "q-a-1", "prompt": "Retry?"}
            question[field] = "   "

            class ResultBoundaryAdapter(FakeAdapter):
                result_boundary = None

                def spawn(self, *args, **kwargs):
                    emitted = super().spawn(*args, **kwargs)
                    self.result_boundary = args[0].to_jsonl()
                    return emitted

            with self.subTest(field=field):
                mailbox = Mailbox()
                adapter = ResultBoundaryAdapter({
                    ("task-a", 1): {
                        "outcome": "failed", "critique": "needs a choice",
                        "question": question,
                    },
                })
                with self.assertRaises(Blocked):
                    drive(
                        DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS,
                        run_id=RUN_ID,
                    )
                self.assertEqual(mailbox.to_jsonl(), adapter.result_boundary)
                self.assertEqual(
                    [e.kind for e in mailbox.read_all()], ["request", "result"],
                )

    def test_drive_gates_the_result_appended_to_the_mailbox_not_spawn_return_value(self):
        class MisleadingReturnAdapter(FakeAdapter):
            def spawn(self, *args, **kwargs):
                super().spawn(*args, **kwargs)
                return {"task_id": "task-a", "attempt": 1, "outcome": "failed"}

        mailbox = Mailbox()
        final = drive(
            DAG, MisleadingReturnAdapter(SCRIPT_A), mailbox, AGENT_SPECS,
            MAX_ATTEMPTS, run_id=RUN_ID,
        )
        self.assertEqual(final.phase, "completed")

    def test_question_waits_with_exact_envelopes_and_resume_completes(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_QUESTION)
        waiting = drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)
        self.assertEqual(waiting.phase, "awaiting-user-input")
        statuses = [e for e in mailbox.read_all() if e.kind == "status"]
        questions = [e for e in mailbox.read_all() if e.kind == "question"]
        self.assertEqual(len(statuses), 1)
        self.assertEqual(len(questions), 1)
        self.assertEqual(set(questions[0].payload), {"task_id", "attempt", "critique", "attempts_remaining", "question_id", "prompt"})
        before = mailbox.to_jsonl()
        self.assertEqual(drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID).phase, "awaiting-user-input")
        self.assertEqual(mailbox.to_jsonl(), before)
        final = oqc.resume(
            DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS,
            answer=self._answer(),
        )
        self.assertEqual(final.phase, "completed")
        requests = [e for e in mailbox.read_all() if e.kind == "request" and e.payload["task_id"] == "task-a"]
        self.assertEqual(requests[-1].payload["brief"]["answer_context"], "retry with the artifact")
        self.assertEqual(requests[-1].payload["brief"]["critique"], "needs a choice")

    def test_stop_answer_is_the_only_terminal_event(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_QUESTION)
        drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)
        final = oqc.resume(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, answer={
            "run_id": RUN_ID, "task_id": "task-a", "attempt": 1,
            "question_id": "q-a-1", "decision": "stop", "text": "stop",
        })
        self.assertEqual(len([e for e in mailbox.read_all() if e.kind == "answer"]), 1)
        self.assertEqual(len([e for e in mailbox.read_all() if e.kind == "status" and e.payload.get("phase") == "blocked"]), 0)

    def test_invalid_answers_leave_jsonl_byte_identical(self):
        invalid_answers = (
            self._answer(run_id="wrong-run"),
            self._answer(task_id="task-b"),
            self._answer(attempt=2),
            self._answer(question_id="stale-question"),
            self._answer(decision="continue"),
            self._answer(text="   "),
        )
        for answer in invalid_answers:
            with self.subTest(answer=answer):
                mailbox = Mailbox()
                adapter = FakeAdapter(SCRIPT_QUESTION)
                drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)
                before = mailbox.to_jsonl()
                with self.assertRaises(Blocked):
                    oqc.resume(
                        DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS,
                        answer=answer,
                    )
                self.assertEqual(mailbox.to_jsonl(), before)

    def test_mismatched_resume_budget_is_rejected_before_answer_approval(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_QUESTION)
        drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)
        before = mailbox.to_jsonl()
        with patch("oqc.approve_answer", wraps=approve_answer) as approval:
            with self.assertRaises(Blocked):
                oqc.resume(
                    DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS + 1,
                    answer=self._answer(),
                )
        approval.assert_not_called()
        self.assertEqual(mailbox.to_jsonl(), before)

    def test_duplicate_answer_is_rejected_without_changing_jsonl(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_QUESTION)
        drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)
        answer = self._answer(decision="stop", text="stop")
        oqc.resume(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, answer=answer)
        before = mailbox.to_jsonl()
        with self.assertRaises(Blocked):
            oqc.resume(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, answer=answer)
        self.assertEqual(mailbox.to_jsonl(), before)

    def test_retry_is_rejected_at_zero_budget_but_stop_is_accepted(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_ZERO_BUDGET_QUESTION)
        waiting = drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)
        self.assertEqual(waiting.context["attempt"], 3)
        self.assertEqual(waiting.context["attempts_remaining"], 0)
        before = mailbox.to_jsonl()
        with self.assertRaises(Blocked):
            oqc.resume(
                DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS,
                answer=self._answer(attempt=3, question_id="q-a-3"),
            )
        self.assertEqual(mailbox.to_jsonl(), before)

        stopped = oqc.resume(
            DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS,
            answer=self._answer(
                attempt=3, question_id="q-a-3", decision="stop", text="stop now",
            ),
        )
        self.assertEqual(stopped.phase, "blocked")
        self.assertEqual(attempts_of(stopped, "task-a"), MAX_ATTEMPTS)

    def test_repeated_questions_preserve_attempt_budget_critique_and_answer_context(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_REPEATED_QUESTION)
        first_wait = drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)
        self.assertEqual(first_wait.context["attempts_remaining"], 2)

        second_wait = oqc.resume(
            DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS,
            answer=self._answer(text="first answer"),
        )
        self.assertEqual(second_wait.phase, "awaiting-user-input")
        self.assertEqual(second_wait.context["attempt"], 2)
        self.assertEqual(second_wait.context["attempts_remaining"], 1)
        second_request = _latest(mailbox, kind="request", task_id="task-a", attempt=2)
        self.assertEqual(second_request["brief"]["critique"], "first failure")
        self.assertEqual(second_request["brief"]["answer_context"], "first answer")

        final = oqc.resume(
            DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS,
            answer=self._answer(
                attempt=2, question_id="q-a-2", text="second answer",
            ),
        )
        self.assertEqual(final.phase, "completed")
        self.assertEqual(attempts_of(final, "task-a"), 3)
        third_request = _latest(mailbox, kind="request", task_id="task-a", attempt=3)
        self.assertEqual(third_request["brief"]["critique"], "second failure")
        self.assertEqual(third_request["brief"]["answer_context"], "second answer")

    def test_reloaded_waiting_mailbox_resumes_with_fresh_seeded_adapter_and_verifies(self):
        live_mailbox = Mailbox()
        live_adapter = FakeAdapter(SCRIPT_QUESTION)
        drive(DAG, live_adapter, live_mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)
        live_state = oqc.resume(
            DAG, live_adapter, live_mailbox, AGENT_SPECS, MAX_ATTEMPTS,
            answer=self._answer(),
        )

        waiting_mailbox = Mailbox()
        drive(
            DAG, FakeAdapter(SCRIPT_QUESTION), waiting_mailbox, AGENT_SPECS,
            MAX_ATTEMPTS, run_id=RUN_ID,
        )
        reloaded = Mailbox.from_jsonl(waiting_mailbox.to_jsonl())
        resumed_state = oqc.resume(
            DAG, FakeAdapter(SCRIPT_QUESTION, mailbox=reloaded), reloaded,
            AGENT_SPECS, MAX_ATTEMPTS, answer=self._answer(),
        )

        verified = verify(reloaded)
        self.assertEqual(resumed_state, live_state)
        self.assertEqual(replay(reloaded), resumed_state)
        self.assertEqual(verified.state, resumed_state)
        self.assertEqual(verified.head_hash, reloaded.read_all()[-1].hash())
        self.assertEqual(reloaded.to_jsonl(), live_mailbox.to_jsonl())
        self.assertEqual(verified.head_hash, verify(live_mailbox).head_hash)


# ---------------------------------------------------------------------------
# drive(): input validation and reuse pins.
# ---------------------------------------------------------------------------


class DriveValidationTest(unittest.TestCase):
    def test_a_non_adapter_port_object_is_rejected(self):
        mailbox = Mailbox()
        with self.assertRaises(Blocked):
            drive(DAG, object(), mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)

    def test_zero_max_attempts_is_blocked(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_A)
        with self.assertRaises(Blocked):
            drive(DAG, adapter, mailbox, AGENT_SPECS, 0, run_id=RUN_ID)

    def test_boolean_max_attempts_is_rejected(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_A)
        with self.assertRaises(Blocked):
            drive(DAG, adapter, mailbox, AGENT_SPECS, True, run_id=RUN_ID)

    def test_missing_agent_spec_for_a_role_is_blocked(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_A)
        with self.assertRaises(Blocked) as ctx:
            drive(DAG, adapter, mailbox, {}, MAX_ATTEMPTS, run_id=RUN_ID)
        self.assertEqual(ctx.exception.reason_code, "missing_target")


class ReusesKernelPrimitivesTest(unittest.TestCase):
    # "No reimplementation of scheduling or routing" -- pinned directly by
    # import identity, not merely by behaviour, so a future edit that
    # copies these functions instead of importing them is caught here.
    def test_oqc_reuses_router_and_gate_functions_by_identity(self):
        import gate
        import router as router_module

        self.assertIs(oqc.next_tasks, router_module.next_tasks)
        self.assertIs(oqc.validate_pair, router_module.validate_pair)
        self.assertIs(oqc.gate_result, gate.gate_result)
        self.assertIs(oqc.retry_or_block, gate.retry_or_block)


# ---------------------------------------------------------------------------
# replay()
# ---------------------------------------------------------------------------


class ReplayTest(unittest.TestCase):
    def test_replay_of_a_reloaded_mailbox_equals_the_live_run_state(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_A)
        live_state = drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)

        reloaded = Mailbox.from_jsonl(mailbox.to_jsonl())
        self.assertEqual(replay(reloaded), live_state)

    def test_replay_is_exactly_reduce_over_read_all(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_A)
        drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)
        self.assertEqual(replay(mailbox), reduce(mailbox.read_all()))


# ---------------------------------------------------------------------------
# Nothing in the kernel imports oqc.
# ---------------------------------------------------------------------------


class KernelStaysImportableWithoutOqcTest(unittest.TestCase):
    KERNEL_MODULE_NAMES = (
        "kernel_specs", "run_state", "router", "mailbox", "gate",
        "adapter_port", "fake_adapter", "compile_prompt", "qc_lib",
    )

    def test_no_kernel_module_source_references_oqc(self):
        for name in self.KERNEL_MODULE_NAMES:
            module = importlib.import_module(name)
            source = inspect.getsource(module)
            with self.subTest(module=name):
                self.assertNotIn("oqc", source.lower())


# ---------------------------------------------------------------------------
# The thin __main__ CLI over replay and verify.
# ---------------------------------------------------------------------------


class CliTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.addCleanup(self._cleanup_tmpdir)

    def _cleanup_tmpdir(self):
        for name in os.listdir(self._tmpdir):
            os.remove(os.path.join(self._tmpdir, name))
        os.rmdir(self._tmpdir)

    def _write_mailbox_file(self, mailbox, name="mailbox.jsonl"):
        path = os.path.join(self._tmpdir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(mailbox.to_jsonl())
        return path

    def _run_cli(self, argv):
        out = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stdout(out):
            with patch.object(sys, "argv", ["oqc"] + argv):
                oqc.main()
        return ctx.exception.code, out.getvalue()

    def _completed_mailbox(self):
        # Built directly via _chain, not drive()/FakeAdapter: these CLI
        # tests only need *some* valid, completed, correctly-chained
        # mailbox file to read back -- how it reached 'completed' is
        # drive()'s own, separately-tested concern.
        mailbox = Mailbox()
        for envelope in _chain(
            _envelope_data(
                envelope_id="env-1", kind="request",
                payload={"task_id": "task-a", "attempt": 1, "brief": {}},
            ),
            _envelope_data(
                envelope_id="env-2", kind="result", sender="agent:worker-a",
                recipient="orchestrator",
                payload={"task_id": "task-a", "attempt": 1, "outcome": "passed"},
            ),
            _envelope_data(
                envelope_id="env-3", kind="status", sender="orchestrator",
                recipient="root", payload={"phase": "completed"},
            ),
        ):
            mailbox.append(envelope)
        return mailbox

    def test_replay_subcommand_prints_derived_state_and_exits_zero(self):
        path = self._write_mailbox_file(self._completed_mailbox())

        code, output = self._run_cli(["replay", path])
        self.assertEqual(code, 0)
        printed = json.loads(output)
        self.assertEqual(printed["phase"], "completed")
        self.assertEqual(printed["task_status"]["task-a"], "passed")

    def test_verify_subcommand_on_a_valid_mailbox_exits_zero(self):
        path = self._write_mailbox_file(self._completed_mailbox())

        code, output = self._run_cli(["verify", path])
        self.assertEqual(code, 0)
        printed = json.loads(output)
        self.assertEqual(printed["phase"], "completed")

    def test_verify_subcommand_on_a_valid_mailbox_prints_the_head_hash(self):
        # Outcome 3 Task 1: the CLI must surface head_hash too, not only
        # the derived state -- it is the value a caller anchors externally
        # (see verify's docstring).
        mailbox = self._completed_mailbox()
        path = self._write_mailbox_file(mailbox)

        code, output = self._run_cli(["verify", path])
        self.assertEqual(code, 0)
        printed = json.loads(output)
        self.assertEqual(printed["head_hash"], mailbox.read_all()[-1].hash())

    def test_verify_subcommand_on_a_tampered_file_exits_two_with_a_blocked_payload(self):
        # A hand-crafted JSONL file with a duplicate envelope_id: caught by
        # mailbox.Mailbox.from_jsonl itself before verify() even runs --
        # still a qc_lib.Blocked either way, so the CLI's exit-code
        # contract holds regardless of which layer raised it.
        line = Envelope.from_dict(_envelope_data(
            envelope_id="env-1", kind="status", sender="orchestrator",
            recipient="root", payload={"phase": "discovery"},
        )).to_json()
        path = os.path.join(self._tmpdir, "tampered.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(line + "\n" + line + "\n")

        code, output = self._run_cli(["verify", path])
        self.assertEqual(code, 2)
        payload = json.loads(output)
        self.assertEqual(payload["status"], "blocked")

    def test_missing_file_exits_two_with_a_named_blocked_payload(self):
        code, output = self._run_cli(["replay", os.path.join(self._tmpdir, "nonexistent.jsonl")])
        self.assertEqual(code, 2)
        payload = json.loads(output)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["reason_code"], "missing_target")

    def test_a_directory_path_exits_two_with_a_blocked_payload_not_a_traceback(self):
        # FINDING 3 (round 2 quality review): `oqc.py replay <a directory>`
        # used to raise an uncaught IsADirectoryError and exit 1 with a
        # bare traceback, unlike every other failure path in this CLI.
        code, output = self._run_cli(["replay", self._tmpdir])
        self.assertEqual(code, 2)
        payload = json.loads(output)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["reason_code"], "missing_target")
        self.assertIn(self._tmpdir, payload["detail"])

    def test_invalid_utf8_file_exits_two_with_a_blocked_payload_not_a_traceback(self):
        # FINDING 3's other half: a file that exists and opens but is not
        # valid UTF-8 used to raise an uncaught UnicodeDecodeError.
        path = os.path.join(self._tmpdir, "invalid-utf8.jsonl")
        with open(path, "wb") as fh:
            fh.write(b"\xff\xfe\x00\x01not valid utf-8")

        code, output = self._run_cli(["verify", path])
        self.assertEqual(code, 2)
        payload = json.loads(output)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["reason_code"], "malformed_checkpoint")
        self.assertIn(path, payload["detail"])

    def test_an_empty_file_still_replays_cleanly(self):
        # Verified-good path per root's requirement: must not be disturbed
        # by the new OSError/UnicodeDecodeError handling.
        path = os.path.join(self._tmpdir, "empty.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("")

        code, output = self._run_cli(["replay", path])
        self.assertEqual(code, 0)
        printed = json.loads(output)
        self.assertEqual(printed["phase"], "discovery")
        self.assertEqual(printed["envelope_count"], 0)

    def test_a_json_array_line_still_exits_two_via_mailbox_from_jsonl(self):
        # Verified-good path per root's requirement: a structurally-invalid
        # JSONL line (a JSON array instead of an envelope object) is
        # UTF-8-clean and opens fine -- it must still be rejected by
        # Mailbox.from_jsonl/Envelope.from_dict, not silently accepted,
        # and not disturbed by this round's new exception handling.
        path = os.path.join(self._tmpdir, "not-an-envelope.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("[1, 2, 3]\n")

        code, output = self._run_cli(["replay", path])
        self.assertEqual(code, 2)
        payload = json.loads(output)
        self.assertEqual(payload["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
