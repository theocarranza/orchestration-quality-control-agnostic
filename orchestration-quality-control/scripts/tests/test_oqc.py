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


class AwaitingUserInputRemainsUnreachableTest(unittest.TestCase):
    # ADR 0014 decision 4 / gate.py's own reservation note beside
    # AWAITING_USER_INPUT: that phase is reserved for a question-triggered
    # transition this kernel slice does not build. drive() composes
    # relay_question into the terminal 'blocked' path (see
    # RelayQuestionComposedWithTheGateTest above) but deliberately never
    # manufactures a phase this model-free, judgment-free loop has no
    # basis to declare on its own -- gate.retry_or_block, the sole
    # authority over that decision, never returns it. This test pins that
    # scope decision.
    def test_drive_never_emits_awaiting_user_input(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_B)
        drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)
        phases = [e.payload.get("phase") for e in mailbox.read_all() if e.kind == "status"]
        self.assertIn("blocked", phases)
        self.assertNotIn("awaiting-user-input", phases)


class QuestionFlowTest(unittest.TestCase):
    def test_passed_result_with_question_is_rejected_by_gate(self):
        with self.assertRaises(Blocked):
            gate_result({"task_id": "task-a", "attempt": 1,
                         "outcome": "passed", "question": {
                             "question_id": "q-1", "prompt": "Retry?"}})

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
        state = reduce(mailbox.read_all())
        final = oqc.resume(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, answer={
            "run_id": RUN_ID, "task_id": "task-a", "attempt": 1,
            "question_id": "q-a-1", "decision": "retry", "text": "retry with the artifact",
        })
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
# verify(): each named tampering class, plus the two extra structural
# checks the task description names (illegal pairs, run_id consistency).
# ---------------------------------------------------------------------------


class VerifyValidMailboxTest(unittest.TestCase):
    def test_verify_of_a_valid_drive_run_returns_the_live_state(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_A)
        live_state = drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)
        self.assertEqual(verify(mailbox).state, live_state)

    def test_verify_of_a_valid_drive_run_returns_the_head_hash(self):
        # Outcome 3 Task 1: verify() must hand back the mailbox's head
        # hash so a caller can anchor it externally -- it is the one entry
        # nothing else in the mailbox protects (see verify's docstring).
        mailbox = Mailbox()
        adapter = FakeAdapter(SCRIPT_A)
        drive(DAG, adapter, mailbox, AGENT_SPECS, MAX_ATTEMPTS, run_id=RUN_ID)
        result = verify(mailbox)
        self.assertEqual(result.head_hash, mailbox.read_all()[-1].hash())

    def test_verify_docstring_documents_the_hash_chain_and_the_last_entry_caveat(self):
        # Documentation-truth guard: verify() is no longer purely
        # structural (Outcome 3 Task 1 adds the cryptographic hash chain),
        # so the old "not cryptographic" disclaimer must be gone -- but the
        # new, narrower caveat (the last entry in a mailbox is never
        # protected by this chain) must be stated instead, not silently
        # dropped.
        doc = verify.__doc__.lower()
        self.assertNotIn("not cryptographic", doc)
        self.assertIn("hash chain", doc)
        self.assertIn("last envelope", doc)

    def test_a_request_in_flight_with_no_result_yet_still_verifies_clean(self):
        # Guard against over-rejection (root's explicit requirement for
        # this round): a task that is genuinely still running -- one
        # 'request', no 'result' at all yet -- must not be treated as any
        # kind of violation. Built directly (not through FakeAdapter/drive)
        # since a single in-flight request needs nothing an adapter loop
        # would add.
        request_only = _corrupt_mailbox([_envelope(
            envelope_id="env-1", kind="request",
            payload={"task_id": "task-a", "attempt": 1, "brief": {}},
        )])
        result = verify(request_only)
        self.assertEqual(status_of(result.state, "task-a"), "running")


