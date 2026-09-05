import inspect
import unittest

from adapter_port import AdapterPort
from kernel_specs import Envelope
from mailbox import Mailbox
from qc_lib import Blocked

ABSTRACT_METHODS = frozenset({"spawn", "emit_status", "relay_question", "enforce_policy"})


def _envelope(**overrides):
    data = {
        "schema_version": 1,
        "envelope_id": "env-0001",
        "run_id": "run-0001",
        "sender": "orchestrator",
        "recipient": "agent:worker-1",
        "kind": "request",
        "payload": {"task_id": "task-1", "attempt": 1, "brief": {}},
        "created_at": "2026-09-04T12:00:00Z",
    }
    data.update(overrides)
    return Envelope.from_dict(data)


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

    def enforce_policy(self, *, run_id, hook_name, context=None):
        raise NotImplementedError


class AdapterPortIsAbstractTest(unittest.TestCase):
    def test_adapter_port_cannot_be_instantiated_directly(self):
        with self.assertRaises(TypeError):
            AdapterPort()

    def test_exactly_four_abstract_methods(self):
        # Four operations only, per ADR 0014 and the master plan's Outcome
        # 2 line -- a table test so a fifth operation quietly added later
        # is caught here rather than discovered by review.
        self.assertEqual(AdapterPort.__abstractmethods__, ABSTRACT_METHODS)

    def test_a_subclass_implementing_all_four_methods_is_instantiable(self):
        adapter = _MinimalConcreteAdapter()
        self.assertIsInstance(adapter, AdapterPort)

    def test_a_subclass_missing_one_method_is_not_instantiable(self):
        # Removing any one of the four must keep the class abstract; this
        # is the mirror image of test_exactly_four_abstract_methods,
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
    # _append is the one path every concrete method goes through; these
    # tests exercise it directly via the minimal subclass rather than
    # indirectly through FakeAdapter, to pin the guarantee to the base
    # class itself.

    def test_append_of_a_legal_pair_lands_in_the_mailbox(self):
        adapter = _MinimalConcreteAdapter()
        mailbox = Mailbox()
        envelope = _envelope()
        returned = adapter._append(mailbox, envelope)
        self.assertIs(returned, envelope)
        self.assertEqual(mailbox.read_all(), (envelope,))

    def test_append_of_an_illegal_worker_to_worker_pair_is_blocked(self):
        adapter = _MinimalConcreteAdapter()
        mailbox = Mailbox()
        illegal = _envelope(
            sender="agent:worker-1", recipient="agent:worker-2", kind="request",
        )
        with self.assertRaises(Blocked) as ctx:
            adapter._append(mailbox, illegal)
        self.assertIn("isolation", ctx.exception.detail.lower())

    def test_append_of_an_illegal_pair_does_not_partially_land_in_the_mailbox(self):
        adapter = _MinimalConcreteAdapter()
        mailbox = Mailbox()
        illegal = _envelope(sender="root", recipient="agent:worker-1", kind="request")
        with self.assertRaises(Blocked):
            adapter._append(mailbox, illegal)
        self.assertEqual(mailbox.read_all(), ())

    def test_append_of_root_addressing_a_worker_directly_is_blocked(self):
        adapter = _MinimalConcreteAdapter()
        mailbox = Mailbox()
        illegal = _envelope(sender="root", recipient="agent:worker-1", kind="request")
        with self.assertRaises(Blocked) as ctx:
            adapter._append(mailbox, illegal)
        self.assertIn("orchestrator", ctx.exception.detail.lower())


if __name__ == "__main__":
    unittest.main()
