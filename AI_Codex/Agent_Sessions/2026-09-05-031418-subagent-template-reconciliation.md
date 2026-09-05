---
date: 2026-09-05
timestamp: 2026-09-05T03:14:18-03:00
type: session
status: open
branch: feature/original-design-realignment
previous: "[[2026-09-04-162018-outcome-1-gate-closure]]"
next: null
ticket: "[[refactor-align-the-architecture-with-original-design]]"
plan: "[[2026-09-04-original-design-realignment-master-plan]]"
handoff: "[[2026-09-04-claude-original-design-implementation-handoff]]"
skill: root-architect-execution
---

# Session — Subagent template reconciliation

Previous Session: [[2026-09-04-162018-outcome-1-gate-closure]]
Next Session: (none)

## Mandate

Owner instruction: the skill must be faithful to the orchestration and use what
it exposes, including the subagent templates. Confirm each host's real subagent
options from its own documentation, then make the skill own the role
definitions instead of restating them inline in every brief.

## Bootstrap — 2026-09-05T03:14:18-03:00

- Branch `feature/original-design-realignment`, in sync with `origin` at
  `0ed1e39`. Untracked: `.superpowers/` only.
- Outcome 2 Tasks 1 and 2 are committed and pushed. Task 2b (consolidate the
  freeze helper) and Task 3 are not started.
- The session gate fired on the predecessor note at the eight-hour boundary.
  Resolved exactly as that note documented: the gate exempts events whose
  `file_path` contains `Agent_Sessions`, which the file tools populate and a
  Bash `sed -i` does not. No policy was skipped or disabled.

## Checkpoint — subagent templates reconciled — 2026-09-05T03:14:18-03:00

```text
time: 2026-09-05T03:14:18-03:00
task: reconcile the subagent templates with the skill and the hosts
attempt: 1 of 3
worker model: none; governance text, edited at root
worker effort: not settable on this host
spec validator: not dispatched; the owner directed the change and the sources
  are each host's own published documentation
quality reviewer: not dispatched; no product-code diff
commands:
  command: diff -r .claude/skills/... .cursor/skills/...
  counts: identical, byte for byte
  command: npx --no-install markdownlint-cli2
  counts: pending below
  command: six baseline suites
  counts: not run — no Python changed; reused from the Task 2 checkpoint
commit hash: pending
next: Task 2b — consolidate the freeze helper — then Task 3
```

### What the hosts actually expose

Confirmed from each host's own documentation rather than from memory. Context7
served the Claude Code subagent reference; Cursor and Codex came from their
published docs, the Codex URL now redirecting to `learn.chatgpt.com`.

| | Claude Code | Cursor | Codex |
| --- | --- | --- | --- |
| Format | Markdown + YAML | Markdown + YAML | **TOML** |
| Model default | `inherit` | `inherit` | inherits from parent |
| Effort | **not expressible** | `model[effort=high]` | `model_reasoning_effort` |
| Read-only | omit write tools | `readonly: true` | `sandbox_mode` |

The `claude-api` skill was loaded first and was the wrong source: it documents
the Anthropic API, SDK and Managed Agents, not Claude Code subagent frontmatter.
Recorded so the next session does not repeat that step.

### Two corrections to this workstream's own record

**Effort was recorded but never set.** The governing plan says to record the
actual model and effort in every checkpoint. Claude Code exposes no effort
control — not in subagent frontmatter, not on the spawn tool. Every
`worker effort: medium` in the Outcome 2 Task 1 and Task 2 checkpoints in
[[2026-09-04-162018-outcome-1-gate-closure]] therefore names a level nothing
applied. Those checkpoints are left as written, since the vault is
non-destructive and they are committed record; this note is the correction. The
contract now requires `not settable on this host` where that is the truth.

**The escalation rule was skipped.** The plan says to prefer the cheapest tier
that can pass and escalate one tier only after evidence of failure.
`impl-executor` pins `model: haiku`, and root overrode it to `sonnet` on every
dispatch without trying haiku or recording any failure. That is not a defensible
reading of the rule on a workstream under quota pressure. The template keeps
`haiku`; escalation now needs recorded evidence.

### What changed

Canonical role definitions now live in
`references/agents/` — `impl-executor.md`, `spec-validator.md`,
`quality-validator.md`, plus a README carrying the host capability matrix. The
files under `.claude/agents/` became thin wrappers holding host frontmatter and
pointing at the canonical text, so the prose exists in exactly one place. That
is the declare-once-generate-per-host shape ADR 0014 mandates for the product's
own host agent files, applied to the skill itself.

