---
title: Final whole-ticket architecture review
date: 2026-09-04
type: review
status: complete
range: e211e45..d184c77
---

# Final whole-ticket architecture review

## Verdict

**Needs fixes; not ready to hand off.** The plan preserves the owner's product
purpose, the fixed-control-plane/generated-workflow distinction, deterministic
kernel authority, vendor-neutral core, ADR/paused-plan disposition, and a
compact executable-first shape. However, its first real run is ordered before
the adapter needed to perform it, and its exit gates do not yet prove that the
workflow is actually generated or that recovery and root relay behavior are
engine-controlled.

Counts: **0 Critical · 3 Important · 2 Minor**.

## Review basis

- Reviewed the complete documentation-only range `e211e45..d184c77` from the
  supplied review package and confirmed HEAD `d184c77fbb2e44e315d52110e188a225f0b01790`.
- Read the active ticket, architecture ruling, all three raw discovery reports,
  ADR 0013, the paused 4.0.0 plan and ledger, the new master plan, and the new
  session ledger.
- Verified the load-bearing local absent-engine claim with one focused package
  script/source search: no kernel front door, mailbox, reducer, compiler, or
  gate implementation is present; only eval prose mentions the planned
  mailbox commands.
- `git diff --check e211e45 d184c77` passed. The only current untracked paths
  are the two user-owned paths already preserved by the session ledger.
- The plan and ticket do not link to ignored `.superpowers` scratch. External
  sources are official or commit-pinned as required; no broad web refresh was
  necessary for this review.

- **Source note on the architecture ruling (recorded 2026-09-04).** This review
  cites `architecture-ruling.md` at three points. That file is not in the
  repository and never was: root synthesized it into the ignored subagent
  workspace
  `.superpowers/sdd/refactor-align-the-architecture-with-original-design/`,
  whose `.superpowers/sdd/.gitignore` is `*`, placing it outside versioned state
  by design. That workspace was removed once its rulings were captured, and its
  transient raw reports are not recoverable except by rerunning
  discovery/review; the reviewed conclusions remain versioned in the master
  plan, the ticket, and the
  [architecture realignment ledger](../AI_Codex/Agent_Sessions/2026-09-04-032820-architecture-realignment.md)
  at Checkpoint 4. The three citations are therefore preserved as plain,
  non-clickable source labels rather than retargeted to an inferred file, which
  would create false provenance. The twelve other local links were corrected
  from `../../../AI_Codex/` to `../AI_Codex/`, the depth that resolves from
  `docs/`.

## Critical

None.

## Important

### 1. The real orchestration slice is scheduled before a spawn adapter exists

Evidence:

- The kernel outcome ends with only a CLI/library boundary and does not include
  the ruling's narrow adapter port
  ([master plan:49-53](../AI_Codex/Implementation_Plans/2026-09-04-original-design-realignment-master-plan.md)).
- Outcome 3 nevertheless requires root to spawn one Orchestrator and complete a
  real workflow
  ([master plan:55-59](../AI_Codex/Implementation_Plans/2026-09-04-original-design-realignment-master-plan.md)).
- The plan does not define an adapter port or complete a first host until
  outcome 4
  ([master plan:61-65](../AI_Codex/Implementation_Plans/2026-09-04-original-design-realignment-master-plan.md)).
- The ruling includes spawn, status, question relay, and hooks in the minimum
  kernel-facing port
  (architecture ruling:47-64).

As written, outcome 3 can pass only by calling a host directly, which violates
the adapter boundary, or by using a fake, which is not the required real slice.

Fix: put the port and fake implementation in outcome 2, then put the smallest
first-host adapter and its real spawn in outcome 3. Keep outcome 4 for generated
host configuration, enforcement hardening, fallback disclosure, and mapping to
the remaining hosts. This preserves five outcomes and the one-host-first rule.

### 2. The gates do not prove that discovery/interview generated the workflow

Evidence:

