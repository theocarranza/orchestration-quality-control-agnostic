"""gate.py — the result gate and the bounded retry/block decision.

This is the Outcome 2 Task 4 slice of
AI_Codex/Architecture/ADR/0014-generated-workflow-deterministic-kernel.md,
decision 4: "A failed gate carries its critique into the next attempt; an
exhausted attempt budget moves the run to a blocked or
awaiting-user-input state that only the engine can set and only root can
answer." `gate_result` is the classifier; `retry_or_block` is the engine
code that makes the retry-or-stop call. Neither function touches a
mailbox or mutates a RunState -- they classify and decide, and the caller
(an orchestrator loop, here the test loop in tests/test_replay.py) is the
one that turns a decision into the next envelope via the adapter port.

Never a silent stall: retry_or_block has exactly two outcomes, RETRY or a
named terminal phase. There is no third path that returns without
deciding either.
"""

from dataclasses import dataclass

from qc_lib import Blocked
from run_state import PHASES, status_of

STAGE = "gate"

PASSED = "passed"
FAILED = "failed"
GATE_OUTCOMES = (PASSED, FAILED)

RETRY = "retry"
BLOCKED_STATE = "blocked"
# Reserved, not yet produced: retry_or_block below never returns this
# today. It names the phase a future question-triggered transition would
# use (an engine that recognises a failure as "needs a decision only root
# can make" rather than "just stop"), which does not exist in this kernel
# slice. Its absence here is a scope decision (see the master plan's
# Outcome 2 line and ADR 0014 decision 4), not a bug -- do not treat a
# retry_or_block call that never yields AWAITING_USER_INPUT as a defect.
AWAITING_USER_INPUT = "awaiting-user-input"
RETRY_DECISIONS = (RETRY, BLOCKED_STATE, AWAITING_USER_INPUT)

# The two terminal decision names must be exactly the run_state phases an
# engine is allowed to write for a stalled run (ADR 0014 decision 4). If
# either constant above ever drifted from run_state.PHASES, a caller could
# build a status envelope that run_state.reduce would then reject as an
# unknown phase. Checked once at import time, mirroring run_state's own
# VALID_OUTCOMES-subset-of-TASK_STATUSES assertion.
assert BLOCKED_STATE in PHASES and AWAITING_USER_INPUT in PHASES, (
    "gate.py's terminal decision names must match run_state.PHASES"
)


@dataclass(frozen=True)
class GateVerdict:
    """The result gate's classification of one worker attempt.

    `critique` is None exactly when outcome == PASSED, and a non-empty
    string exactly when outcome == FAILED -- gate_result enforces that
    pairing on construction, so a caller can carry `critique` forward
    without a None-or-empty special case for the failed branch.
    """

    task_id: str
    attempt: object
    outcome: str
    critique: object


def gate_result(result):
    """Classify a worker result as passed or failed.

    `result` is a plain mapping with at least 'task_id' and 'outcome' (one
    of GATE_OUTCOMES). When outcome == FAILED it must also carry a
    non-empty 'critique' string explaining why: a failure without an
    explanation is exactly the silent-stall shape ADR 0014 decision 4
    exists to rule out, so this raises Blocked rather than let it through
    unexplained. 'attempt', if present, must be a non-negative integer
    (checked presence-gated, the same way 'task_id' and 'critique' already
    are: this kernel slice does not require every result to carry one, but
    a result that does must carry a valid one) and is then passed through
    unchanged on the returned GateVerdict for the caller's own
    bookkeeping; it plays no further role in classification here.
    """
    if not hasattr(result, "get"):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"gate_result requires a mapping, got {type(result).__name__}",
            recovery_action="pass a mapping with 'task_id', 'outcome', and (if failed) 'critique'",
        )

    task_id = result.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"result['task_id'] must be a non-empty string, got {task_id!r}",
            recovery_action="set result['task_id'] to a non-empty string",
        )

    outcome = result.get("outcome")
    if outcome not in GATE_OUTCOMES:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"result['outcome'] must be one of {GATE_OUTCOMES}, got {outcome!r}",
            recovery_action=f"set result['outcome'] to one of {GATE_OUTCOMES}",
        )

    if "attempt" in result:
        attempt = result.get("attempt")
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 0:
            raise Blocked(
                stage=STAGE,
                reason_code="malformed_checkpoint",
                detail=f"result['attempt'] must be a non-negative integer, got {attempt!r}",
                recovery_action="set result['attempt'] to a non-negative integer",
            )

    critique = result.get("critique")
    if outcome == FAILED:
        # Presence, not truthiness: an empty-string or whitespace-only
        # critique is not an explanation either, and must be rejected the
        # same way a missing one is (see run_state's own truthiness-guard
        # regression for why "if critique:" is the wrong check here).
        if not isinstance(critique, str) or not critique.strip():
            raise Blocked(
                stage=STAGE,
                reason_code="malformed_checkpoint",
                detail="a failed result must carry a non-empty 'critique' explaining why",
                recovery_action="set result['critique'] to a non-empty string explaining the failure",
            )
    else:
        critique = None

    return GateVerdict(
        task_id=task_id,
        attempt=result.get("attempt"),
        outcome=outcome,
        critique=critique,
    )


