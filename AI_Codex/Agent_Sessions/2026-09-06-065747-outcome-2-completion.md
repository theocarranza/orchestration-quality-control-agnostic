---
date: 2026-09-06
timestamp: 2026-09-06T06:57:47-03:00
type: session
status: open
branch: feature/original-design-realignment
previous: "[[2026-09-05-031418-subagent-template-reconciliation]]"
next: null
ticket: "[[refactor-align-the-architecture-with-original-design]]"
plan: "[[2026-09-04-original-design-realignment-master-plan]]"
handoff: "[[2026-09-04-claude-original-design-implementation-handoff]]"
skill: root-architect-execution
---

# Session — Outcome 2 completion

Previous Session: [[2026-09-05-031418-subagent-template-reconciliation]]
Next Session: (none)

## Mandate

Carry Outcome 2 to its gate under owner authorisation to drive the
implementation to conclusion unattended, committing and pushing when the outcome
is genuinely concluded.

## Bootstrap — 2026-09-06T06:57:47-03:00

- Branch `feature/original-design-realignment` at `65c0c30`, pushed and in sync.
- Tasks 1, 2, 2b, 3, 4 and 5 committed and pushed. Task 6 is delivered and
  awaiting review; Task 7, the gate, remains.
- Suite at 442 tests, green under `python3.12`.
- Session rotated because the predecessor note crossed the eight-hour gate
  boundary and had begun blocking Bash writes — including a subagent's writes to
  the scratchpad. Resolved with the file tools, per the `Agent_Sessions`
  `file_path` exemption documented in that note. No policy skipped.

## Quota

Owner reported the five-hour session at 82% used and the weekly at 86% used
(weekly resets Monday 13:00, with a temporary 50% boost through 2026-09-13).
The plan's guard fires below 10% weekly or 5% session; neither has fired. A full
resumption handoff was written and pushed as `65c0c30` before starting Task 6,
so the work survives an abrupt stop.

## Checkpoint — Outcome 2 Task 6 delivered, review incomplete — 2026-09-06T07:05:00-03:00

```text
time: 2026-09-06T07:05:00-03:00
task: Outcome 2 Task 6 — the deterministic validation and compilation boundary
attempt: 1 of 3
worker model: claude-sonnet-5
worker effort: not settable on this host
spec validator: DISPATCHED AND KILLED by a session rate limit before returning
  any verdict. Not run. Must be re-run before the Outcome 2 gate.
quality reviewer: not yet dispatched
commands:
  command: PYTHONPATH=... python3.12 -m unittest discover -s .../scripts/tests
  counts: 442 tests, OK (412 entering the task)
  command: root verification — contract fixture, determinism, branches, tiers
  counts: all four confirmed by execution, detailed below
commit hash: pending
next: re-run both reviews on Task 6, then Task 7 — the Outcome 2 gate
```

Delivered `compile_workflow.py` and its tests. `compile_workflow(decisions)`
emits a `RunSpec`, a generated `TaskDag` and generated `AgentSpec` records as
three siblings, validating a contradictory `shape`/`named_inputs` pair before
emitting anything.

### Why this is committed before its reviews

The five-hour and weekly quotas were both close to their guards, and a rate
limit had just killed the plan-compliance validator mid-run. Leaving verified
work uncommitted across that boundary is the failure mode the resumption handoff
was written to prevent. Root committed on its own execution evidence and is
recording plainly that **neither review has run**. This is a deviation from the
per-task loop, taken deliberately and disclosed, not an omission.

Root's own verification, by execution rather than by reading the report:

- a relevant decision change (adding a named input) alters the emitted DAG, and
  the new role appears in the agent manifest
- an irrelevant change (language) leaves the DAG byte-identical
- recompiling identical decisions is byte-identical
- independent branches are genuinely emitted: `task-docs` and `task-api` with
  empty `depends_on`
- no `inherit` appears in any emitted `AgentSpec`
- an invalid `profile` is rejected by name — root hit this by passing a wrong
  value, so the validation path is exercised rather than assumed

### The parallel-branch limitation is now concrete, not theoretical

The implementer was told not to dodge this and did not. It compiled an
isolated-workers workflow with two genuinely independent tasks, scripted only
one to exhaust its budget, and left the other with no script entry at all — so
`FakeAdapter` would have raised had `drive` ever touched it. `drive` halted the
whole run at the first task's exhaustion; the healthy sibling stayed `pending`
and never reached the mailbox.

So one doomed branch silently blocks unrelated healthy siblings, with no way for
a caller to opt out short of editing a frozen function. This does not violate
Outcome 2's exit evidence, which names only the two-task dependent DAG and a
separate exhausted-retry fixture. It becomes a real question the moment a
generated multi-branch workflow is scheduled for actual work, which is
Outcome 3. Recorded here as an open architectural question for root, escalated
rather than judged unilaterally by the implementer.

### Outstanding before the gate

1. Re-run plan-compliance on Task 6. Root's specific question for it: the
   compiler validates only the subset of `decisions` it consumes and silently
   ignores the rest, so a typo such as `named_input` for `named_inputs` would
   compile a workflow with no branches rather than raising.
2. Run quality on Task 6.
3. Then Task 7, the gate.