- The defining distinction says discovery generates the task DAG, roles,
  capabilities, tiers, tools, and schemas
  ([master plan:27](../AI_Codex/Implementation_Plans/2026-09-04-original-design-realignment-master-plan.md));
  the ticket makes this the product purpose and principle
  ([ticket:13-23](../AI_Codex/Tickets/Active/refactor-align-the-architecture-with-original-design.md)).
- The kernel exit gate proves only a two-task DAG supplied as accepted input
  ([master plan:49-53](../AI_Codex/Implementation_Plans/2026-09-04-original-design-realignment-master-plan.md)).
- Outcome 3 names dynamic `AgentSpec` generation, but neither names generated
  DAG construction nor gates provenance from discovery/interview input; its
  evidence checks only identities, mailbox sequence, hashes, and handoff
  ([master plan:55-59](../AI_Codex/Implementation_Plans/2026-09-04-original-design-realignment-master-plan.md)).

The plan could therefore pass with a fixed two-task DAG and hard-coded roles,
recreating the fixed-output failure under different names.

Fix: require a deterministic validation/compilation boundary from accepted
discovery/interview decisions to a `RunSpec`, generated DAG, and generated
`AgentSpec` records. Add a small contract fixture showing that a relevant input
change changes the emitted DAG or agent manifest, and require the real run to
use the emitted spec. This does not require a second live run.

### 3. Recovery proof stops before the exhausted/reply/resume lifecycle

Evidence:

- Outcome 2 proves one injected failure followed by completion, but not
  classification, critique carry-forward, maximum-attempt blocking, or replay
  of that exhausted path
  ([master plan:49-53](../AI_Codex/Implementation_Plans/2026-09-04-original-design-realignment-master-plan.md)).
- Outcome 3 requires a blocked/user-input handoff only "when required" and says
  root receives state/result envelopes; it does not require the corresponding
  engine-declared question, root reply relay, legal reply transition, or resume
  ([master plan:55-59](../AI_Codex/Implementation_Plans/2026-09-04-original-design-realignment-master-plan.md)).
- The ruling requires failure classification, retry transition, critique
  carry-forward, escalation, maximum attempts, blocked handoff, and an adapter
  question-relay boundary
  (architecture ruling:33-45,
  architecture ruling:47-69).

This leaves the central self-healing and passive-root promise unproven. A run
could ask root directly, lose critiques, or become irrecoverably blocked while
still satisfying the written exits.

Fix: extend the model-free reducer/replay proof with two compact paths: a
recoverable classified failure that carries critique into the next attempt,
and an exhausted retry that reaches `blocked` or `awaiting-user-input`. In the
real slice, capture that root stays idle until the engine emits the allowed
state, relays a schema-valid answer through the adapter, and the reducer either
resumes or finishes blocked. Reject direct agent state mutation and illegal
sender/recipient transitions in table tests.

## Minor

### 1. The target architecture is phrased as current installed behavior

[Master plan:14-16](../AI_Codex/Implementation_Plans/2026-09-04-original-design-realignment-master-plan.md)
says the product "installs as" the new authoring/execution system, while the
same plan correctly records that the engine is absent
([master plan:29-39](../AI_Codex/Implementation_Plans/2026-09-04-original-design-realignment-master-plan.md)).
The proposed-plan context makes the intent inferable, but this is still a
present-tense claim about unavailable behavior.

Fix: rename the section to `Target product boundary` and use future/required
language such as "The product will install as" or "The product must expose."

### 2. The ticket duplicates its primary acceptance criterion

[Ticket:29-34](../AI_Codex/Tickets/Active/refactor-align-the-architecture-with-original-design.md)
states the five outcomes/fixed-vs-generated/source requirement twice in
successive bullets. This slightly weakens an otherwise concise ticket and can
create ambiguity about whether "required sources" and "required durable and
external references" are separate gates.

Fix: merge the first two bullets into one criterion retaining five outcomes,
exit evidence, non-goals, the fixed/generated distinction, and durable/external
sources.

## Ready-to-hand-off decision

**No.** Address the three Important findings and re-review the amended plan and
ledger. The Minor items may be fixed in the same documentation commit; neither
requires expanding ticket scope or implementing the future kernel in this
planning ticket.
