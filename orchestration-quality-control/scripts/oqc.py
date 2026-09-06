#!/usr/bin/env python3
"""oqc.py — the single CLI/library boundary over the deterministic kernel.

This is the Outcome 2 Task 5 slice of
AI_Codex/Architecture/ADR/0014-generated-workflow-deterministic-kernel.md.
Scope was clarified by root on 2026-09-05: `oqc.py` cannot be a CLI
boundary with nothing to drive, and `replay` needs a real run to replay,
so this module also owns the orchestrator `drive` loop that Outcome 2
Task 4 kept inline inside its test fixtures (tests/test_replay.py). This
module provides exactly three capabilities -- `drive`, `replay`, `verify`
-- plus a thin `__main__` CLI over the last two.

The kernel stays importable without this module. Nothing in
kernel_specs.py, run_state.py, router.py, mailbox.py, gate.py,
adapter_port.py, fake_adapter.py, compile_prompt.py or qc_lib.py imports
oqc -- see tests/test_oqc.py's KernelStaysImportableWithoutOqcTest, which
scans every one of those modules' source for the substring rather than
merely trusting the import graph at the time this was written.

Every decision in `drive` below is made by this module or by the
gate.py functions it calls -- `router.next_tasks`, `gate.gate_result` and
`gate.retry_or_block` are reused, never reimplemented, and
`adapter_port.AdapterPort` is the only thing an adapter is asked to do:
execute (spawn, emit a status, relay a question, enforce a policy hook).
No judgment leaks into the adapter, per ADR 0014 decision 0.
"""

import argparse
from dataclasses import dataclass

from adapter_port import AdapterPort
from compile_prompt import compile_brief
from gate import PASSED, RETRY, gate_result, retry_or_block
from kernel_specs import GENESIS_HASH
from mailbox import Mailbox
from qc_lib import Blocked, run_main, thaw
from router import next_tasks, validate_pair
from run_state import reduce, status_of

STAGE = "oqc"

# The macro phase drive() names when it records a mid-run decision (e.g. a
# retry) that is not itself a lifecycle transition. 'execution' is the
# run_state.PHASES member that best describes "a task is being worked on
# and the run has neither finished nor stalled" -- see the RETRY branch in
# drive() below.
_WORKING_PHASE = "execution"


# ---------------------------------------------------------------------------
# drive(): the orchestrator loop.
# ---------------------------------------------------------------------------


def _node_for(dag, task_id):
    for node in dag.tasks:
        if node.task_id == task_id:
            return node
    raise Blocked(
        stage=STAGE,
        reason_code="missing_target",
        detail=f"task_id {task_id!r} is not a node in this DAG",
        recovery_action="only drive task_ids that router.next_tasks actually returned",
    )


def _agent_spec_for(agent_specs, node):
    agent_spec = agent_specs.get(node.role)
    if agent_spec is None:
        raise Blocked(
            stage=STAGE,
            reason_code="missing_target",
            detail=f"no AgentSpec for role {node.role!r} (task {node.task_id!r})",
            recovery_action="add an AgentSpec for this role to agent_specs",
        )
    return agent_spec


def _require_adapter_port(adapter):
    if not isinstance(adapter, AdapterPort):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"adapter must be an adapter_port.AdapterPort, got {type(adapter).__name__}",
            recovery_action="pass a concrete AdapterPort implementation",
        )


def _require_max_attempts(max_attempts):
    if (
        not isinstance(max_attempts, int)
        or isinstance(max_attempts, bool)
        or max_attempts < 1
    ):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"max_attempts must be a positive integer, got {max_attempts!r}",
            recovery_action="pass max_attempts >= 1",
        )


def _latest_result_payload(mailbox, *, task_id, attempt):
    matches = [
        envelope.payload
        for envelope in mailbox.read_all()
        if envelope.kind == "result"
        and envelope.payload.get("task_id") == task_id
        and envelope.payload.get("attempt") == attempt
    ]
    if not matches:
        raise Blocked(
            stage=STAGE,
            reason_code="missing_target",
            detail=(
                f"no 'result' envelope found for task_id={task_id!r} "
                f"attempt={attempt!r} after spawn"
            ),
            recovery_action="an AdapterPort.spawn() implementation must append a matching 'result' envelope",
        )
    return matches[-1]


