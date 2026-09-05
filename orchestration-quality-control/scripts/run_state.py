"""Derived run state and the pure reducer: scripts/run_state.py.

This is the Outcome 2 Task 2 slice of
AI_Codex/Architecture/ADR/0014-generated-workflow-deterministic-kernel.md,
decision 2: run state "is a pure reduction over that history and is never
mutated directly." `RunState` is a value, not a store -- the only way to
produce a non-initial one is `reduce(envelopes, state)`, a plain left fold
with no I/O, no clock read, no randomness, and no module-level mutable
state. Reducing the same sequence twice yields an equal (though not
identical) `RunState`, and reducing a prefix then continuing with the rest
from the resulting state equals reducing the whole sequence at once --
both are direct consequences of `reduce` being nothing more than a fold.

Phase mechanism for this task's scope. The nine observable phases named by
the master plan and ADR 0014 (`discovery` through `awaiting-user-input`)
are macro lifecycle stages of the whole run, not a property of any single
envelope `kind` -- `discovery`/`interview`/`planning` happen before an
Orchestrator or any DAG exists at all. Routing which envelope *kind*
should trigger which phase is a workflow/router concern (Task 3 and
later), which this task must not build. So, at this layer, whichever
component owns a phase transition announces it explicitly: a `status`
envelope whose payload carries `{"phase": <one of PHASES>, ...}`. `reduce`
reads that field and nothing else to decide the phase; every other
envelope kind still counts toward `envelope_count` (so the fold sees every
envelope) but leaves `phase`/`context`/`history` unchanged, exactly like a
router or brief compiler passing through kernel-invisible traffic.

Attempt bookkeeping (Outcome 2 Task 4 quality-review fix, and its round-3
follow-up). A `request` envelope's payload carries `task_id` and, when it
also carries `task_id`, `attempt` is now MANDATORY, not merely validated
when present: a `request` envelope always dispatches one attempt of one
task, so "which attempt" is never meaningfully absent, and this module
raises `Blocked` naming the field if it is missing. (An earlier round of
this fix made `attempt` presence-gated exactly like `task_id` -- validated
only if included -- to avoid breaking a then-frozen test file's fixtures
that never carried the field at all. That reading left the guarantee
defeatable by omission: three `request` envelopes for the same task with
no `attempt` key folded to `attempts_of() == 0` and status `running`,
identical in shape to the unenforced-convention problem this fix exists
to eliminate. Root re-scoped the frozen file to close the gap; see that
file's own history for the one-line fixture change this forced.) Once
present, `attempt` must be a non-negative integer, and the sequence of
attempts for one task_id must be exactly 1, 2, 3, ... with no repeats and
no gaps -- a second `request` for a (task_id, attempt) pair already seen,
or one that skips ahead, is rejected here, in the reducer, rather than by
the mailbox (which stays a dumb append-only log with no opinion about
payload shape). `attempts` (the derived mapping this validation feeds) is
exact only because both the mandatory-presence check and the sequencing
rejection hold. `result` envelopes get type validation on `attempt` when
present (still presence-gated: a missing `attempt` there is not the same
defect, since a result is reporting on an attempt a request already
claimed and counted, not claiming a new one itself) but no mandatory
requirement and no sequencing rule -- (b)/(c) in the fix, and this
follow-up, are request-only.
"""

from dataclasses import dataclass

from qc_lib import Blocked, freeze

STAGE = "run_state"

PHASES = (
    "discovery",
    "interview",
    "planning",
    "orchestration",
    "execution",
    "verification",
    "completed",
    "blocked",
    "awaiting-user-input",
)

INITIAL_PHASE = "discovery"

TASK_STATUSES = ("pending", "running", "passed", "failed")
VALID_OUTCOMES = ("passed", "failed")

# Structural guarantee, checked once at import time rather than on every
# envelope reduced: every valid outcome must also be a valid task status,
# since a 'result' envelope's outcome is written straight into task_status.
# This is the only place that relationship can actually be violated -- an
# edit to one of the two constants above -- so this is where it is enforced.
assert set(VALID_OUTCOMES) <= set(TASK_STATUSES), (
    "VALID_OUTCOMES must be a subset of TASK_STATUSES"
)