class VerifyDuplicateResultTest(unittest.TestCase):
    # FINDING 1 (round 2 quality review): a second 'result' for a
    # (task_id, attempt) pair already answered used to be silently
    # accepted, letting a duplicated or forged result override a genuine
    # outcome. Root's exact reproduction, via plain Mailbox.append (no
    # tampering, no bypass of the public API):
    #     request(task-a, attempt=1)
    #     result(task-a, attempt=1, outcome=failed, critique="real failure")
    #     result(task-a, attempt=1, outcome=passed)          # second result
    def test_a_duplicate_result_overriding_a_real_failure_is_blocked(self):
        mailbox = Mailbox()
        request, first_result, second_result = _chain(
            _envelope_data(
                envelope_id="env-1", kind="request",
                payload={"task_id": "task-a", "attempt": 1, "brief": {}},
            ),
            _envelope_data(
                envelope_id="env-2", kind="result", sender="agent:worker-a",
                recipient="orchestrator",
                payload={"task_id": "task-a", "attempt": 1, "outcome": "failed", "critique": "real failure"},
            ),
            _envelope_data(
                envelope_id="env-3", kind="result", sender="agent:worker-a",
                recipient="orchestrator",
                payload={"task_id": "task-a", "attempt": 1, "outcome": "passed"},
            ),
        )
        # Built through the ordinary, un-bypassed public API, with a
        # genuine (not tampered) hash chain -- this is not a chain-tamper
        # scenario, it is what a flaky transport's duplicated callback (or
        # an outright forged second report) looks like on the wire.
        mailbox.append(request)
        mailbox.append(first_result)
        mailbox.append(second_result)

        with self.assertRaises(Blocked) as ctx:
            verify(mailbox)
        self.assertIn("task-a", ctx.exception.detail)
        self.assertIn("1", ctx.exception.detail)

    def test_a_second_result_with_the_same_outcome_is_still_blocked(self):
        # The check is "already answered", not "answered differently" --
        # a second identical result is exactly as much a forged/duplicated
        # report as one with a different outcome, and must not be waved
        # through just because it happens to agree.
        mailbox = Mailbox()
        request, first_result, second_result = _chain(
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
                envelope_id="env-3", kind="result", sender="agent:worker-a",
                recipient="orchestrator",
                payload={"task_id": "task-a", "attempt": 1, "outcome": "passed"},
            ),
        )
        mailbox.append(request)
        mailbox.append(first_result)
        mailbox.append(second_result)

        with self.assertRaises(Blocked):
            verify(mailbox)


class VerifyAttemptlessForgeryTest(unittest.TestCase):
    # FINDING 2 (round 2 quality review): a 'result' with no `attempt` at
    # all used to satisfy verify's old task_id-only fallback against any
    # prior request for that task_id, regardless of which attempt it
    # actually resolved. Root's exact reproduction:
    #     request(task-b, attempt=1)      # genuinely in flight
    #     result(task-b, outcome=passed)  # no attempt key
    # Closed at the source in run_state.py (attempt is now mandatory on a
    # task-resolving result), so this is rejected before it can even be
    # reduced -- and independently by verify's own check 3, which no
    # longer has a task_id-only fallback to fall back to.
    def test_an_attempt_less_result_is_rejected_not_paired_by_task_id_alone(self):
        mailbox = Mailbox()
        request, forged_result = _chain(
            _envelope_data(
                envelope_id="env-1", kind="request",
                payload={"task_id": "task-b", "attempt": 1, "brief": {}},
            ),
            _envelope_data(
                envelope_id="env-2", kind="result", sender="agent:worker-a",
                recipient="orchestrator",
                payload={"task_id": "task-b", "outcome": "passed"},  # no attempt
            ),
        )
        mailbox.append(request)
        mailbox.append(forged_result)

        with self.assertRaises(Blocked) as ctx:
            verify(mailbox)
        self.assertIn("task-b", ctx.exception.detail)