@dataclass(frozen=True)
class RetryDecision:
    """What the engine does next after a FAILED gate verdict.

    `action` is one of RETRY_DECISIONS. When action == RETRY, `critique`
    is the text the caller must carry into the next attempt's compiled
    brief and `phase` is None (there is no phase transition to record).
    When action is terminal (BLOCKED_STATE or AWAITING_USER_INPUT),
    `phase` holds exactly that string, ready to write into a status
    envelope's payload['phase'], and `critique` holds the final failing
    critique for context.
    """

    action: str
    task_id: str
    critique: object
    phase: object


def retry_or_block(state, task_id, critique, attempts_remaining):
    """Decide whether to retry `task_id` carrying `critique` forward, or stop.

    `state` must be the RunState derived (via run_state.reduce) from the
    mailbox as of the failure being decided on. This cross-checks
    `status_of(state, task_id) == FAILED` before deciding anything, so a
    caller cannot obtain a retry decision for a task the mailbox-derived
    state does not actually show as failed -- the mailbox stays the
    source of truth even for this decision. `critique` must be the
    non-empty string a prior `gate_result` call produced for this
    failure.

    `attempts_remaining` is exactly:

        attempts_remaining = max_attempts - attempts_made_so_far

    where `attempts_made_so_far` INCLUDES the attempt that just failed and
    produced `critique`. Worked example with max_attempts=3: pass 2 right
    after attempt 1 fails (3 - 1 = 2 left), pass 1 after attempt 2 fails
    (3 - 2 = 1 left), pass 0 after attempt 3 fails (3 - 3 = 0 left, the
    budget is exhausted). The name deliberately reads as "what is left",
    not "what has been spent" -- passing attempts-made instead of
    attempts-remaining inverts this function's semantics: the value stays
    positive and keeps growing as attempts accumulate instead of counting
    down to zero, so the `attempts_remaining > 0` check below never turns
    false and this function retries forever instead of ever stopping.

    When `attempts_remaining > 0`, this returns a RETRY decision carrying
    `critique` forward unchanged. When `attempts_remaining == 0` (the
    budget is exhausted), this returns a terminal decision with
    action == phase == BLOCKED_STATE -- per ADR 0014 decision 4, only this
    engine code may choose that state, and only root may answer it. This
    function never returns AWAITING_USER_INPUT: that phase is reserved for
    a question-triggered transition this kernel slice does not build (see
    the note beside its constant above); every exhaustion here names
    BLOCKED_STATE specifically. There is no third outcome: every call
    either retries or names a terminal phase. A negative
    `attempts_remaining` is rejected as malformed rather than silently
    treated as exhausted, since it can only mean a caller's attempt
    bookkeeping is wrong.
    """
    current_status = status_of(state, task_id)
    if current_status != FAILED:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=(
                f"retry_or_block called for task '{task_id}' but the mailbox-derived "
                f"state shows status '{current_status}', not '{FAILED}'"
            ),
            recovery_action="only call retry_or_block after a gate_result FAILED verdict for this task",
        )

    if not isinstance(critique, str) or not critique.strip():
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"critique must be a non-empty string, got {critique!r}",
            recovery_action="pass the non-empty critique gate_result produced for this failure",
        )

    if (
        not isinstance(attempts_remaining, int)
        or isinstance(attempts_remaining, bool)
        or attempts_remaining < 0
    ):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=(
                f"attempts_remaining must be a non-negative integer, got "
                f"{attempts_remaining!r}"
            ),
            recovery_action=(
                "pass attempts_remaining = max_attempts - attempts_made_so_far "
                "(attempts_made_so_far includes the attempt that just failed); "
                "0 or more"
            ),
        )

    if attempts_remaining > 0:
        return RetryDecision(action=RETRY, task_id=task_id, critique=critique, phase=None)

    return RetryDecision(
        action=BLOCKED_STATE,
        task_id=task_id,
        critique=critique,
        phase=BLOCKED_STATE,
    )
