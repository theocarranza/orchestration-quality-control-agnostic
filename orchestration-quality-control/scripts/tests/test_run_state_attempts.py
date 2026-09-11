"""Tests for run_state attempt validation, derivation, and mappings."""

import unittest

from kernel_specs import Envelope, GENESIS_HASH
from qc_lib import Blocked
from run_state import attempts_of, reduce, status_of

def _request_with_attempt(task_id, attempt, *, envelope_id, run_id="run-1"):
    return Envelope.from_dict({
        "schema_version": 2,
        "previous_hash": GENESIS_HASH,
        "envelope_id": envelope_id,
        "run_id": run_id,
        "sender": "orchestrator",
        "recipient": "agent:worker-1",
        "kind": "request",
        "payload": {"task_id": task_id, "attempt": attempt},
        "created_at": "2026-09-04T12:00:00Z",
    })


def _result_with_attempt(task_id, attempt, outcome, *, envelope_id, run_id="run-1"):
    return Envelope.from_dict({
        "schema_version": 2,
        "previous_hash": GENESIS_HASH,
        "envelope_id": envelope_id,
        "run_id": run_id,
        "sender": "agent:worker-1",
        "recipient": "orchestrator",
        "kind": "result",
        "payload": {"task_id": task_id, "attempt": attempt, "outcome": outcome},
        "created_at": "2026-09-04T12:00:01Z",
    })


class RequestAttemptValidationTest(unittest.TestCase):
    # Outcome 2 Task 4 quality-review FIX 4(a), and its round-3 follow-up:
    # `attempt` is now MANDATORY on a task-dispatching 'request' envelope,
    # not merely validated when present. An earlier round made it
    # presence-gated exactly like task_id, to avoid breaking a
    # then-frozen test_router.py fixture; root reproduced the resulting
    # gap directly (three requests with no attempt at all silently
    # reduced to attempts_of == 0) and re-scoped test_router.py (this
    # round's widened scope) rather than leave the guarantee defeatable
    # by omission. See run_state.py's module docstring for the full
    # history.

    def test_valid_attempt_on_request_is_accepted_and_recorded(self):
        state = reduce([_request_with_attempt("task-1", 1, envelope_id="env-1")])
        self.assertEqual(attempts_of(state, "task-1"), 1)

    def test_missing_attempt_on_request_is_blocked(self):
        request = Envelope.from_dict({
            "schema_version": 2,
            "previous_hash": GENESIS_HASH,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "orchestrator",
            "recipient": "agent:worker-1",
            "kind": "request",
            "payload": {"task_id": "task-1"},
            "created_at": "2026-09-04T12:00:00Z",
        })
        with self.assertRaises(Blocked) as ctx:
            reduce([request])
        self.assertIn("attempt", ctx.exception.detail)

    def test_three_requests_with_no_attempt_for_one_task_is_blocked(self):
        # Root's exact reproduction: three 'request' envelopes for the
        # same task with NO attempt key at all used to reduce cleanly to
        # attempts_of == 0 and status 'running' -- an unenforced
        # convention identical in shape to the one FIX 4 itself
        # eliminated for task_id/outcome. There is no valid count this
        # task could silently settle at, so this must raise (on the
        # first such envelope, since reduce is a left fold that stops at
        # the first Blocked -- see test_missing_attempt_on_request_is_blocked
        # for that single-envelope case in isolation).
        def _request_without_attempt(envelope_id):
            return Envelope.from_dict({
                "schema_version": 2,
                "previous_hash": GENESIS_HASH,
                "envelope_id": envelope_id,
                "run_id": "run-1",
                "sender": "orchestrator",
                "recipient": "agent:worker-1",
                "kind": "request",
                "payload": {"task_id": "task-1"},
                "created_at": "2026-09-04T12:00:00Z",
            })

        with self.assertRaises(Blocked) as ctx:
            reduce([
                _request_without_attempt("env-1"),
                _request_without_attempt("env-2"),
                _request_without_attempt("env-3"),
            ])
        self.assertIn("attempt", ctx.exception.detail)

    def test_non_integer_attempt_on_request_is_blocked(self):
        request = Envelope.from_dict({
            "schema_version": 2,
            "previous_hash": GENESIS_HASH,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "orchestrator",
            "recipient": "agent:worker-1",
            "kind": "request",
            "payload": {"task_id": "task-1", "attempt": "1"},
            "created_at": "2026-09-04T12:00:00Z",
        })
        with self.assertRaises(Blocked) as ctx:
            reduce([request])
        self.assertIn("attempt", ctx.exception.detail)

    def test_negative_attempt_on_request_is_blocked(self):
        with self.assertRaises(Blocked) as ctx:
            reduce([_request_with_attempt("task-1", -1, envelope_id="env-1")])
        self.assertIn("attempt", ctx.exception.detail)

    def test_boolean_attempt_on_request_is_blocked(self):
        # bool is a subclass of int; True/False must not silently pass as
        # 1/0 (mirrors kernel_specs._require_const_int's guard).
        request = Envelope.from_dict({
            "schema_version": 2,
            "previous_hash": GENESIS_HASH,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "orchestrator",
            "recipient": "agent:worker-1",
            "kind": "request",
            "payload": {"task_id": "task-1", "attempt": True},
            "created_at": "2026-09-04T12:00:00Z",
        })
        with self.assertRaises(Blocked) as ctx:
            reduce([request])
        self.assertIn("attempt", ctx.exception.detail)

    def test_none_attempt_on_request_is_blocked(self):
        # Presence, not truthiness: an explicit attempt=None is present
        # but invalid, and must be rejected exactly like a missing-but-
        # required task_id already is.
        request = Envelope.from_dict({
            "schema_version": 2,
            "previous_hash": GENESIS_HASH,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "orchestrator",
            "recipient": "agent:worker-1",
            "kind": "request",
            "payload": {"task_id": "task-1", "attempt": None},
            "created_at": "2026-09-04T12:00:00Z",
        })
        with self.assertRaises(Blocked) as ctx:
            reduce([request])
        self.assertIn("attempt", ctx.exception.detail)


