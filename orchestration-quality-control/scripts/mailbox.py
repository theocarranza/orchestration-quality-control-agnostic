"""The append-only event mailbox: scripts/mailbox.py.

This is the Outcome 2 Task 2 slice of
AI_Codex/Architecture/ADR/0014-generated-workflow-deterministic-kernel.md,
decision 2: "Every hand-off is an envelope appended to a per-run mailbox."
A `Mailbox` holds the ordered `Envelope` history for one run. It exposes
exactly two operations on that history -- `append` and `read_all` -- plus
`to_jsonl`/`from_jsonl` for persisting and replaying it. There is no method
that deletes, replaces, or edits an entry already in the log: the public
surface below is deliberately the whole surface, and
tests/test_mailbox.py asserts that surface stays exactly this shape.

`run_state.reduce` (a sibling module) is what turns a mailbox's history
into a `RunState`; this module only ever hands out `Envelope` objects and
never derives or stores state of its own.

`envelope_id` uniqueness (Outcome 2 Task 4 quality-review fix). The
Envelope schema documents `envelope_id` as "unique identifier for this
envelope within its run's mailbox", but nothing enforced that until now.
The gap was concrete, not theoretical: two independently-seeded
`fake_adapter.FakeAdapter` instances writing into one mailbox could both
start counting from 1, producing ids like `env-1, env-2, env-1, env-2` --
silently accepted, and indistinguishable afterwards from four genuinely
distinct hand-offs. `append` (and the direct constructor, so both
construction paths agree) now raises `Blocked` naming the duplicate id
instead. The realistic trigger this guards against is resuming a
persisted run: reload a mailbox from `to_jsonl`/`from_jsonl`, construct a
fresh adapter for it, and without a fix on the *adapter* side its id
counter restarts at zero and collides with ids the reloaded log already
holds. See `fake_adapter.FakeAdapter.__init__`'s `mailbox=` parameter for
the paired fix that avoids ever producing the collision in the first
place; this module's job is to make a collision that does happen loud
instead of silent.
"""

import json

from kernel_specs import Envelope
from qc_lib import Blocked

STAGE = "mailbox"


def _require_envelope(value):
    if not isinstance(value, Envelope):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"mailbox entries must be Envelope instances, got {type(value).__name__}",
            recovery_action="construct an Envelope (e.g. via Envelope.from_dict) before appending",
        )
    return value


def _require_unique_envelope_id(envelope, existing_ids):
    """Raise Blocked naming the duplicate if envelope.envelope_id already
    appears among `existing_ids` -- shared by the constructor and `append` so
    both construction paths enforce the schema's uniqueness contract
    identically in O(1) time per append.
    """
    if envelope.envelope_id in existing_ids:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=(
                f"duplicate envelope_id {envelope.envelope_id!r}: already "
                "present in this run's mailbox"
            ),
            recovery_action=(
                "use a new envelope_id that has not already appeared in "
                "this run's mailbox"
            ),
        )
    return envelope


class Mailbox:
    """An append-only, per-run log of `Envelope` records.

    `append` adds one envelope after the current end of the log; it never
    rewrites, reorders, or removes an entry already present. `read_all`
    returns an immutable snapshot (a `tuple`) of the log as it stands at
    the moment of the call -- later appends cannot reach back and change a
    snapshot a caller is already holding, because the snapshot is a fresh
    tuple copy, not a view onto live storage.

    The constructor also copies its input rather than aliasing it, so a
    mailbox seeded from an existing list (e.g. during replay) is protected
    from later mutation of that list by its caller. This matters because
    `append` is not the only way to build a `Mailbox` -- the direct
    constructor is a second construction path, and the append-only
    guarantee -- and the envelope_id-uniqueness guarantee below -- must
    hold on both, not only on the one this module happens to use
    internally.
    """

    def __init__(self, envelopes=()):
        events = []
        seen_ids = set()
        for envelope in envelopes:
            envelope = _require_envelope(envelope)
            _require_unique_envelope_id(envelope, seen_ids)
            seen_ids.add(envelope.envelope_id)
            events.append(envelope)
        self._events = events
        self._seen_ids = seen_ids

    def append(self, envelope):
        """Append one envelope after the current end of the log.

        Rejects an envelope whose `envelope_id` already appears earlier in
        this mailbox: the schema documents that field as unique within a
        run's mailbox, and a silent duplicate is exactly what let two
        independently-counting adapters overwrite each other's identity
        (see the module docstring).
        """
        envelope = _require_envelope(envelope)
        _require_unique_envelope_id(envelope, self._seen_ids)
        self._seen_ids.add(envelope.envelope_id)
        self._events.append(envelope)

    def read_all(self):
        """Return the full history so far as an immutable tuple snapshot."""
        return tuple(self._events)

    def to_jsonl(self):
        """Serialise the history to JSON Lines: one canonical `Envelope.to_json()`
        per line, in log order. Deterministic for a given history, so a
        replay of `from_jsonl(to_jsonl())` produces byte-identical text.
        """
        if not self._events:
            return ""
        return "".join(envelope.to_json() + "\n" for envelope in self._events)

    @classmethod
    def from_jsonl(cls, text):
        """Parse JSON Lines produced by `to_jsonl` back into a `Mailbox`,
        preserving order. Blank lines are ignored so a trailing newline
        round-trips cleanly.
        """
        envelopes = []
        for line in text.split("\n"):
            if line.strip() == "":
                continue
            try:
                envelopes.append(Envelope.from_json(line))
            except json.JSONDecodeError as exc:
                raise Blocked(
                    stage=STAGE,
                    reason_code="malformed_checkpoint",
                    detail=f"invalid JSON on mailbox line: {exc}",
                    recovery_action="ensure every line is one canonical Envelope.to_json() line",
                ) from exc
        return cls(envelopes)