class VerifyDuplicateEnvelopeIdTest(unittest.TestCase):
    def test_a_duplicated_envelope_id_is_blocked(self):
        e1, e2 = _chain(
            _envelope_data(
                envelope_id="env-1", kind="status", sender="orchestrator",
                recipient="root", payload={"phase": "orchestration"},
            ),
            _envelope_data(
                envelope_id="env-1", kind="status", sender="orchestrator",
                recipient="root", payload={"phase": "completed"},
            ),
        )
        mailbox = _corrupt_mailbox([e1, e2])
        with self.assertRaises(Blocked) as ctx:
            verify(mailbox)
        self.assertIn("env-1", ctx.exception.detail)
        self.assertIn("duplicate", ctx.exception.detail.lower())


class VerifyForgedResultTest(unittest.TestCase):
    def test_a_result_with_no_preceding_request_anywhere_is_blocked(self):
        result_only = _envelope(
            envelope_id="env-1", kind="result", sender="agent:worker-a",
            recipient="orchestrator",
            payload={"task_id": "task-a", "attempt": 1, "outcome": "passed"},
        )
        mailbox = _corrupt_mailbox([result_only])
        with self.assertRaises(Blocked) as ctx:
            verify(mailbox)
        self.assertIn("no preceding", ctx.exception.detail.lower())


class VerifyDeletionTest(unittest.TestCase):
    def test_deleting_a_request_leaves_its_result_orphaned_and_blocked(self):
        # Built directly via _chain, not FakeAdapter/adapter.spawn: the
        # "delete an entry" tamper this test proves needs only a genuine
        # request+result pair to delete from, nothing an adapter loop adds.
        _request, result = _chain(
            _envelope_data(
                envelope_id="env-1", kind="request",
                payload={"task_id": "task-a", "attempt": 1, "brief": {}},
            ),
            _envelope_data(
                envelope_id="env-2", kind="result", sender="agent:worker-a",
                recipient="orchestrator",
                payload={"task_id": "task-a", "attempt": 1, "outcome": "passed"},
            ),
        )

        tampered = _corrupt_mailbox([result])  # request deleted
        with self.assertRaises(Blocked) as ctx:
            verify(tampered)
        self.assertIn("no preceding", ctx.exception.detail.lower())


class VerifyReorderingTest(unittest.TestCase):
    def test_a_result_moved_ahead_of_its_request_is_blocked(self):
        request, result = _chain(
            _envelope_data(
                envelope_id="env-1", kind="request",
                payload={"task_id": "task-a", "attempt": 1, "brief": {}},
            ),
            _envelope_data(
                envelope_id="env-2", kind="result", sender="agent:worker-a",
                recipient="orchestrator",
                payload={"task_id": "task-a", "attempt": 1, "outcome": "passed"},
            ),
        )

        reordered = _corrupt_mailbox([result, request])
        with self.assertRaises(Blocked) as ctx:
            verify(reordered)
        self.assertIn("no preceding", ctx.exception.detail.lower())


class VerifyBrokenAttemptSequenceTest(unittest.TestCase):
    def test_a_skipped_attempt_number_is_blocked(self):
        req_1, res_1, req_3, res_3 = _chain(
            _envelope_data(
                envelope_id="env-1", kind="request",
                payload={"task_id": "task-a", "attempt": 1, "brief": {}},
            ),
            _envelope_data(
                envelope_id="env-2", kind="result", sender="agent:worker-a",
                recipient="orchestrator",
                payload={"task_id": "task-a", "attempt": 1, "outcome": "failed", "critique": "x"},
            ),
            _envelope_data(
                envelope_id="env-3", kind="request",
                payload={"task_id": "task-a", "attempt": 3, "brief": {}},  # skips attempt 2
            ),
            _envelope_data(
                envelope_id="env-4", kind="result", sender="agent:worker-a",
                recipient="orchestrator",
                payload={"task_id": "task-a", "attempt": 3, "outcome": "passed"},
            ),
        )
        mailbox = _corrupt_mailbox([req_1, res_1, req_3, res_3])
        with self.assertRaises(Blocked) as ctx:
            verify(mailbox)
        self.assertIn("attempt", ctx.exception.detail.lower())


