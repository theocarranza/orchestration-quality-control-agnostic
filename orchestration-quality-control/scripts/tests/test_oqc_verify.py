"""Tests for oqc.py: verify() and tamper detection."""

import json
import unittest

from fake_adapter import FakeAdapter
from kernel_specs import AgentSpec, Envelope, GENESIS_HASH, TaskDag
from mailbox import Mailbox
from oqc import drive, verify
from qc_lib import Blocked
from router import validate_pair
from run_state import reduce, status_of

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
    chained = []
    previous_hash = GENESIS_HASH
    for data in envelope_data_dicts:
        envelope = Envelope.from_dict({**data, "previous_hash": previous_hash})
        chained.append(envelope)
        previous_hash = envelope.hash()
    return chained


def _corrupt_mailbox(envelopes):
    mailbox = Mailbox()
    mailbox._events = list(envelopes)
    return mailbox


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



if __name__ == "__main__":
    unittest.main()
