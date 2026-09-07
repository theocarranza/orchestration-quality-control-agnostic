import inspect
import unittest

from adapter_port import AdapterPort
from kernel_specs import ENVELOPE_SCHEMA_VERSION, Envelope, GENESIS_HASH
from mailbox import Mailbox
from qc_lib import Blocked

ABSTRACT_METHODS = frozenset({"spawn", "emit_status", "relay_question", "relay_answer", "enforce_policy"})


def _envelope_kwargs(**overrides):
    """The content _append actually accepts: no schema_version, no
    previous_hash -- those two are constructed and owned by _append
    itself (see adapter_port.py's module and _append docstrings), so a
    caller here has no field to even attempt supplying either through.
    """
    data = {
        "envelope_id": "env-0001",
        "run_id": "run-0001",
        "sender": "orchestrator",
        "recipient": "agent:worker-1",
        "kind": "request",
        "payload": {"task_id": "task-1", "attempt": 1, "brief": {}},
        "created_at": "2026-09-04T12:00:00Z",
    }
    data.update(overrides)
    return data


class _MinimalConcreteAdapter(AdapterPort):
    """The smallest possible subclass -- exists only to exercise the base
    class's contract (instantiability, the shared `_append` helper) in
    isolation from FakeAdapter's scripted behaviour.
    """

    def spawn(self, mailbox, *, run_id, task_id, attempt, agent_id, brief):
        raise NotImplementedError

    def emit_status(self, mailbox, *, run_id, phase, context=None):
        raise NotImplementedError

    def relay_question(self, mailbox, *, run_id, question):
        raise NotImplementedError

    def relay_answer(self, mailbox, *, answer):
        raise NotImplementedError

    def enforce_policy(self, *, run_id, hook_name, context=None):
        raise NotImplementedError


class AdapterPortIsAbstractTest(unittest.TestCase):
    def test_adapter_port_cannot_be_instantiated_directly(self):
        with self.assertRaises(TypeError):
            AdapterPort()

    def test_exactly_five_abstract_methods(self):
        # Five operations, per the master plan's Outcome 3 line -- a table
        # test so an operation quietly added later
        # is caught here rather than discovered by review.
        self.assertEqual(AdapterPort.__abstractmethods__, ABSTRACT_METHODS)

    def test_a_subclass_implementing_all_five_methods_is_instantiable(self):
        adapter = _MinimalConcreteAdapter()
        self.assertIsInstance(adapter, AdapterPort)

    def test_a_subclass_missing_one_method_is_not_instantiable(self):
        # Removing any one of the five must keep the class abstract; this
        # is the mirror image of test_exactly_five_abstract_methods,
        # proving the ABC actually enforces the contract rather than just
        # naming it.
        class _MissingEnforcePolicy(AdapterPort):
            def spawn(self, mailbox, *, run_id, task_id, attempt, agent_id, brief):
                raise NotImplementedError

            def emit_status(self, mailbox, *, run_id, phase, context=None):
                raise NotImplementedError

            def relay_question(self, mailbox, *, run_id, question):
                raise NotImplementedError

        with self.assertRaises(TypeError):
            _MissingEnforcePolicy()

        class _MissingRelayAnswer(AdapterPort):
            def spawn(self, mailbox, *, run_id, task_id, attempt, agent_id, brief):
                raise NotImplementedError
            def emit_status(self, mailbox, *, run_id, phase, context=None):
                raise NotImplementedError
            def relay_question(self, mailbox, *, run_id, question):
                raise NotImplementedError
            def enforce_policy(self, *, run_id, hook_name, context=None):
                raise NotImplementedError

        with self.assertRaises(TypeError):
            _MissingRelayAnswer()

    def test_relay_answer_has_only_mailbox_and_keyword_answer(self):
        params = inspect.signature(AdapterPort.relay_answer).parameters
        self.assertEqual(tuple(params), ("self", "mailbox", "answer"))
        self.assertTrue(params["answer"].kind is inspect.Parameter.KEYWORD_ONLY)
        for forbidden in ("sender", "recipient", "run_id"):
            self.assertNotIn(forbidden, params)


