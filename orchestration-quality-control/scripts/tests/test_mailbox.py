import unittest
from types import MappingProxyType

from kernel_specs import Envelope
from qc_lib import Blocked

from mailbox import Mailbox


def _envelope(**overrides):
    data = {
        "schema_version": 1,
        "envelope_id": "env-0001",
        "run_id": "run-0001",
        "sender": "root",
        "recipient": "orchestrator",
        "kind": "request",
        "payload": {"note": "begin"},
        "created_at": "2026-09-04T12:00:00Z",
    }
    data.update(overrides)
    return Envelope.from_dict(data)


class MailboxAppendAndReadAllTest(unittest.TestCase):
    def test_empty_mailbox_reads_as_empty_tuple(self):
        mailbox = Mailbox()
        self.assertEqual(mailbox.read_all(), ())

    def test_append_adds_to_the_end_and_read_all_reflects_it(self):
        mailbox = Mailbox()
        first = _envelope(envelope_id="env-0001")
        second = _envelope(envelope_id="env-0002")
        mailbox.append(first)
        mailbox.append(second)
        self.assertEqual(mailbox.read_all(), (first, second))

    def test_appending_a_non_envelope_is_rejected(self):
        mailbox = Mailbox()
        with self.assertRaises(Blocked) as ctx:
            mailbox.append({"not": "an envelope"})
        self.assertIn("Envelope", ctx.exception.detail)


class MailboxEnvelopeIdUniquenessTest(unittest.TestCase):
    # Outcome 2 Task 4 quality-review FIX 3: the schema documents
    # envelope_id as unique within a run's mailbox, but nothing enforced
    # it. Root reproduced two FakeAdapter instances producing
    # ['env-1', 'env-2', 'env-1', 'env-2'] into one mailbox, silently
    # accepted. This is the one broken-and-restored for the implementer
    # report.

    def test_appending_a_duplicate_envelope_id_is_blocked(self):
        mailbox = Mailbox()
        mailbox.append(_envelope(envelope_id="env-1"))
        with self.assertRaises(Blocked) as ctx:
            mailbox.append(_envelope(envelope_id="env-1", kind="result", payload={"n": 2}))
        self.assertIn("env-1", ctx.exception.detail)

    def test_a_rejected_duplicate_does_not_land_in_the_mailbox(self):
        mailbox = Mailbox()
        mailbox.append(_envelope(envelope_id="env-1"))
        with self.assertRaises(Blocked):
            mailbox.append(_envelope(envelope_id="env-1"))
        self.assertEqual(len(mailbox.read_all()), 1)

    def test_constructor_also_rejects_a_duplicate_envelope_id(self):
        with self.assertRaises(Blocked) as ctx:
            Mailbox([_envelope(envelope_id="env-1"), _envelope(envelope_id="env-1")])
        self.assertIn("env-1", ctx.exception.detail)

    def test_from_jsonl_rejects_a_persisted_log_with_duplicate_ids(self):
        duplicated_text = (
            _envelope(envelope_id="env-1").to_json() + "\n"
            + _envelope(envelope_id="env-1", kind="result", payload={"n": 2}).to_json() + "\n"
        )
        with self.assertRaises(Blocked):
            Mailbox.from_jsonl(duplicated_text)

    def test_distinct_ids_are_unaffected(self):
        mailbox = Mailbox()
        mailbox.append(_envelope(envelope_id="env-1"))
        mailbox.append(_envelope(envelope_id="env-2"))
        self.assertEqual(len(mailbox.read_all()), 2)


class MailboxGenuinelyAppendOnlyTest(unittest.TestCase):
    # These tests are written to FAIL if the append-only guarantee is ever
    # weakened -- e.g. if append() were changed to allow replacing an
    # existing slot, or if read_all() ever exposed the live internal
    # storage instead of a snapshot. Verified during implementation by
    # temporarily breaking each guarantee and watching the corresponding
    # test go red (see the implementer report).

    def test_a_previously_taken_snapshot_is_unaffected_by_later_appends(self):
        mailbox = Mailbox()
        mailbox.append(_envelope(envelope_id="env-0001"))
        snapshot_before = mailbox.read_all()
        mailbox.append(_envelope(envelope_id="env-0002"))
        snapshot_after = mailbox.read_all()

        # The earlier snapshot must still show exactly what it showed when
        # it was taken -- appending later must not reach back and mutate it.
        self.assertEqual(snapshot_before, (_envelope(envelope_id="env-0001"),))
        self.assertEqual(len(snapshot_after), 2)
        self.assertEqual(snapshot_after[: len(snapshot_before)], snapshot_before)

    def test_order_of_appended_entries_is_preserved(self):
        mailbox = Mailbox()
        ids = ["env-0001", "env-0002", "env-0003", "env-0004"]
        for envelope_id in ids:
            mailbox.append(_envelope(envelope_id=envelope_id))
        self.assertEqual([e.envelope_id for e in mailbox.read_all()], ids)

    def test_read_all_result_cannot_be_mutated_to_alter_the_mailbox(self):
        mailbox = Mailbox()
        mailbox.append(_envelope(envelope_id="env-0001"))
        snapshot = mailbox.read_all()
        with self.assertRaises(TypeError):
            snapshot[0] = _envelope(envelope_id="tampered")
        # And even if item assignment on the returned tuple were somehow
        # possible, it must not be able to reach the mailbox's own storage.
        self.assertEqual(
            [e.envelope_id for e in mailbox.read_all()], ["env-0001"]
        )

    def test_no_public_api_permits_deletion_replacement_or_edit(self):
        # Enumerate the public surface and confirm it is exactly the
        # append/read/serialise shape this task specifies -- nothing named
        # like remove/delete/replace/edit/clear/pop/set could have been
        # added without this test noticing.
        public_names = {
            name for name in dir(Mailbox) if not name.startswith("_")
        }
        self.assertEqual(
            public_names, {"append", "read_all", "to_jsonl", "from_jsonl"}
        )
        forbidden_substrings = (
            "delete", "remove", "replace", "edit", "clear", "pop", "set",
            "update", "insert",
        )
        for name in public_names:
            for forbidden in forbidden_substrings:
                self.assertNotIn(forbidden, name.lower())

    def test_mailbox_has_no_dunder_item_mutation_hooks(self):
        # __setitem__/__delitem__ would let a caller rewrite or remove a
        # specific entry in place; a genuinely append-only log must not
        # define them.
        self.assertFalse(hasattr(Mailbox, "__setitem__"))
        self.assertFalse(hasattr(Mailbox, "__delitem__"))