def drive(dag, adapter, mailbox, agent_specs, max_attempts, *, run_id):
    """Run `dag` to completion (or to a terminal stop) through `adapter`.

    This is the real orchestrator loop Outcome 2 Task 4's test fixtures
    (tests/test_replay.py) drove by hand: select a runnable task with
    `router.next_tasks`, compile its brief, spawn it through the adapter,
    gate the result, and either retry carrying the critique forward or
    stop at a terminal state. All engine authority lives here (and in the
    gate.py functions this calls) -- the adapter only executes.

    Parameters match the brief's named signature
    (`dag, adapter, mailbox, agent_specs, max_attempts`) with one
    necessary addition: `run_id`, keyword-only and required. None of
    `dag` (a `kernel_specs.TaskDag`), `agent_specs`, or `max_attempts`
    carries a run identity, and every `AdapterPort` method requires
    `run_id` explicitly -- there is no way to spawn the very first
    envelope of a fresh run without one, so it must come from the caller.
    `agent_specs` is a mapping from role (as named on a
    `kernel_specs.TaskNode`) to the `kernel_specs.AgentSpec` generated
    for that role; `max_attempts` is the attempt budget shared by every
    task in `dag` (matching tests/test_replay.py's `MAX_ATTEMPTS`, a
    single scalar applied uniformly).

    Scheduling. `router.next_tasks(dag, state)` is re-derived from the
    mailbox at the top of every outer iteration and answers only "which
    *new* tasks are now runnable" (pending, with every dependency
    passed) -- it has no notion of "retry this task that already
    failed", because a failed task's status is 'failed', not 'pending',
    and `next_tasks` never returns a non-pending task. Retrying a task
    already in flight is instead driven directly by
    `gate.retry_or_block`'s RETRY decision, in the inner loop below,
    exactly like tests/test_replay.py's own fixtures never asked
    `next_tasks` for permission to attempt task-a a second time. When
    `next_tasks` returns more than one runnable task_id (independent
    branches with no dependency between them), this loop takes the
    first in its returned sort order, drives it to conclusion (pass or a
    terminal stop), and only then re-derives `next_tasks` for the next
    one -- tasks are never run concurrently, matching "no long-running
    process" (ADR 0014 decision 0) and this kernel's model-free,
    single-threaded nature.

    If any task reaches a terminal (non-RETRY) decision, this function
    stops the *entire* run immediately and returns -- it does not
    attempt to keep making progress on unrelated, still-runnable
    branches. This matches the two-task dependent fixture this task's
    evidence is built on (Outcome 2 Task 4's Fixture B, where task-b must
    never run once task-a is exhausted) and keeps this slice's scope to
    exactly what is tested; a scheduler that keeps running healthy
    siblings past a sibling's terminal block is a real, larger feature
    this kernel slice does not build.

    Two findings carried forward from Task 4's quality review, both
    closed in this function:

    1. A RETRY decision now leaves a durable trace. The instant
       `retry_or_block` returns RETRY, this function calls
       `adapter.emit_status` to append a 'status' envelope recording
       that decision (`context={"decision": "retry", "task_id":...,
       "critique":..., "attempt":..., "attempts_remaining":...}`)
       *before* compiling or spawning the next attempt. Without this, a
       crash between the decision and the next spawn would leave the
       task sitting at status 'failed' with nothing in the mailbox to
       distinguish "root chose to retry" from silent abandonment --
       replaying the mailbox would show only a failed result, identical
       in shape either way. The recorded phase is `_WORKING_PHASE`
       ('execution'): a retry is not itself a macro lifecycle
       transition, so it does not claim to be 'completed', 'blocked', or
       any other terminal name -- only the `context` payload carries the
       decision. See tests/test_oqc.py's
       RetryDecisionRecordedDurablyTest, which truncates a mailbox
       immediately after this envelope and confirms the decision is
       still legible.

    2. `relay_question` and `enforce_policy` are now composed into this
       loop alongside `spawn`, `emit_status`, `gate_result` and
       `retry_or_block`, so all four `AdapterPort` operations work
       together rather than being proven only in isolation (as
       tests/test_adapter_port.py and tests/test_fake_adapter.py already
       do for each method alone):

       - `enforce_policy` is called once per attempt, immediately before
         that attempt's `spawn` (`hook_name="pre-spawn"`, carrying
         `task_id`/`attempt` as context). A `qc_lib.Blocked` raised there
         is authoritative (per `adapter_port.AdapterPort.enforce_policy`'s
         own docstring) and stops the run before anything is appended --
         proven by tests/test_oqc.py's
         EnforcePolicyComposedWithSpawnTest.

       - `relay_question` is called on the one path this model-free
         kernel slice actually has a real question to ask: once
         `retry_or_block` returns a terminal decision, this function
         relays a question to root asking how to proceed, *composed
         with* the terminal status the gate already decided, rather than
         exercised in isolation. It does **not** attempt to make
         `awaiting-user-input` reachable. `gate.retry_or_block` (which
         this module must not reimplement or override -- ADR 0014
         decision 4 gives only the engine that decision, and here "the
         engine" for this specific choice is `gate.py`, not `oqc.py`)
         never returns AWAITING_USER_INPUT; every exhaustion it produces
         names BLOCKED_STATE. Making the run declare
         'awaiting-user-input' from inside `drive` instead would mean
         this loop fabricating a judgment -- "this failure specifically
         needs a human decision, as opposed to just being stuck" -- that
         nothing in a deterministic, model-free path actually has a
         basis to make; `adapter_port.AdapterPort.relay_question`'s own
         docstring describes relaying a question a worker already asked
         over a separate channel this kernel slice does not build. So
         that phase remains unreachable here, exactly as
         gate.py's own reservation note beside AWAITING_USER_INPUT
         still accurately describes, and tests/test_oqc.py's
         AwaitingUserInputRemainsUnreachableTest pins that as a
         deliberate scope decision rather than an oversight.
    """
    _require_adapter_port(adapter)
    _require_max_attempts(max_attempts)

    while True:
        state = reduce(mailbox.read_all())
        runnable = next_tasks(dag, state)
        if not runnable:
            break

        task_id = runnable[0]
        node = _node_for(dag, task_id)
        agent_spec = _agent_spec_for(agent_specs, node)

        critique = None
        attempt = 0
        while True:
            attempt += 1
            brief = compile_brief(node, agent_spec, critique=critique, attempt=attempt)

            adapter.enforce_policy(
                run_id=run_id,
                hook_name="pre-spawn",
                context={"task_id": task_id, "attempt": attempt},
            )
            adapter.spawn(
                mailbox,
                run_id=run_id,
                task_id=task_id,
                attempt=attempt,
                agent_id=agent_spec.agent_id,
                brief=brief,
            )

            result_payload = _latest_result_payload(mailbox, task_id=task_id, attempt=attempt)
            verdict = gate_result(result_payload)

            if verdict.outcome == PASSED:
                break  # this task is done; the outer loop re-derives next_tasks

            state = reduce(mailbox.read_all())
            attempts_remaining = max_attempts - attempt
            decision = retry_or_block(state, task_id, verdict.critique, attempts_remaining)

            if decision.action == RETRY:
                # FINDING 1: record the retry decision durably, in the
                # mailbox, at the moment it is made.
                adapter.emit_status(
                    mailbox,
                    run_id=run_id,
                    phase=_WORKING_PHASE,
                    context={
                        "decision": RETRY,
                        "task_id": task_id,
                        "critique": decision.critique,
                        "attempt": attempt,
                        "attempts_remaining": attempts_remaining,
                    },
                )
                critique = decision.critique
                continue  # attempt the same task again

            # Terminal: gate.retry_or_block returned a non-RETRY decision
            # (BLOCKED_STATE today -- see the docstring above for why
            # AWAITING_USER_INPUT is not manufactured here).
            adapter.relay_question(
                mailbox,
                run_id=run_id,
                question=(
                    f"task '{task_id}' exhausted its attempt budget after "
                    f"{attempt} attempt(s); final critique: {decision.critique}. "
                    "how should the run proceed?"
                ),
            )
            adapter.emit_status(
                mailbox,
                run_id=run_id,
                phase=decision.phase,
                context={"task_id": task_id, "critique": decision.critique},
            )
            return reduce(mailbox.read_all())

    # Every runnable task was driven to a PASSED verdict above (any
    # terminal decision returns immediately, before this point), so a
    # normal exit here means the whole DAG passed. The check below is
    # defensive, not load-bearing: kernel_specs.TaskDag already refuses a
    # DAG with an unknown dependency or a cycle, so every node is
    # reachable by construction -- but naming the invariant explicitly,
    # and failing loudly if it were ever wrong, costs nothing.
    final_state = reduce(mailbox.read_all())
    if not all(status_of(final_state, node.task_id) == PASSED for node in dag.tasks):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail="next_tasks reported nothing runnable but not every DAG task has passed",
            recovery_action="this indicates an unreachable task in the DAG; check depends_on",
        )
    adapter.emit_status(mailbox, run_id=run_id, phase="completed", context={})
    return reduce(mailbox.read_all())