class VerifyIllegalSenderRecipientPairTest(unittest.TestCase):
    def test_a_worker_to_worker_envelope_is_blocked(self):
        illegal = _envelope(
            envelope_id="env-1", kind="request", sender="agent:worker-a",
            recipient="agent:worker-b",
            payload={"task_id": "task-a", "attempt": 1, "brief": {}},
        )
        mailbox = _corrupt_mailbox([illegal])
        with self.assertRaises(Blocked) as ctx:
            verify(mailbox)
        self.assertIn("isolation", ctx.exception.detail.lower())


class VerifyRunIdConsistencyTest(unittest.TestCase):
    def test_mixed_run_ids_are_blocked(self):
        e1 = _envelope(
            envelope_id="env-1", run_id="run-1", kind="status",
            sender="orchestrator", recipient="root", payload={"phase": "discovery"},
        )
        e2 = _envelope(
            envelope_id="env-2", run_id="run-2", kind="status",
            sender="orchestrator", recipient="root", payload={"phase": "completed"},
        )
        mailbox = _corrupt_mailbox([e1, e2])
        with self.assertRaises(Blocked):
            verify(mailbox)


# ---------------------------------------------------------------------------
# Outcome 3 Task 1: the hash chain catches what Outcome 2's purely
# structural checks could not -- a payload-only tamper that disturbs no
# id, no pairing, and no attempt sequencing -- and, symmetrically, cannot
# catch a tamper confined to the mailbox's very last entry.
# ---------------------------------------------------------------------------


class VerifyChainCatchesPayloadOnlyTamperTest(unittest.TestCase):
    def test_a_result_outcome_flip_that_breaks_no_structural_check_is_caught(self):
        # The exact scenario the pre-Outcome-3 verify() docstring named as
        # out of reach: an attacker edits a result's outcome from 'failed'
        # to 'passed' without touching any id, pairing, or attempt number.
        # A third envelope (the status closing out the run) is required so
        # the tampered entry is NOT the mailbox's last one -- tampering the
        # last entry is a different, undetectable case (see
        # VerifyLastEnvelopeUnprotectedTest below).
        request, real_result, status = _chain(
            _envelope_data(
                envelope_id="env-1", kind="request",
                payload={"task_id": "task-a", "attempt": 1, "brief": {}},
            ),
            _envelope_data(
                envelope_id="env-2", kind="result", sender="agent:worker-a",
                recipient="orchestrator",
                payload={"task_id": "task-a", "attempt": 1, "outcome": "failed", "critique": "real failure"},
            ),
            _envelope_data(
                envelope_id="env-3", kind="status", sender="orchestrator",
                recipient="root", payload={"phase": "blocked"},
            ),
        )

        # Flip the result's outcome, keeping its own id, pairing, and
        # previous_hash exactly as they were -- so id-uniqueness (check 1),
        # legal pairing (check 2), and request/response pairing (check 3)
        # all still hold for this envelope in isolation. Nothing about this
        # single edit is structurally invalid; only the fact that it
        # changes env-2's hash -- which env-3's previous_hash was computed
        # against before the edit -- makes it detectable at all.
        tampered_result = Envelope.from_dict({
            **real_result.to_dict(),
            "payload": {"task_id": "task-a", "attempt": 1, "outcome": "passed"},
        })
        self.assertNotEqual(tampered_result.hash(), real_result.hash())

        tampered_mailbox = _corrupt_mailbox([request, tampered_result, status])
        with self.assertRaises(Blocked) as ctx:
            verify(tampered_mailbox)
        self.assertIn("env-3", ctx.exception.detail)
        self.assertIn("chain", ctx.exception.detail.lower())

        # Confirm this is genuinely the tampering-entry-N-breaks-entry-N+1
        # shape, not a coincidence of check ordering: env-2 (the tampered
        # entry itself) still passes id/pairing/request-response cleanly on
        # its own -- it is specifically env-3, the entry *after* it, whose
        # previous_hash no longer matches.
        tamper_with_no_successor = _corrupt_mailbox([request, tampered_result])
        # Two envelopes only (no env-3 to disagree with the tampered hash):
        # this must verify cleanly, proving the tamper alone is invisible
        # without something after it to carry the original hash forward.
        verify(tamper_with_no_successor)


