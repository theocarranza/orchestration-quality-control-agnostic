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

    This is a plain frozen dataclass with no validating alternate
    constructor, unlike `RunSpec`/`AgentSpec`/`Envelope` in kernel_specs.py
    -- there is nothing here for an external caller to get wrong the way a
    hand-authored RunSpec/AgentSpec/Envelope can be malformed, since the
    only way to *reach* a given RunState in a real run is by folding
    Envelope objects that were already validated on construction. What
    __post_init__ below does guard is immutability itself: `history` and
    `context` must end up frozen (a tuple of strings, and a recursively
    frozen mapping) no matter which of the two construction paths --
    `reduce`'s internal building, or a direct `RunState(...)` call bypassing
    reduce entirely -- was used to build this instance.
    """

    run_id: object
    phase: str
    envelope_count: int
    context: object
    history: tuple

    def __post_init__(self):
        object.__setattr__(self, "history", tuple(self.history))
        object.__setattr__(self, "context", freeze(self.context))


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
    )


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

    if envelope.kind != "status":
        return RunState(
            run_id=run_id,
            phase=state.phase,
            envelope_count=state.envelope_count + 1,
            context=state.context,
            history=state.history,
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