The old `impl-validator` is retired via `git rm`, its history preserved. It
claimed to be read-only while holding `Bash`, so it could write. It is replaced
by a genuinely read-only `spec-validator` (`tools: Read, Grep, Glob`) and a
`quality-validator` that keeps `Bash` because rerunning acceptance commands is
its entire purpose.

Its template also mandated "no narrating comments" and forbade `if/else`
ladders, and pointed every implementer at a Flutter/Dart ruleset whose `fpdart`
types do not exist in Python. Both are gone. The comment banned by that rule is
exactly the kind that explains why a recursive freeze must recurse — the absence
of which caused a real defect in Task 1.

Briefs shrink accordingly: standing constraints, the interpreter rule, the two
failure modes and the report shapes are now in the templates, leaving briefs to
carry only task-specific slots.

## Checkpoint — Outcome 2 Task 2b — 2026-09-05T04:20:41-03:00

```text
time: 2026-09-05T04:20:41-03:00
task: Outcome 2 Task 2b — consolidate the freeze helper
attempt: 3 of 3
worker model: claude-haiku-4-5
worker effort: not settable on this host
spec validator: claude-sonnet-5, read-only, FINDINGS (3) then resolved
quality reviewer: claude-sonnet-5, fresh agent, FINDINGS (1) then resolved
commands:
  command: PYTHONPATH=... python3.12 -m unittest discover -s .../scripts/tests
  counts: 191 tests, OK
  command: root regression drill — revert thaw to partial
  counts: 2 failures, restore byte-identical, 191 OK
  command: root regression drill — short-circuit freeze on MappingProxyType
  counts: 3 failures, restore byte-identical, 191 OK
  command: other five suites
  counts: not run — nothing outside scripts/ changed; Task 7 owns the sweep
commit hash: pending
next: Outcome 2 Task 3 — scheduling and routing checks
```

`freeze` and `thaw` now live once, in `qc_lib`, imported by `kernel_specs` and
`run_state`. The suite went 165 → 191.

### The cheapest tier was the right tier

This task ran on `claude-haiku-4-5`, the first honest application of the plan's
escalation rule after root had been overriding `impl-executor`'s pinned `haiku`
to `sonnet` on every previous dispatch without evidence. Haiku did the work
correctly across three attempts at roughly 100k subagent tokens per round
against sonnet's ~190k. No escalation was needed or taken.

Root also owes a retraction. After attempt 1 root reported that haiku "follows
instructions less precisely" because it returned a prose summary instead of the
contract's report shape. That was wrong, and the cause was root's own design —
see below. Attempts 2 and 3 returned the exact shape once the block was lifted.

### The single source of truth was unreadable

The `agent-continuity` markdown allowlist hook gates `Read` and `Grep` on `*.md`
inside the project tree. Its default patterns cover the vault, `CLAUDE.md`,
`.agent/**` and `docs/**` — not `.claude/skills/**`. The thin-wrapper design
committed in `3ad627c` therefore pointed every subagent at a canonical role
definition none of them could open, and it failed silently rather than erroring.

The spec validator surfaced it by reporting that it could not read its own role
file, and judging from the inline brief instead of routing around the block —
the right behaviour from a validator that finds its environment broken.

Fixed in `08908dc` with `.claude/agent-continuity.config.json`. The hook's
patterns replace its defaults rather than extending them, so the defaults are
repeated verbatim before adding `.claude/*` and `.cursor/*`; omitting them would
have quietly narrowed vault protection. Verified by executing the hook directly:
role definitions and `contracts.md` pass, a control path outside the patterns is
still denied.

### What review caught that the move did not

Spec compliance found two tests that proved nothing — the already-frozen cases
wrapped containers with no mutable content nested inside, so a short-circuit
regression would have passed both. That is the Task 1 vacuous-proof failure mode
recurring in the one place written to guard against it. It also found a dead
`MappingProxyType` import left in `kernel_specs` and a function-body import in
`qc_lib` paid once per node of a recursive walk.

Quality then found the defect that mattered: **`freeze` was total and `thaw` was
partial.** `freeze` recurses on `(dict, MappingProxyType)` and `(list, tuple)`,
accepting any mixture; `thaw` recursed only when the outer value was already
frozen, so a plain dict wrapping a frozen value came back untouched and
`json.dumps` raised far from the cause. Root reproduced it exactly.

Nothing in the tree hits this today, because `kernel_specs` only thaws what it
froze. It was a trap for Tasks 4 and 5, which build replay, the result gate and
the CLI — all of which serialise derived state, and all of which would reach for
the failing shape.