class ResultAttemptValidationTest(unittest.TestCase):
    # FIX 4(a)'s other half: type validation on 'result' payloads, plus
    # (Outcome 2 Task 5 quality-review FINDING 2) mandatory presence too,
    # exactly like 'request' -- but still no sequencing rule, since a
    # result never claims a *new* attempt the way a request does; see
    # ResultAttemptMandatoryTest below for the presence guarantee itself
    # and the module docstring for why root reversed the original
    # presence-gated design.

    def test_valid_attempt_on_result_is_accepted(self):
        state = reduce([_result_with_attempt("task-1", 1, "passed", envelope_id="env-1")])
        self.assertEqual(status_of(state, "task-1"), "passed")

    def test_non_integer_attempt_on_result_is_blocked(self):
        result = Envelope.from_dict({
            "schema_version": 2,
            "previous_hash": GENESIS_HASH,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "agent:worker-1",
            "recipient": "orchestrator",
            "kind": "result",
            "payload": {"task_id": "task-1", "attempt": "1", "outcome": "passed"},
            "created_at": "2026-09-04T12:00:00Z",
        })
        with self.assertRaises(Blocked) as ctx:
            reduce([result])
        self.assertIn("attempt", ctx.exception.detail)

    def test_negative_attempt_on_result_is_blocked(self):
        with self.assertRaises(Blocked) as ctx:
            reduce([_result_with_attempt("task-1", -1, "passed", envelope_id="env-1")])
        self.assertIn("attempt", ctx.exception.detail)