@dataclass(frozen=True)
class RunState:
    """The immutable, derived state of one run.

    `history` records every macro phase reached so far, in order,
    including repeats and always ending in `phase` -- it is populated
    solely by `reduce`'s fold, never edited directly. `context` is the
    frozen payload of the status envelope that produced the current
    phase (empty for the untouched initial state), so a `blocked` or
    `awaiting-user-input` state can carry along e.g. a reason or question
    without this module needing to know what a reason or question is.

    `task_status` is a frozen mapping from task_id to one of
    ("pending", "running", "passed", "failed"), derived from `request` and
    `result` envelopes: a `request` envelope carrying a task_id marks
    the task running; a `result` envelope with an outcome marks it
    passed or failed. Any task never mentioned is pending.

    `attempts` is a frozen mapping from task_id to the number of `request`
    envelopes carrying a valid `attempt` number seen for that task_id --
    exact because `_apply` rejects a repeated or out-of-order attempt
    number for the same task_id before it ever reaches this mapping (see
    the module docstring). A task_id never mentioned with an `attempt` is
    absent from the mapping; `attempts_of` below makes that default (0)
    explicit, mirroring `status_of`'s "pending" default for `task_status`.

    This is a plain frozen dataclass with no validating alternate
    constructor, unlike `RunSpec`/`AgentSpec`/`Envelope` in kernel_specs.py
    -- there is nothing here for an external caller to get wrong the way a
    hand-authored RunSpec/AgentSpec/Envelope can be malformed, since the
    only way to *reach* a given RunState in a real run is by folding
    Envelope objects that were already validated on construction. What
    __post_init__ below does guard is immutability itself: `history`,
    `context`, `task_status` and `attempts` must end up frozen (a tuple of
    strings, and recursively frozen mappings) no matter which of the two
    construction paths -- `reduce`'s internal building, or a direct
    `RunState(...)` call bypassing reduce entirely -- was used to build
    this instance.
    """

    run_id: object
    phase: str
    envelope_count: int
    context: object
    history: tuple
    task_status: object
    attempts: object

    def __post_init__(self):
        object.__setattr__(self, "history", tuple(self.history))
        object.__setattr__(self, "context", freeze(self.context))
        object.__setattr__(self, "task_status", freeze(self.task_status))
        object.__setattr__(self, "attempts", freeze(self.attempts))


def initial_state():
    """The state of a run before any envelope has been folded into it.

    A run starts in `discovery` by definition, so `history` already
    contains that phase even though no envelope produced it -- this keeps
    the invariant `state.history[-1] == state.phase` true for every
    RunState, including this one.
    """
    return RunState(
        run_id=None,
        phase=INITIAL_PHASE,
        envelope_count=0,
        context={},
        history=(INITIAL_PHASE,),
        task_status={},
        attempts={},
    )


def status_of(state, task_id):
    """Return the status of a task, or 'pending' if the task was never mentioned.

    `task_status` records only tasks that have been mentioned in envelopes
    (via a 'request' or 'result' envelope carrying the task_id). Any task
    not in task_status is implicitly pending and has not yet started.
    This function makes that default explicit.
    """
    if task_id in state.task_status:
        return state.task_status[task_id]
    return "pending"


def attempts_of(state, task_id):
    """Return the number of valid 'request' attempts recorded for a task,
    or 0 if the task was never mentioned with an `attempt` number.

    Mirrors `status_of`'s explicit default. Exact (not merely a count of
    'request' envelopes seen) because `_apply` rejects a duplicate or
    out-of-order `attempt` value for the same task_id before it can ever
    be folded into `state.attempts` -- see the module docstring.
    """
    if task_id in state.attempts:
        return state.attempts[task_id]
    return 0


