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

## Checkpoint — Outcome 2 gate PASS — 2026-09-06T11:05:57-03:00

```text
time: 2026-09-06T11:05:57-03:00
task: Outcome 2 Task 7 — the Outcome 2 gate
attempt: 1 of 3
worker model: none; Task 7 is root verification, not a code task
worker effort: not settable on this host
spec validator: claude-sonnet-5, read-only, PASS, no findings
quality reviewer: not dispatched; no product-code diff, and root holds the
  command evidence at this exact HEAD
commands:
  command: six baseline suites under python3.12
  counts: 443 + 8 + 6 + 36 + 19 + 49 = 561 tests, OK, zero failures
  command: python3.12 eval-harness/check_documentation_truth.py .
  counts: exit 0, no findings
  command: git diff --check over 0c056c2..HEAD and the worktree
  counts: exit 0 both; working tree clean
  command: existence check on the five formerly quarantined targets
  counts: all five present
commit hash: pending
next: Outcome 3 — the real orchestration slice
```

**Outcome 2 is complete.** Eighteen commits since the Outcome 1 gate. The kernel
went from nothing executable to 443 tests in its own suite, 561 across the tree.

### The first honest full sweep

Five of the six suites had not run since the interpreter was pinned to
`python3.12` in `23fe8c0`. Every task after that point verified only the scripts
suite, under the Validation scope rule. This gate is therefore the first
execution of the Claude hooks, the three adapters and the eval harness on the
interpreter the plan actually mandates. All five pass unchanged. The pin caused
no damage, which was not knowable before this sweep and is now evidence rather
than assumption.

### The quarantined claims are retired

ADR 0014 quarantined five components as named in prose but absent from the tree:
`scripts/oqc.py`, `scripts/mailbox.py`, `scripts/compile_prompt.py`,
`scripts/gate.py` and `schemas/envelope.schema.json`. All five now exist as
working code with tests. Outcome 1 made documentation truth executable so that
prose could not lead implementation; Outcome 2 made the implementation catch up
to the prose. The checker that would have failed on those names now passes
because the targets are real, not because the names were removed.

### Exit evidence, confirmed against code

The validator was told explicitly that six tasks' reports say this passes and
its job was to find out whether the code agrees — reports, commit messages,
docstrings and ledger checkpoints all excluded as evidence. It confirmed each
condition with citations:

- all nine observable phases table-tested, one `subTest` per phase, including
  `awaiting-user-input`
- the model-free replay running on a DAG **emitted by `compile_workflow`**, not
  hand-written, with the critique asserted on the second attempt's own request
  envelope and `completed` asserted on `reduce`-derived state
- a separate exhausted-retry fixture reaching a terminal state with the
  dependent task proven never to have run, including on an emitted DAG where the
  sibling had no script entry at all, so the fake adapter would have raised had
  `drive` touched it
- replay, legal and illegal routing, and no-direct-mutation cases through the
  fake adapter
- the compilation boundary with both halves of the contract fixture
- table tests rejecting direct state mutation and illegal sender/recipient pairs

It found no prose claiming a capability the tree lacks, and no vacuous test in
the load-bearing evidence.

### Four limits, disclosed rather than discovered

Each is recorded in the code that carries it, and the gate confirmed the
descriptions are accurate rather than merely present:

1. `verify` is structural, not cryptographic. ADR 0014 decision 2's artifact and
   brief hashes need an envelope field the frozen schema lacks. Outcome 3.
2. `drive` halts the whole run on any terminal decision rather than continuing
   independent branches. Demonstrated concretely on an emitted multi-branch DAG.
   This is the open architectural question for Outcome 3.
3. `compile_workflow` generates DAG topology and capabilities; `tools`,
   `output_schema`, `model_tier` and `reasoning_effort` are fixed placeholders,
   because no decision field exists to drive them and inventing one would
   manufacture a decision nobody made.
4. `gate_defaults` and `plan_interview` are reused only in tests. Runtime wiring
   is Outcome 5's product surface.

### What this outcome cost, and what caught what

Six implementation tasks, eleven implementer rounds, twelve reviews. Every
quality review found something real; three found defects that would have reached
Outcome 3. The pattern across all of them was the same shape: **a guarantee that
held only for well-formed input.** A falsy outcome pinning a task at `running`
forever. Recursion failing past 1000 nodes with a host-dependent threshold. An
attempt count defeatable by omitting a field. A duplicate result silently
overriding a real failure. A bare `KeyError` escaping a function that promised a
named error.

Two of those gaps trace to root's own freeze instructions, and one to a root
ruling that was right about counting and wrong about pairing. The layered review
caught all of them. That is the argument for keeping both reviewers.

Root's own drill was reported as inconclusive once, when a patch broke module
import rather than cleanly disabling the check under test. An inconclusive
experiment is not evidence, and was not recorded as one.

### Progress — incremental checkpointing added — 2026-09-06T11:20:00-03:00

Owner instruction: tighten ledger checkpoint frequency so an abrupt quota
interruption loses less. Encoded in both host copies of the skill rather than
practised only in this session.

The checkpoint contract now requires a short `### Progress` note at five points
that previously produced no record until a task passed: dispatching a worker or
reviewer, a verdict returning, root reproducing a finding, root making a design
ruling, and scope being widened or frozen. The full checkpoint block still lands
at `PASS`; the progress notes are the trail that survives losing the turn before
reaching it.

This session is the argument for it. Three rate limits killed agents mid-run —
one implementer twice and one validator once. Each time the work was recoverable
only because root had verified state on disk and could reconstruct it. A
reviewer's findings returned but not yet acted on would have been lost outright,
and re-earning them costs a full review round.

Negative results matter most here: root's inconclusive cycle-detection drill and
the rejected design options are exactly what a resumed session would otherwise
repeat at full cost.

### Progress — Outcome 3 opened, packet authored — 2026-09-06T11:35:00-03:00

Owner directed starting Outcome 3 with the weekly quota at 94% used. Root
flagged that the plan's guard had fired; the owner acknowledged and directed the
work regardless, which is the owner's call and is recorded as such rather than
argued twice.

Root began with planning rather than dispatch. A packet survives an abrupt stop;
an implementer round killed mid-run at this quota level loses its work and the
next session pays for it twice. No subagent was dispatched.

Six tasks authored, ordered by what Outcome 2 deferred rather than by
convenience:

1. **Envelope hashes and cryptographic verify.** Outcome 3's exit evidence names
   artifact hashes explicitly, so `verify` stops being structural-only. This
   changes a frozen wire format, so it lands alone and first, before anything is
   built on the old shape.
2. **The branch-halting decision.** `drive` halts the whole run on any terminal
   decision; on a generated multi-branch DAG one doomed branch starves healthy
   siblings. Decide it deliberately rather than discover it against a real host.
3. **The vendor-neutral Orchestrator contract.**
4. **The smallest real host adapter**, Claude first, since `adapters/claude/`
   already carries a builder, hooks and tests.
5. **The captured real run** — the load-bearing evidence, and the first thing in
   this workstream that is not model-free. Capture once, commit the capture,
   assert against the artifact so the evidence is replayable without re-spawning.
6. **The gate.**

`awaiting-user-input` becomes reachable in this outcome. Outcome 2 left it
representable but never decided, because no question-triggered transition existed
and fabricating one would have moved a state transition outside the engine. The
answer-relay evidence requires it, so it gets built in `gate.py` — the sole
authority — not in an adapter or a loop.