class ResultAttemptMandatoryTest(unittest.TestCase):
    # Outcome 2 Task 5 quality-review FINDING 2: `attempt` is now
    # MANDATORY on a task-resolving 'result' envelope (one carrying both
    # `task_id` and `outcome`), mirroring RequestAttemptValidationTest's
    # coverage of the same guarantee on 'request'. Root reproduced the
    # exact gap this closes: an attempt-less result let oqc.verify's
    # (task_id, attempt) pairing fall back to a weaker task_id-only match,
    # so a forged result with no attempt at all could resolve a task no
    # specific attempt of ever actually corresponded to.

    def test_missing_attempt_on_a_task_resolving_result_is_blocked(self):
        result = Envelope.from_dict({
            "schema_version": 2,
            "previous_hash": GENESIS_HASH,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "agent:worker-1",
            "recipient": "orchestrator",
            "kind": "result",
            "payload": {"task_id": "task-1", "outcome": "passed"},
            "created_at": "2026-09-04T12:00:00Z",
        })
        with self.assertRaises(Blocked) as ctx:
            reduce([result])
        self.assertIn("attempt", ctx.exception.detail)

    def test_missing_attempt_is_blocked_even_after_a_genuine_request(self):
        # Root's exact reproduction: a genuine request for task-b, then a
        # result reporting on it with no attempt at all. Must be rejected
        # here regardless of any 'request' that came before it -- a
        # result's own attempt field is never inferred from context.
        request = Envelope.from_dict({
            "schema_version": 2,
            "previous_hash": GENESIS_HASH,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "orchestrator",
            "recipient": "agent:worker-1",
            "kind": "request",
            "payload": {"task_id": "task-b", "attempt": 1},
            "created_at": "2026-09-04T12:00:00Z",
        })
        result = Envelope.from_dict({
            "schema_version": 2,
            "previous_hash": GENESIS_HASH,
            "envelope_id": "env-2",
            "run_id": "run-1",
            "sender": "agent:worker-1",
            "recipient": "orchestrator",
            "kind": "result",
            "payload": {"task_id": "task-b", "outcome": "passed"},
            "created_at": "2026-09-04T12:00:01Z",
        })
        with self.assertRaises(Blocked) as ctx:
            reduce([request, result])
        self.assertIn("attempt", ctx.exception.detail)

    def test_a_result_with_only_attempt_and_no_outcome_does_not_require_it(self):
        # attempt is mandatory on a *task-resolving* result specifically
        # (task_id and outcome both present) -- a result payload missing
        # outcome never reaches the task_status/attempt-mandatory branch
        # at all, exactly like a 'request' payload with no task_id is
        # simply not a task-dispatching request and carries no
        # requirement either. This does not weaken the guarantee: such a
        # 'result' resolves nothing (task_status is left untouched).
        result = Envelope.from_dict({
            "schema_version": 2,
            "previous_hash": GENESIS_HASH,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "agent:worker-1",
            "recipient": "orchestrator",
            "kind": "result",
            "payload": {"task_id": "task-1"},
            "created_at": "2026-09-04T12:00:00Z",
        })
        state = reduce([result])
        self.assertEqual(status_of(state, "task-1"), "pending")

    def test_a_request_in_flight_with_no_result_yet_still_reduces_cleanly(self):
        # Guard against over-rejection: mandatory attempt applies to
        # 'result' envelopes, not to a task that simply has no result
        # envelope at all yet. A lone in-flight request must still reduce
        # to 'running' without raising.
        request = Envelope.from_dict({
            "schema_version": 2,
            "previous_hash": GENESIS_HASH,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "orchestrator",
            "recipient": "agent:worker-1",
            "kind": "request",
            "payload": {"task_id": "task-1", "attempt": 1},
            "created_at": "2026-09-04T12:00:00Z",
        })
        state = reduce([request])
        self.assertEqual(status_of(state, "task-1"), "running")


