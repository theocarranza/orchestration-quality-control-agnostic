"""fake_adapter.py — a scripted, model-free implementation of AdapterPort.

This is the Outcome 3 extension of the Outcome 2 Task 4 slice of
AI_Codex/Architecture/ADR/0014-generated-workflow-deterministic-kernel.md.
Outcome 2 established the adapter boundary and deterministic fake; this
extension adds the root-answer relay while retaining that origin context.
`FakeAdapter` implements the five-operation `adapter_port.AdapterPort`
entirely from a `script` mapping (task_id, attempt) -> a result mapping,
so a whole run can be driven end to end with no network call, no LLM
call, no sleep, and no clock read anywhere in the path. It appends
envelopes to the `mailbox` it is given; it never constructs, reads, or
mutates a `run_state.RunState` itself -- that derivation is strictly the
caller's job via `run_state.reduce`.

Every id and timestamp this adapter emits comes from an internal,
strictly-increasing counter, never from the wall clock or any other
real-world source of variation. Two fresh `FakeAdapter` instances driven
through the same call sequence from the same starting point therefore
produce byte-identical envelopes -- this is what makes a replay of the
same script reproducible (see tests/test_replay.py's determinism
fixture).

Resuming a persisted run (Outcome 2 Task 4 quality-review fix). A fresh
`FakeAdapter()` used to always seed its counter at zero, so id generation
was only collision-free for a mailbox that adapter itself had written
end to end. Reload a mailbox from `mailbox.Mailbox.from_jsonl` and hand
it to a brand-new `FakeAdapter` and the old behaviour would restart the
counter at zero and immediately regenerate `env-1`, `env-2`, ... --
colliding with ids the reloaded log already holds (now caught loudly by
`Mailbox.append`'s duplicate check, but still the wrong outcome). Passing
that mailbox in via the `mailbox=` constructor keyword seeds the counter
from its highest existing `env-<N>` id instead, so a resumed run
continues the sequence rather than restarting it.

Outcome 3 Task 1: this module names no `schema_version` and no
`previous_hash` anywhere below -- not because those values happen to be
easy to get right here, but because `adapter_port.AdapterPort._append`'s
signature has no parameter for either. Every envelope this adapter
produces goes through `_append` with only content (ids, pairing, kind,
payload, timestamp); `_append` alone constructs and chains it. This
module is exactly the shape a real host adapter (Task 4) should copy.
"""

import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

from adapter_port import AdapterPort
from qc_lib import Blocked, require_enum
from run_state import PHASES
from gate import AnswerDecision, RetryDecision, AWAITING_USER_INPUT, approve_answer

STAGE = "fake_adapter"

_SYNTHETIC_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)
_ENV_ID_PATTERN = re.compile(r"^env-(\d+)$")


def _high_water_mark(mailbox):
    """Return the highest numeric suffix already used among `mailbox`'s
    envelope ids that match this adapter's own 'env-N' scheme.

    Ids from a different scheme (e.g. a real host adapter's own id
    format) are simply ignored for this purpose -- this heuristic only
    needs to agree with itself: it is here so a *fake* adapter resuming a
    mailbox another *fake* adapter wrote does not collide with it.
    """
    highest = 0
    for envelope in mailbox.read_all():
        match = _ENV_ID_PATTERN.fullmatch(envelope.envelope_id)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest


class FakeAdapter(AdapterPort):
    """Deterministic stand-in for a real host adapter.

    `script` maps `(task_id, attempt)` to a result mapping with at least
    `'outcome'` (`'passed'` or `'failed'`) and, when `'failed'`, a
    `'critique'` string. `spawn()` appends the 'request' envelope and --
    because a fake adapter's whole purpose is to never wait on a real
    worker -- immediately looks up and appends the matching 'result'
    envelope from `script`, so a caller never polls or sleeps between the
    two.

    `mailbox`, if given, seeds the id/timestamp counter from that
    mailbox's existing high-water mark (see `_high_water_mark` above)
    instead of starting at zero -- pass the mailbox a resumed run is
    continuing so this adapter's ids do not collide with ones already in
    it. Omit it (the default) for a fresh mailbox, where the high-water
    mark is zero anyway.
    """

    def __init__(self, script, *, mailbox=None):
        self._script = dict(script)
        self._counter = _high_water_mark(mailbox) if mailbox is not None else 0

    def _next_meta(self, prefix):
        """Return (id, created_at) from the internal counter, never the wall clock."""
        self._counter += 1
        envelope_id = f"{prefix}-{self._counter}"
        created_at = (_SYNTHETIC_EPOCH + timedelta(seconds=self._counter)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        return envelope_id, created_at

    def spawn(self, mailbox, *, run_id, task_id, attempt, agent_id, brief):
        script_key = (task_id, attempt)
        if script_key not in self._script:
            raise Blocked(
                stage=STAGE,
                reason_code="missing_target",
                detail=(
                    f"no scripted result for task_id={task_id!r} attempt={attempt!r}; "
                    "the fake adapter has nothing to reply with"
                ),
                recovery_action="add an entry for this (task_id, attempt) pair to the script",
            )
        scripted = self._script[script_key]
        outcome = scripted.get("outcome")
        require_enum(outcome, ("passed", "failed"), "script outcome", stage=STAGE)
        result_payload = {"task_id": task_id, "attempt": attempt, "outcome": outcome}
        if outcome == "failed":
            result_payload["critique"] = scripted.get("critique")
        for key in ("artifact", "question"):
            if key in scripted:
                result_payload[key] = scripted[key]

        request_id, request_created_at = self._next_meta("env")
        request = self._append(
            mailbox,
            envelope_id=request_id,
            run_id=run_id,
            sender="orchestrator",
            recipient=f"agent:{agent_id}",
            kind="request",
            payload={"task_id": task_id, "attempt": attempt, "brief": brief},
            created_at=request_created_at,
        )

        result_id, result_created_at = self._next_meta("env")
        result = self._append(
            mailbox,
            envelope_id=result_id,
            run_id=run_id,
            sender=f"agent:{agent_id}",
            recipient="orchestrator",
            kind="result",
            payload=result_payload,
            created_at=result_created_at,
        )

        return (request, result)

    def emit_status(self, mailbox, *, run_id, phase, context=None):
        require_enum(phase, PHASES, "phase", stage=STAGE)
        payload = dict(context or {})
        payload["phase"] = phase
        envelope_id, created_at = self._next_meta("env")
        return self._append(
            mailbox,
            envelope_id=envelope_id,
            run_id=run_id,
            sender="orchestrator",
            recipient="root",
            kind="status",
            payload=payload,
            created_at=created_at,
        )

    def relay_question(self, mailbox, *, run_id, decision):
        from run_state import reduce
        if not isinstance(decision, RetryDecision) or decision.action != AWAITING_USER_INPUT or decision.phase != AWAITING_USER_INPUT:
            raise Blocked(
                stage=STAGE,
                reason_code="malformed_checkpoint",
                detail="decision must be an awaiting-user-input RetryDecision",
                recovery_action="pass the decision returned by gate.decide_failure",
            )
        q = decision.question
        if not isinstance(q, Mapping) or set(q) != {"question_id", "prompt"} or any(not isinstance(q[k], str) or not q[k].strip() for k in q):
            raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="question must contain question_id and prompt", recovery_action="pass a complete question")
        state = reduce(mailbox.read_all())
        context = state.context
        expected = {"task_id": decision.task_id, "attempt": decision.attempt, "critique": decision.critique, "attempts_remaining": decision.attempts_remaining, "question_id": q["question_id"], "prompt": q["prompt"]}
        expected_context = {**expected, "phase": AWAITING_USER_INPUT}
        if (run_id != state.run_id or state.phase != AWAITING_USER_INPUT
                or dict(context or {}) != expected_context):
            raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="decision does not match current waiting context", recovery_action="relay the current approved decision")
        previous_counter = self._counter
        envelope_id, created_at = self._next_meta("env")
        try:
            return self._append(
                mailbox,
                envelope_id=envelope_id,
                run_id=run_id,
                sender="orchestrator",
                recipient="root",
                kind="question",
                payload=expected,
                created_at=created_at,
            )
        except Blocked:
            self._counter = previous_counter
            raise

    def relay_answer(self, mailbox, *, answer):
        if not isinstance(answer, AnswerDecision):
            raise Blocked(stage=STAGE, reason_code="malformed_checkpoint",
                          detail="answer must be an approved AnswerDecision",
                          recovery_action="approve the raw answer through gate.approve_answer")
        from run_state import reduce
        state = reduce(mailbox.read_all())
        raw = {key: getattr(answer, key) for key in
               ("run_id", "task_id", "attempt", "question_id", "decision", "text")}
        expected = approve_answer(state, raw)
        if expected != answer:
            raise Blocked(stage=STAGE, reason_code="malformed_checkpoint",
                          detail="answer decision does not match current state",
                          recovery_action="approve a current answer decision")
        previous_counter = self._counter
        envelope_id, created_at = self._next_meta("env")
        try:
            return self._append(mailbox, envelope_id=envelope_id, run_id=answer.run_id,
                                sender="root", recipient="orchestrator", kind="answer",
                                payload=raw, created_at=created_at)
        except Blocked:
            # A rejected append must be observationally indistinguishable
            # from a call that never consumed an id.
            self._counter = previous_counter
            raise

    def enforce_policy(self, *, run_id, hook_name, context=None):
        # The fake adapter enforces no host-specific policy of its own: it
        # always allows, and discloses nothing beyond that. A real host
        # adapter is the only place this method inspects hook_name/context
        # and might raise Blocked.
        return {}
