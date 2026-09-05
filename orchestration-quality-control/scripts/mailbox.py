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
    guarantee must hold on both, not only on the one this module happens
    to use internally.
    """

    def __init__(self, envelopes=()):
        self._events = [_require_envelope(envelope) for envelope in envelopes]

    def append(self, envelope):
        """Append one envelope after the current end of the log."""
        self._events.append(_require_envelope(envelope))

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