class NoWorkerAddressingParameterTest(unittest.TestCase):
    # ADR 0014 decision 3: the port must not expose any way for one
    # worker to address another, or for root to address a worker
    # directly. Structurally, that means none of the three
    # envelope-producing methods accepts a caller-chosen sender or
    # recipient at all -- pairing is fixed by the method itself.

    def test_spawn_accepts_no_sender_or_recipient_parameter(self):
        params = inspect.signature(AdapterPort.spawn).parameters
        self.assertNotIn("sender", params)
        self.assertNotIn("recipient", params)

    def test_emit_status_accepts_no_sender_or_recipient_parameter(self):
        params = inspect.signature(AdapterPort.emit_status).parameters
        self.assertNotIn("sender", params)
        self.assertNotIn("recipient", params)

    def test_relay_question_accepts_no_sender_or_recipient_parameter(self):
        params = inspect.signature(AdapterPort.relay_question).parameters
        self.assertNotIn("sender", params)
        self.assertNotIn("recipient", params)


class AppendHelperEnforcesRoutingTest(unittest.TestCase):
    # _append is the one path every concrete method goes through to
    # produce an envelope at all; these tests exercise it directly via
    # the minimal subclass rather than indirectly through FakeAdapter, to
    # pin the guarantee to the base class itself.

    def test_append_of_a_legal_pair_lands_in_the_mailbox(self):
        adapter = _MinimalConcreteAdapter()
        mailbox = Mailbox()
        kwargs = _envelope_kwargs()
        returned = adapter._append(mailbox, **kwargs)
        self.assertIsInstance(returned, Envelope)
        self.assertEqual(mailbox.read_all(), (returned,))
        self.assertEqual(returned.envelope_id, kwargs["envelope_id"])
        self.assertEqual(returned.run_id, kwargs["run_id"])
        self.assertEqual(returned.sender, kwargs["sender"])
        self.assertEqual(returned.recipient, kwargs["recipient"])
        self.assertEqual(returned.kind, kwargs["kind"])
        self.assertEqual(returned.payload, kwargs["payload"])
        self.assertEqual(returned.created_at, kwargs["created_at"])

    def test_append_of_an_illegal_worker_to_worker_pair_is_blocked(self):
        adapter = _MinimalConcreteAdapter()
        mailbox = Mailbox()
        with self.assertRaises(Blocked) as ctx:
            adapter._append(mailbox, **_envelope_kwargs(
                sender="agent:worker-1", recipient="agent:worker-2", kind="request",
            ))
        self.assertIn("isolation", ctx.exception.detail.lower())

    def test_append_of_an_illegal_pair_does_not_partially_land_in_the_mailbox(self):
        adapter = _MinimalConcreteAdapter()
        mailbox = Mailbox()
        with self.assertRaises(Blocked):
            adapter._append(mailbox, **_envelope_kwargs(
                sender="root", recipient="agent:worker-1", kind="request",
            ))
        self.assertEqual(mailbox.read_all(), ())

    def test_append_of_root_addressing_a_worker_directly_is_blocked(self):
        adapter = _MinimalConcreteAdapter()
        mailbox = Mailbox()
        with self.assertRaises(Blocked) as ctx:
            adapter._append(mailbox, **_envelope_kwargs(
                sender="root", recipient="agent:worker-1", kind="request",
            ))
        self.assertIn("orchestrator", ctx.exception.detail.lower())


class AppendHelperOwnsSchemaVersionTest(unittest.TestCase):
    def test_append_stamps_the_current_envelope_schema_version(self):
        adapter = _MinimalConcreteAdapter()
        mailbox = Mailbox()
        returned = adapter._append(mailbox, **_envelope_kwargs())
        self.assertEqual(returned.schema_version, ENVELOPE_SCHEMA_VERSION)

    def test_append_has_no_schema_version_parameter(self):
        # Structural, not merely behavioural: a caller cannot even
        # attempt to name the contract version -- there is no parameter
        # slot for it, mirroring how spawn/emit_status/relay_question
        # have no sender/recipient parameter (NoWorkerAddressingParameterTest).
        params = inspect.signature(AdapterPort._append).parameters
        self.assertNotIn("schema_version", params)

    def test_passing_schema_version_to_append_raises_type_error(self):
        adapter = _MinimalConcreteAdapter()
        mailbox = Mailbox()
        with self.assertRaises(TypeError):
            adapter._append(mailbox, schema_version=1, **_envelope_kwargs())