# ---------------------------------------------------------------------------
# replay(): rebuild derived state from the event log.
# ---------------------------------------------------------------------------


def replay(mailbox):
    """Rebuild a mailbox's derived `run_state.RunState` from its history.

    This is nothing more than `run_state.reduce` over the mailbox's full
    ordered history -- replay is not a second, divergent derivation of
    run state, it is the same pure reduction a live run already used at
    every step. Replaying a mailbox therefore always equals the state the
    live run that produced it ended on, including after a
    serialise/reload round trip via `mailbox.Mailbox.to_jsonl`/
    `from_jsonl` (see tests/test_oqc.py's ReplayTest).
    """
    return reduce(mailbox.read_all())


# ---------------------------------------------------------------------------
# verify(): structural integrity, plus the cryptographic hash chain.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerifyResult:
    """What `verify` returns: derived state, plus the mailbox's head hash.

    `state` is exactly what `replay` would have returned for the same
    mailbox. `head_hash` is `kernel_specs.Envelope.hash()` of the last
    envelope in the mailbox (`kernel_specs.GENESIS_HASH` for an empty
    mailbox) -- see `verify`'s own docstring for why a caller needs this
    value and cannot get it any other way.
    """

    state: object
    head_hash: str


def verify(mailbox):
    """Check a mailbox's structural invariants and its hash chain; raise
    `qc_lib.Blocked` naming the first violation found.

    Structural checks (1-4 below) and the hash chain (5) together cover
    every named tampering class: a hand-edited payload that changes an
    outcome, id, or ordering, whether or not it also breaks the chain.
    Before Outcome 3, `kernel_specs.Envelope` carried no hash field at
    all, so a tampered *payload* that disturbed none of checks 1-4 (e.g.
    editing a result's `outcome` from 'failed' to 'passed' without
    touching any id, pairing, or attempt sequencing) was out of this
    function's reach. Check 5 closes exactly that gap: any edit to any
    envelope's canonical JSON -- including a payload edit that disturbs
    nothing else -- changes that envelope's hash, which the *next*
    envelope's `previous_hash` no longer matches.

    The one entry this still cannot protect is the last envelope in the
    mailbox: nothing follows it to carry its hash forward, so a tamper
    confined to that one entry changes nothing check 5 can compare against
    -- there is no next `previous_hash` to disagree with it. That is why
    this function returns `head_hash` (see `VerifyResult`): a caller that
    records that value somewhere outside the mailbox itself (an external
    log, a second run's first envelope, a signature) closes the gap for
    everything except whatever is later appended after that recording; a
    caller that never anchors it leaves the last entry unprotected
    indefinitely. This function cannot anchor `head_hash` itself -- it has
    no notion of "outside the mailbox" -- it can only hand the value back.

    What is checked, in this order, each raising `qc_lib.Blocked` on the
    first violation found:

    1. Every `envelope_id` is unique within the mailbox. `mailbox.Mailbox`
       already enforces this on every envelope that arrives through its
       public `append`/constructor, but this function does not assume
       that guarantee held for whatever mailbox it was actually handed
       (e.g. one built by writing directly to `Mailbox`'s internal
       storage, bypassing its guard entirely) -- it re-checks
       independently, exactly the "test every construction path"
       standard this kernel already holds itself to elsewhere.

    2. Every envelope's (sender, recipient) pair is legal, via
       `router.validate_pair` -- reused, not reimplemented. Note that
       `mailbox.Mailbox.append` itself never calls `validate_pair` (only
       `adapter_port.AdapterPort._append` does, for envelopes built
       through a real adapter call); a mailbox loaded from a hand-edited
       or otherwise tampered JSONL file has never had this checked until
       `verify` runs it.

    3. Every 'result' envelope naming a `task_id` is preceded *earlier in
       the log* by a matching 'request' envelope for the same
       `(task_id, attempt)` pair. `attempt` is unconditional here (no
       task_id-only fallback) because `run_state._apply` (Outcome 2 Task
       5 quality-review FINDING 2) now makes `attempt` mandatory on every
       task-resolving 'result' at the source -- a 'result' that ever
       reaches this check without one could not have survived `reduce`
       either, so a task_id-only fallback here would only ever paper over
       the same gap that mandatory field already closes, not handle a
       case that can legitimately still occur. This single check subsumes
       three of the named tampering classes: reordering (a result moved
       ahead of its request leaves nothing earlier that matches when the
       result is reached), deletion (removing a request while its result
       remains leaves the same gap), and an outright forged result with
       no request anywhere in the log at all.

    4. No second 'result' answers a `(task_id, attempt)` pair already
       resolved (FINDING 1). A duplicated result -- a flaky transport's
       retried callback in a real adapter, or an outright forgery -- must
       not be allowed to silently override a genuine outcome (e.g. flip a
       recorded failure to a pass) just because its `envelope_id` differs
       from the first. The *first* result for a given `(task_id, attempt)`
       is accepted (and is what check 3 above matches future results
       against); a second is rejected here, naming the task and attempt,
       before this function ever gets to check 5.

    5. The hash chain (Outcome 3 Task 1): for every envelope in order,
       its `previous_hash` must equal `kernel_specs.GENESIS_HASH` if it is
       the first envelope in the mailbox, or `kernel_specs.Envelope.hash()`
       of the envelope immediately before it otherwise. `Blocked` names
       the first envelope_id whose `previous_hash` does not match.

    6. Run continuity and sequential per-task attempt numbering, by
       delegating to `run_state.reduce` -- both are already enforced
       there (`run_state._apply` rejects a second run_id mixed into one
       mailbox, and rejects a repeated or out-of-order attempt number
       for a task_id). Reimplementing either check here would be a
       second, divergent copy of logic this kernel already owns; this
       function instead reuses it and lets whatever `qc_lib.Blocked`
       `reduce` raises propagate unchanged.

    Returns a `VerifyResult` carrying the `run_state.RunState` `reduce`
    derived while performing check 6 (so a caller that already wants
    derived state does not need a second pass over the mailbox) and the
    mailbox's head hash (see above).
    """
    envelopes = mailbox.read_all()

    seen_ids = set()
    for envelope in envelopes:
        if envelope.envelope_id in seen_ids:
            raise Blocked(
                stage=STAGE,
                reason_code="malformed_checkpoint",
                detail=f"duplicate envelope_id {envelope.envelope_id!r} in mailbox",
                recovery_action="ensure every envelope_id is unique within the mailbox",
            )
        seen_ids.add(envelope.envelope_id)

    requested_pairs = set()
    answered_pairs = set()
    for envelope in envelopes:
        validate_pair(envelope.sender, envelope.recipient)

        payload = envelope.payload
        task_id = payload.get("task_id") if hasattr(payload, "get") else None
        attempt = payload.get("attempt") if hasattr(payload, "get") else None

        if envelope.kind == "request":
            if isinstance(task_id, str) and task_id:
                if attempt is not None:
                    requested_pairs.add((task_id, attempt))
        elif envelope.kind == "result":
            if isinstance(task_id, str) and task_id:
                pair = (task_id, attempt)
                if pair not in requested_pairs:
                    raise Blocked(
                        stage=STAGE,
                        reason_code="malformed_checkpoint",
                        detail=(
                            f"'result' envelope for task_id={task_id!r} "
                            f"attempt={attempt!r} has no preceding 'request' "
                            "envelope for the same task and attempt"
                        ),
                        recovery_action=(
                            "ensure a matching 'request' envelope for this "
                            "task_id and attempt appears earlier in the mailbox"
                        ),
                    )
                # FINDING 1: a second result for a pair already answered
                # must not silently override the first.
                if pair in answered_pairs:
                    raise Blocked(
                        stage=STAGE,
                        reason_code="malformed_checkpoint",
                        detail=(
                            f"a second 'result' envelope answers task_id={task_id!r} "
                            f"attempt={attempt!r}, which already has a result"
                        ),
                        recovery_action=(
                            "ensure exactly one 'result' envelope exists per "
                            "task_id and attempt"
                        ),
                    )
                answered_pairs.add(pair)

    # CHECK 5: the hash chain. A plain linear walk: each envelope's
    # previous_hash must match the hash of whatever came immediately
    # before it (or GENESIS_HASH, for the first). This is the check that
    # makes a payload-only tamper -- one that disturbs none of checks 1-4
    # above -- visible: editing anything in an envelope's canonical JSON
    # (including its own previous_hash) changes that envelope's hash,
    # which the following envelope's previous_hash then no longer equals.
    expected_previous_hash = GENESIS_HASH
    for envelope in envelopes:
        if envelope.previous_hash != expected_previous_hash:
            raise Blocked(
                stage=STAGE,
                reason_code="malformed_checkpoint",
                detail=(
                    f"envelope {envelope.envelope_id!r} has previous_hash "
                    f"{envelope.previous_hash!r}, but the entry before it in "
                    f"this mailbox hashes to {expected_previous_hash!r} -- "
                    "the hash chain is broken"
                ),
                recovery_action=(
                    "this mailbox has been tampered with, or was built "
                    "without routing every envelope through "
                    "adapter_port.AdapterPort._append; do not trust its "
                    "history"
                ),
            )
        expected_previous_hash = envelope.hash()

    # expected_previous_hash now holds the hash of the mailbox's last
    # envelope (or GENESIS_HASH, for an empty mailbox) -- the head hash a
    # caller must anchor externally, since nothing in the mailbox itself
    # protects this one entry. See this function's own docstring.
    head_hash = expected_previous_hash

    return VerifyResult(state=reduce(envelopes), head_hash=head_hash)