class DuplicateAttemptRejectionTest(unittest.TestCase):
    # Outcome 2 Task 4 quality-review FIX 4(b) -- the guarantee that
    # matters most: root reproduced spawning twice for the identical
    # (task_id="task-a", attempt=1), which used to be silently accepted,
    # leaving `reduce` unable to tell a genuine retry from a duplicate
    # spawn (counting envelopes gave 2, counting distinct attempts gave
    # 1). This is the one broken-and-restored for the implementer report.

    def test_second_request_with_the_same_attempt_is_blocked(self):
        first = _request_with_attempt("task-a", 1, envelope_id="env-1")
        duplicate = _request_with_attempt("task-a", 1, envelope_id="env-2")
        with self.assertRaises(Blocked) as ctx:
            reduce([first, duplicate])
        self.assertIn("task-a", ctx.exception.detail)
        self.assertIn("attempt", ctx.exception.detail.lower())

    def test_out_of_order_attempt_is_blocked(self):
        # attempt=1 then attempt=3, skipping 2 -- also not "the next
        # expected attempt", so also rejected.
        first = _request_with_attempt("task-a", 1, envelope_id="env-1")
        skipped = _request_with_attempt("task-a", 3, envelope_id="env-2")
        with self.assertRaises(Blocked):
            reduce([first, skipped])

    def test_sequential_retries_for_the_same_task_are_accepted(self):
        sequence = [
            _request_with_attempt("task-a", 1, envelope_id="env-1"),
            _result_with_attempt("task-a", 1, "failed", envelope_id="env-2"),
            _request_with_attempt("task-a", 2, envelope_id="env-3"),
            _result_with_attempt("task-a", 2, "passed", envelope_id="env-4"),
        ]
        state = reduce(sequence)
        self.assertEqual(attempts_of(state, "task-a"), 2)
        self.assertEqual(status_of(state, "task-a"), "passed")

    def test_sequential_attempts_across_two_tasks_do_not_interfere(self):
        sequence = [
            _request_with_attempt("task-a", 1, envelope_id="env-1"),
            _request_with_attempt("task-b", 1, envelope_id="env-2"),
        ]
        state = reduce(sequence)
        self.assertEqual(attempts_of(state, "task-a"), 1)
        self.assertEqual(attempts_of(state, "task-b"), 1)


class AttemptsMappingDerivationTest(unittest.TestCase):
    # FIX 4(c): a first-class, exact attempts-per-task view.

    def test_attempts_mapping_counts_valid_request_envelopes_per_task(self):
        sequence = [
            _request_with_attempt("task-a", 1, envelope_id="env-1"),
            _request_with_attempt("task-a", 2, envelope_id="env-2"),
            _request_with_attempt("task-a", 3, envelope_id="env-3"),
        ]
        state = reduce(sequence)
        self.assertEqual(attempts_of(state, "task-a"), 3)

    def test_attempts_mapping_only_contains_mentioned_tasks(self):
        state = reduce([_request_with_attempt("task-a", 1, envelope_id="env-1")])
        self.assertIn("task-a", state.attempts)
        self.assertNotIn("task-b", state.attempts)

    def test_attempts_of_returns_zero_for_unmentioned_task(self):
        state = reduce([])
        self.assertEqual(attempts_of(state, "never-requested"), 0)

    def test_attempts_mapping_unaffected_by_a_results_own_attempt_field(self):
        # A result's attempt is validated (ResultAttemptValidationTest) but
        # must not itself bump the count -- only a 'request' claims a new
        # attempt; a 'result' merely reports on one already claimed.
        sequence = [
            _request_with_attempt("task-a", 1, envelope_id="env-1"),
            _result_with_attempt("task-a", 1, "failed", envelope_id="env-2"),
        ]
        state = reduce(sequence)
        self.assertEqual(attempts_of(state, "task-a"), 1)


class AttemptsImmutabilityTest(unittest.TestCase):
    def test_attempts_mapping_item_assignment_raises_via_reduce(self):
        state = reduce([_request_with_attempt("task-a", 1, envelope_id="env-1")])
        with self.assertRaises(TypeError):
            state.attempts["task-a"] = 99


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

if __name__ == "__main__":
    unittest.main()