class AppendHelperChainsPreviousHashTest(unittest.TestCase):
    # Outcome 3 Task 1: _append is the single choke point where
    # previous_hash is computed and set (see adapter_port.py's module and
    # _append docstrings).

    def test_the_first_envelope_into_an_empty_mailbox_gets_genesis_hash(self):
        adapter = _MinimalConcreteAdapter()
        mailbox = Mailbox()
        returned = adapter._append(mailbox, **_envelope_kwargs())
        self.assertEqual(returned.previous_hash, GENESIS_HASH)

    def test_the_second_envelope_gets_the_hash_of_the_first(self):
        adapter = _MinimalConcreteAdapter()
        mailbox = Mailbox()
        first = adapter._append(mailbox, **_envelope_kwargs(envelope_id="env-0001"))
        second = adapter._append(mailbox, **_envelope_kwargs(
            envelope_id="env-0002", sender="agent:worker-1",
            recipient="orchestrator", kind="result",
            payload={"task_id": "task-1", "attempt": 1, "outcome": "passed"},
        ))
        self.assertEqual(second.previous_hash, first.hash())
        self.assertNotEqual(second.previous_hash, GENESIS_HASH)

    def test_a_third_envelope_chains_to_the_second_not_the_first(self):
        # Guards against an off-by-one that always chains to history[0]
        # (or to whatever was appended first) instead of the actual
        # immediately-preceding entry.
        adapter = _MinimalConcreteAdapter()
        mailbox = Mailbox()
        first = adapter._append(mailbox, **_envelope_kwargs(envelope_id="env-0001"))
        second = adapter._append(mailbox, **_envelope_kwargs(
            envelope_id="env-0002", sender="agent:worker-1",
            recipient="orchestrator", kind="result",
            payload={"task_id": "task-1", "attempt": 1, "outcome": "passed"},
        ))
        third = adapter._append(mailbox, **_envelope_kwargs(
            envelope_id="env-0003", sender="orchestrator", recipient="root",
            kind="status", payload={"phase": "completed"},
        ))
        self.assertEqual(third.previous_hash, second.hash())
        self.assertNotEqual(third.previous_hash, first.hash())

    def test_appended_envelope_is_reachable_through_the_mailbox_with_its_computed_hash(self):
        adapter = _MinimalConcreteAdapter()
        mailbox = Mailbox()
        adapter._append(mailbox, **_envelope_kwargs())
        stored = mailbox.read_all()[0]
        self.assertEqual(stored.previous_hash, GENESIS_HASH)

    def test_previous_hash_is_read_fresh_from_the_mailbox_on_every_call(self):
        # Not cached on the adapter instance -- two independent
        # _MinimalConcreteAdapter instances appending into the SAME
        # mailbox must still chain correctly against each other, since a
        # real orchestrator loop may hand different mailbox snapshots to
        # different adapter calls but the mailbox itself is the one
        # shared source of truth.
        mailbox = Mailbox()
        first_adapter = _MinimalConcreteAdapter()
        second_adapter = _MinimalConcreteAdapter()
        first = first_adapter._append(mailbox, **_envelope_kwargs(envelope_id="env-0001"))
        second = second_adapter._append(mailbox, **_envelope_kwargs(
            envelope_id="env-0002", sender="agent:worker-1",
            recipient="orchestrator", kind="result",
            payload={"task_id": "task-1", "attempt": 1, "outcome": "passed"},
        ))
        self.assertEqual(second.previous_hash, first.hash())


class AppendHelperMakesPreviousHashUnconstructableTest(unittest.TestCase):
    # Outcome 3 Task 1, round 2: root's explicit requirement -- an adapter
    # must not be able to set previous_hash at all, not merely have it
    # silently overridden. _append's signature has no parameter for it, so
    # this is a structural (TypeError) guarantee, not merely a behavioural
    # one.

    def test_append_has_no_previous_hash_parameter(self):
        params = inspect.signature(AdapterPort._append).parameters
        self.assertNotIn("previous_hash", params)

    def test_passing_previous_hash_to_append_raises_type_error(self):
        adapter = _MinimalConcreteAdapter()
        mailbox = Mailbox()
        with self.assertRaises(TypeError):
            adapter._append(mailbox, previous_hash="a" * 64, **_envelope_kwargs())

    def test_append_only_accepts_content_fields(self):
        # Enumerate the full parameter set: exactly the content _append
        # needs to build one envelope, nothing more -- a future edit that
        # widens this back out to accept a whole pre-built Envelope (or
        # re-adds previous_hash/schema_version) is caught here.
        params = set(inspect.signature(AdapterPort._append).parameters) - {"self", "mailbox"}
        self.assertEqual(
            params,
            {"envelope_id", "run_id", "sender", "recipient", "kind", "payload", "created_at"},
        )


if __name__ == "__main__":
    unittest.main()