class VerifyLastEnvelopeUnprotectedTest(unittest.TestCase):
    # The documented consequence: nothing follows the last envelope in a
    # mailbox to carry its hash forward, so a tamper confined to it alone
    # is invisible to this chain -- this is not a bug, it is the reason
    # verify() returns head_hash for a caller to anchor externally.
    def test_tampering_only_the_last_envelope_is_not_caught_by_verify(self):
        request, real_result = _chain(
            _envelope_data(
                envelope_id="env-1", kind="request",
                payload={"task_id": "task-a", "attempt": 1, "brief": {}},
            ),
            _envelope_data(
                envelope_id="env-2", kind="result", sender="agent:worker-a",
                recipient="orchestrator",
                payload={"task_id": "task-a", "attempt": 1, "outcome": "failed", "critique": "real failure"},
            ),
        )
        tampered_result = Envelope.from_dict({
            **real_result.to_dict(),
            "payload": {"task_id": "task-a", "attempt": 1, "outcome": "passed"},
        })
        self.assertNotEqual(tampered_result.hash(), real_result.hash())

        tampered_mailbox = _corrupt_mailbox([request, tampered_result])

        # No exception: the tamper is confined to the last entry, so
        # nothing in this mailbox disagrees with it.
        result = verify(tampered_mailbox)
        self.assertEqual(status_of(result.state, "task-a"), "passed")  # the tampered outcome went through
        # head_hash reflects the TAMPERED content -- a caller who had
        # anchored the pre-tamper head hash from an earlier verify() call
        # would see a mismatch when comparing against this one, which is
        # exactly how this gap is meant to be closed externally.
        self.assertEqual(result.head_hash, tampered_result.hash())
        self.assertNotEqual(result.head_hash, real_result.hash())


class VerifyChainRoundTripsThroughJsonlTest(unittest.TestCase):
    def test_a_valid_chain_survives_to_jsonl_from_jsonl_and_still_verifies(self):
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

        live_result = verify(mailbox)

        reloaded = Mailbox.from_jsonl(mailbox.to_jsonl())
        reloaded_result = verify(reloaded)

        self.assertEqual(reloaded_result.state, live_result.state)
        self.assertEqual(reloaded_result.head_hash, live_result.head_hash)
        # And the round trip itself is byte-stable, exactly like every
        # other Mailbox round trip in this kernel.
        self.assertEqual(reloaded.to_jsonl(), mailbox.to_jsonl())

    def test_a_tampered_chain_still_fails_verify_after_a_round_trip(self):
        # The chain-tamper detection above must survive serialisation too
        # -- a tamper is not somehow laundered clean by writing it to disk
        # and reading it back.
        request, real_result, status = _chain(
            _envelope_data(
                envelope_id="env-1", kind="request",
                payload={"task_id": "task-a", "attempt": 1, "brief": {}},
            ),
            _envelope_data(
                envelope_id="env-2", kind="result", sender="agent:worker-a",
                recipient="orchestrator",
                payload={"task_id": "task-a", "attempt": 1, "outcome": "failed", "critique": "real failure"},
            ),
            _envelope_data(
                envelope_id="env-3", kind="status", sender="orchestrator",
                recipient="root", payload={"phase": "blocked"},
            ),
        )
        tampered_result = Envelope.from_dict({
            **real_result.to_dict(),
            "payload": {"task_id": "task-a", "attempt": 1, "outcome": "passed"},
        })
        tampered_mailbox = _corrupt_mailbox([request, tampered_result, status])
        tampered_jsonl = tampered_mailbox.to_jsonl()

        reloaded = Mailbox.from_jsonl(tampered_jsonl)
        with self.assertRaises(Blocked) as ctx:
            verify(reloaded)
        self.assertIn("chain", ctx.exception.detail.lower())


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