class MailboxConstructionDoesNotAliasCallerState(unittest.TestCase):
    # Failure mode: a mailbox built via the direct constructor (not just via
    # append()) that stores the caller's list/iterable by reference would
    # let external code silently rewrite history it should no longer be
    # able to touch. This must hold for every construction path, not only
    # the one exercised by append().

    def test_constructor_copies_the_input_sequence(self):
        first = _envelope(envelope_id="env-0001")
        source = [first]
        mailbox = Mailbox(source)
        source.append(_envelope(envelope_id="env-0002"))
        source[0] = _envelope(envelope_id="tampered")

        self.assertEqual(mailbox.read_all(), (first,))

    def test_constructor_rejects_a_non_envelope_member(self):
        with self.assertRaises(Blocked):
            Mailbox([{"not": "an envelope"}])


class MailboxJsonlRoundTripTest(unittest.TestCase):
    def test_empty_mailbox_round_trips(self):
        mailbox = Mailbox()
        self.assertEqual(mailbox.to_jsonl(), "")
        restored = Mailbox.from_jsonl(mailbox.to_jsonl())
        self.assertEqual(restored.read_all(), ())

    def test_round_trip_is_byte_stable(self):
        mailbox = Mailbox()
        mailbox.append(_envelope(envelope_id="env-0001"))
        mailbox.append(_envelope(envelope_id="env-0002", kind="result", payload={"n": 2}))
        first_text = mailbox.to_jsonl()

        restored = Mailbox.from_jsonl(first_text)
        second_text = restored.to_jsonl()

        self.assertEqual(first_text, second_text)
        self.assertEqual(mailbox.read_all(), restored.read_all())

    def test_round_trip_is_byte_stable_for_non_ascii_payloads(self):
        note = "héllo wörld — 日本語 — emoji: 🎉"
        mailbox = Mailbox()
        mailbox.append(_envelope(payload={"note": note}))
        first_text = mailbox.to_jsonl()

        # Encode/decode as UTF-8 bytes explicitly: byte-stability must hold
        # at the byte level, not merely at the Python-string level.
        first_bytes = first_text.encode("utf-8")
        restored = Mailbox.from_jsonl(first_bytes.decode("utf-8"))
        second_text = restored.to_jsonl()
        second_bytes = second_text.encode("utf-8")

        self.assertEqual(first_bytes, second_bytes)
        self.assertEqual(restored.read_all()[0].payload["note"], note)

    def test_order_is_preserved_across_the_round_trip(self):
        mailbox = Mailbox()
        ids = ["env-0001", "env-0002", "env-0003"]
        for envelope_id in ids:
            mailbox.append(_envelope(envelope_id=envelope_id))
        restored = Mailbox.from_jsonl(mailbox.to_jsonl())
        self.assertEqual([e.envelope_id for e in restored.read_all()], ids)

    def test_malformed_jsonl_line_is_rejected_as_blocked(self):
        with self.assertRaises(Blocked):
            Mailbox.from_jsonl("{not valid json}\n")

    def test_key_order_in_source_payload_does_not_affect_wire_form(self):
        payload_a = {"a": 1, "b": 2}
        payload_b = {"b": 2, "a": 1}
        mailbox_a = Mailbox()
        mailbox_a.append(_envelope(payload=payload_a))
        mailbox_b = Mailbox()
        mailbox_b.append(_envelope(payload=payload_b))
        self.assertEqual(mailbox_a.to_jsonl(), mailbox_b.to_jsonl())


if __name__ == "__main__":
    unittest.main()