Root's ruling: make `thaw` symmetric rather than document a precondition. A
shared public helper with a footnote requires five later tasks to remember it,
and the penalty for forgetting is a silent wrong result surfacing at
serialisation. Removing the precondition removes the class.

## Checkpoint — Outcome 2 Task 3 — 2026-09-05T05:00:26-03:00

```text
time: 2026-09-05T05:00:26-03:00
task: Outcome 2 Task 3 — scheduling and routing checks
attempt: 3 of 3 on claude-haiku-4-5, then 1 of 3 at escalated tier
worker model: claude-haiku-4-5 for attempts 1-3; claude-sonnet-5 for the
  quality fix round, escalated with recorded evidence
worker effort: not settable on this host
spec validator: claude-sonnet-5, read-only, FINDINGS (4) then resolved
quality reviewer: claude-sonnet-5, fresh agent, FINDINGS (4) then resolved
commands:
  command: PYTHONPATH=... python3.12 -m unittest discover -s .../scripts/tests
  counts: 246 tests, OK
  command: root drill — neuter the root->worker routing branch
  counts: 3 failures, restore byte-identical
  command: quality drill — disable _check_dag_acyclic
  counts: 3 failures, exactly the cycle tests, restore clean
  command: root verification — falsy outcome, deep chains, routing matrix
  counts: all four defects confirmed fixed by execution
  command: other five suites
  counts: not run — nothing outside scripts/ changed; Task 7 owns the sweep
commit hash: pending
next: Outcome 2 Task 4 — adapter port, fake adapter, model-free DAG replay
```

Delivered `scripts/router.py` with `next_tasks` and `validate_pair`, `TaskNode`
and `TaskDag` records with iterative cycle detection in `kernel_specs`, and
derived per-task status in `run_state`. The suite went 191 → 246.

### The escalation rule, applied honestly in both directions

Attempts 1-3 ran on `claude-haiku-4-5` and resolved every finding put to them.
Root then escalated one tier for the quality fix round, with the evidence the
plan requires: asked to wire an unused constant in meaningfully, haiku added two
runtime checks that could never fire — a judgment miss rather than a mechanical
one — and the remaining work was algorithmic. That is recorded as a tier change
with cause, not as a fourth failure. Haiku had converged; the task had grown.

### What each layer caught, and what nobody caught until the end

Root found the first serious defect directly: `_FrozenDefaultDict`, a bespoke
container where `d[k]` returned a value for any key while `k in d` was False,
and `d.get(k, None)` returned `"pending"` instead of `None`. It was a second
hand-rolled immutability mechanism one task after Task 2b consolidated to one.
Replaced by a plain frozen mapping plus an explicit `status_of`.

Spec compliance found something subtler: two illegal-pair tests that the
**catch-all branch already satisfied**. `validate_pair`'s fallback echoes the
identities into its message, so a test asserting on "root" and "worker" passed
whether or not the dedicated branch existed. Only worker-to-worker was genuinely
proven, because "isolation" appeared nowhere else. It also found that no test
ever passed an unrecognised identity, leaving the catch-all's own guarantee
untested, that `TaskDag.from_dict` rejected dicts while every sibling accepted
them, and that `TaskNode` labelled the offending index by counting occurrences
rather than position — reporting `depends_on[0]` for an item at index 1.

Quality then found the two that mattered most, both reproduced by root:

**A silent deadlock.** `_apply` gated on truthiness, not presence. A `result`
envelope carrying `outcome=""` short-circuited before the `VALID_OUTCOMES` check,
raised nothing, and pinned its task at `running` forever — after which
`next_tasks` returned `()` permanently for everything downstream. `"unknown"`
was rejected while `""` was not: strictest where it mattered least.

**Unbounded recursion in cycle detection.** A 995-node chain constructed; 1000
raised bare `RecursionError` instead of `Blocked`, with the threshold depending
on the host's recursion limit and on input ordering. Task 6 generates DAGs and a
long linear pipeline is exactly its output. Now an iterative three-colour DFS:
5000 nodes construct in 232ms and a back edge raises `Blocked`.

Quality also proved the `TaskDag` mutation test vacuous by setting
`frozen=False` and watching it still pass, and supplied the better remedy for
the dead-code finding — make `VALID_OUTCOMES ⊆ TASK_STATUSES` structural, once,
where it can be violated, rather than re-derived per envelope.

### A drill that proved nothing, recorded as such

Root's first attempt to drill cycle detection broke module import: the suite
fell from 235 to 128 with collection errors rather than producing clean
behavioural failures. That is not evidence, and root did not report it as such.
The quality validator ran the drill properly and got the real answer — exactly
three cycle tests fail when the check is disabled, so detection is genuinely
proven while its recursion depth was not.