def _apply(state, envelope):
    if state.run_id is not None and envelope.run_id != state.run_id:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=(
                f"envelope run_id {envelope.run_id!r} does not match "
                f"this run's id {state.run_id!r}"
            ),
            recovery_action="only reduce envelopes that belong to the same run_id",
        )
    run_id = envelope.run_id if state.run_id is None else state.run_id

    # Handle task status updates from request and result envelopes
    # task_status contains only tasks that have been mentioned in envelopes
    task_status = dict(state.task_status)
    attempts = dict(state.attempts)

    if envelope.kind == "request":
        payload = envelope.payload
        if hasattr(payload, "get") and "task_id" in payload:
            # Presence, not truthiness: a present-but-invalid task_id (e.g.
            # "", None, 0) must be validated and rejected, not silently
            # skipped the way `if task_id:` used to skip it.
            task_id = payload.get("task_id")
            if not isinstance(task_id, str) or not task_id:
                raise Blocked(
                    stage=STAGE,
                    reason_code="malformed_checkpoint",
                    detail=(
                        f"'request' envelope payload['task_id'] must be a "
                        f"non-empty string, got {task_id!r}"
                    ),
                    recovery_action="set payload['task_id'] to a non-empty string",
                )
            task_status[task_id] = "running"

            # attempt is now MANDATORY on a task-dispatching request (round-3
            # follow-up to FIX 4): a request always dispatches one attempt of
            # one task, so unlike task_id's own presence-gated pattern above,
            # there is no valid reading of "this request carries no attempt
            # number". Presence-gating this (an earlier round's judgment
            # call) left attempts_of() defeatable by omission -- see the
            # module docstring for the exact reproduction that forced this.
            if "attempt" not in payload:
                raise Blocked(
                    stage=STAGE,
                    reason_code="malformed_checkpoint",
                    detail=(
                        "'request' envelope payload is missing required "
                        "field 'attempt'"
                    ),
                    recovery_action=(
                        "set payload['attempt'] to the next sequential "
                        f"attempt number for task_id={task_id!r}"
                    ),
                )
            attempt = payload.get("attempt")
            if (
                not isinstance(attempt, int)
                or isinstance(attempt, bool)
                or attempt < 0
            ):
                raise Blocked(
                    stage=STAGE,
                    reason_code="malformed_checkpoint",
                    detail=(
                        f"'request' envelope payload['attempt'] must be a "
                        f"non-negative integer, got {attempt!r}"
                    ),
                    recovery_action="set payload['attempt'] to a non-negative integer",
                )
            expected_next = attempts.get(task_id, 0) + 1
            if attempt != expected_next:
                raise Blocked(
                    stage=STAGE,
                    reason_code="malformed_checkpoint",
                    detail=(
                        f"'request' envelope for task_id={task_id!r} has "
                        f"attempt={attempt!r}, but attempt {expected_next} "
                        "was expected next (a duplicate or out-of-order "
                        "attempt number for this task)"
                    ),
                    recovery_action=(
                        f"set payload['attempt'] to {expected_next} for "
                        f"task_id={task_id!r}"
                    ),
                )
            attempts[task_id] = attempt
    elif envelope.kind == "result":
        payload = envelope.payload
        # attempt on a result gets the same type validation as on a
        # request (presence-gated), but no sequencing rule: a result is
        # reporting on an attempt a request already claimed and validated,
        # not claiming a new one itself.
        if hasattr(payload, "get") and "attempt" in payload:
            attempt = payload.get("attempt")
            if (
                not isinstance(attempt, int)
                or isinstance(attempt, bool)
                or attempt < 0
            ):
                raise Blocked(
                    stage=STAGE,
                    reason_code="malformed_checkpoint",
                    detail=(
                        f"'result' envelope payload['attempt'] must be a "
                        f"non-negative integer, got {attempt!r}"
                    ),
                    recovery_action="set payload['attempt'] to a non-negative integer",
                )
        # Presence, not truthiness: `if task_id and outcome:` used to let a
        # present-but-falsy outcome (e.g. "") short-circuit before the
        # VALID_OUTCOMES check ever ran, silently leaving the task stranded
        # at "running" forever. Gate on whether the keys are present at
        # all, then validate whatever value is there -- absent means
        # absent, present means validated.
        if (
            hasattr(payload, "get")
            and "task_id" in payload
            and "outcome" in payload
        ):
            task_id = payload.get("task_id")
            outcome = payload.get("outcome")
            if not isinstance(task_id, str) or not task_id:
                raise Blocked(
                    stage=STAGE,
                    reason_code="malformed_checkpoint",
                    detail=(
                        f"'result' envelope payload['task_id'] must be a "
                        f"non-empty string, got {task_id!r}"
                    ),
                    recovery_action="set payload['task_id'] to a non-empty string",
                )
            if outcome not in VALID_OUTCOMES:
                raise Blocked(
                    stage=STAGE,
                    reason_code="malformed_checkpoint",
                    detail=(
                        f"'result' envelope outcome must be one of {VALID_OUTCOMES}, "
                        f"got {outcome!r}"
                    ),
                    recovery_action=f"set payload['outcome'] to one of {VALID_OUTCOMES}",
                )
            task_status[task_id] = outcome

    if envelope.kind != "status":
        return RunState(
            run_id=run_id,
            phase=state.phase,
            envelope_count=state.envelope_count + 1,
            context=state.context,
            history=state.history,
            task_status=task_status,
            attempts=attempts,
        )

    payload = envelope.payload
    phase = payload.get("phase") if hasattr(payload, "get") else None
    if phase not in PHASES:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=(
                f"'status' envelope payload must set 'phase' to one of {PHASES}, "
                f"got {phase!r}"
            ),
            recovery_action=f"set payload['phase'] to one of {PHASES}",
        )
    return RunState(
        run_id=run_id,
        phase=phase,
        envelope_count=state.envelope_count + 1,
        context=payload,
        history=state.history + (phase,),
        task_status=task_status,
        attempts=attempts,
    )


def reduce(envelopes, state=None):
    """Fold an envelope sequence into a `RunState`.

    Pure: no I/O, no clock read, no randomness, no module-level mutable
    state, and the input sequence is only ever iterated, never written to.
    `state` defaults to `initial_state()`; passing an explicit prior state
    is what lets a caller reduce a prefix, then continue from the result
    with the remaining envelopes, and land on exactly the state a single
    whole-sequence reduce would have produced -- reduce is nothing more
    than `functools.reduce(_apply, envelopes, state)` with a friendlier
    default.
    """
    if state is None:
        state = initial_state()
    for envelope in envelopes:
        state = _apply(state, envelope)
    return state