# ---------------------------------------------------------------------------
# __main__: a thin CLI over replay and verify. The library above is the
# real surface -- this just reads a JSONL mailbox from a path and prints
# the resulting derived state, or a Blocked payload, per qc_lib.run_main's
# shared exit-code contract.
# ---------------------------------------------------------------------------


def _state_to_dict(state):
    return {
        "run_id": state.run_id,
        "phase": state.phase,
        "envelope_count": state.envelope_count,
        "context": thaw(state.context),
        "history": list(state.history),
        "task_status": thaw(state.task_status),
        "attempts": thaw(state.attempts),
    }


def _load_mailbox_file(path):
    # OSError is caught broadly around the open (covering not just a
    # missing file but also e.g. IsADirectoryError -- `replay <a
    # directory>` -- and PermissionError), and UnicodeDecodeError
    # separately around the read (a file that exists and opens but is not
    # valid UTF-8). Both used to propagate as a bare, uncaught traceback
    # and a non-2 exit code, unlike every other failure path in this CLI;
    # both are now qc_lib.Blocked, naming the path, so run_main's shared
    # exit-0/exit-2 contract holds here too.
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise Blocked(
            stage=STAGE,
            reason_code="missing_target",
            detail=f"cannot read mailbox file {path!r}: {exc}",
            recovery_action="verify the path exists, is a regular file, and is readable",
        ) from exc
    except UnicodeDecodeError as exc:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"mailbox file {path!r} is not valid UTF-8: {exc}",
            recovery_action="ensure the mailbox file is UTF-8-encoded JSONL",
        ) from exc
    return Mailbox.from_jsonl(text)


def main():
    parser = argparse.ArgumentParser(
        description="Deterministic kernel CLI: replay or verify a mailbox JSONL file.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_replay = sub.add_parser("replay", help="Rebuild derived state from a mailbox JSONL file.")
    p_replay.add_argument("mailbox_path")

    p_verify = sub.add_parser("verify", help="Check structural integrity of a mailbox JSONL file.")
    p_verify.add_argument("mailbox_path")

    args = parser.parse_args()

    def body():
        mailbox = _load_mailbox_file(args.mailbox_path)
        if args.command == "replay":
            return _state_to_dict(replay(mailbox))
        result = verify(mailbox)
        printed = _state_to_dict(result.state)
        printed["head_hash"] = result.head_hash
        return printed

    run_main(STAGE, body)


if __name__ == "__main__":
    main()
