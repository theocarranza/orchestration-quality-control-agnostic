---
date: 2026-09-04
timestamp: 2026-09-04T03:28:20-03:00
closed: null
type: session
status: active
branch: feature/4-0-0-return-to-intention
previous: "[[2026-09-02-212024-implement-4-0-0-orchestration]]"
next: null
ticket: "[[refactor-align-the-architecture-with-original-design]]"
---

# Session — Architecture realignment with the original design

Previous Session: [[2026-09-02-212024-implement-4-0-0-orchestration]]
Next Session: (none yet — this session is active)

## Mandate

Architect-led execution of
[[refactor-align-the-architecture-with-original-design]]: delegate bounded
discovery, identify drift from the original engine-first and isolated-agent
design, and produce a short master plan that governs later implementation.

## Checkpoint 1 — bootstrap and execution boundaries — 2026-09-04T03:28:20-03:00

- Branch: `feature/4-0-0-return-to-intention` in the primary checkout.
- Pre-existing untracked paths preserved as user-owned inputs:
  `.claude/agents/`,
  `AI_Codex/Tickets/Active/refactor-align-the-architecture-with-original-design.md`,
  and `AI_Codex_OrchestratorQcPlugin/`.
- Ruling: work in place on the existing ticket branch. A fresh worktree would
  omit the untracked ticket and research notes; copying them would create a
  second, ambiguous source of truth. Cost if wrong: this session shares the
  user's checkout, so every commit must remain narrowly staged and reversible.
- Model routing: root retains architectural judgment; Terra or Luna returns
  raw discovery evidence; implementation/drafting uses the least-capable
  available suitable worker. Official OpenAI documentation describes GPT-5.4
  Mini as intended for coding and subagents, but that exact spawn preset is not
  exposed in this session, so dispatches must use an allowed equivalent and
  name both model and effort explicitly.
- Quota guard: the available goal/usage interface returned no active goal,
  remaining-token budget, or 5-hour/7-day percentages. The session cannot
  mechanically observe the requested thresholds; any host-supplied warning or
  user-reported threshold will trigger an immediate handoff and standby.
- Scope ruling: this ticket's first deliverable is analysis plus a concise
  master plan. The paused 4.0.0 implementation ledger is evidence, not the plan
  to resume before this realignment decision exists. Cost if wrong: Phase 2+
  remains paused until the owner accepts or executes the new master plan.
- Ownership interruption: staging initially failed because `.git/objects` and
  the predecessor note were owned by another filesystem UID. The owner repaired
  both paths during this checkpoint; the predecessor now links forward and
  commit-backed checkpoints can resume.

## Checkpoint 2 — fresh offline baseline — 2026-09-04T03:33:40-03:00

PASS. The six recorded suites ran from `562e8f9` with the scripts suite's
required `PYTHONPATH`; 98 scripts + 8 Claude hooks + 6 Claude adapter + 36
Codex adapter + 19 Cursor adapter + 32 eval-harness = **199 tests, 0
failures**. Cursor's installer refusal messages are expected assertions in
passing tests. Product code was unchanged.

## Checkpoint 3 — delegated discovery evidence — 2026-09-04T03:36:47-03:00

PASS. Three isolated read-only discovery briefs returned raw evidence; root
has not delegated the architectural decision.

| Brief | Model | Evidence captured |
| --- | --- | --- |
| `.superpowers/sdd/refactor-align-the-architecture-with-original-design/discovery-local.md` | `gpt-5.6-luna`, medium | Current package, executable scripts, adapters, hooks, tests, and plan-only gaps |
| `.superpowers/sdd/refactor-align-the-architecture-with-original-design/discovery-ancestors.md` | `gpt-5.6-terra`, medium | Both referenced repositories pinned to commits; documented claims separated from code-confirmed behavior and stubs |
| `.superpowers/sdd/refactor-align-the-architecture-with-original-design/discovery-host-surfaces.md` | `gpt-5.6-luna`, low | Local Claude/Cursor/Codex surfaces plus Context7 retrieval for current Claude and Cursor agent configuration |

The shared raw fact is that the local product claims the planned `oqc.py`
engine, envelope mailbox, reducer/compiler/gate, circuit breaker, and
three-template topology, but those components are not executable in the
current tree. The ancestors provide useful mechanisms, not a complete source
to copy: the E2E runtime leaves worker outcomes disconnected and ships stub
hooks, while the hierarchical runtime has a working reducer/stream but no
persisted mailbox and retains concrete workflow/provider coupling.

## Checkpoint 4 — root architecture ruling — 2026-09-04T03:39:00-03:00

Root synthesized the evidence into
`.superpowers/sdd/refactor-align-the-architecture-with-original-design/architecture-ruling.md`.

- Ruling: the fixed topology is the product control plane — root/interviewer →
  one Orchestrator → isolated execution agents — while each authored
  workflow's task graph, roles, schemas, tools, and model tiers are generated.
  Cost if wrong: the product may permit more workflow variation than a fixed
  Validator/Remediator pattern would.
- Ruling: deterministic code owns mailbox/event validation, immutable state
  reduction, next-step routing, brief compilation, result gates, retry/block,
  and replay. Agents judge and author only. Cost if wrong: the kernel becomes a
  larger compatibility boundary across adapters.
- Ruling: workflow-document QC becomes an internal or optional capability, not
  the primary product identity. Cost if wrong: existing QC-focused users need
  an explicit compatibility path.
- Ruling: the existing eight-phase 4.0.0 plan is evidence but no longer the
  governing build order. The replacement proves one model-free vertical slice
  and one real host slice before broad migration, cleanup, or benchmarking.
  Cost if wrong: some already-planned inventory and evaluation work will be
  deferred or discarded.
- Ruling: core agent manifests use capabilities and model/reasoning tiers;
  adapters map them to host-native settings and disclose fallbacks. Cost if
  wrong: adapters carry ongoing model-catalog maintenance.

## Checkpoint 5 — master-plan draft — 2026-09-04T03:44:29-03:00

`gpt-5.6-luna` at medium effort completed the bounded drafting task. It
created
[[../Implementation_Plans/2026-09-04-original-design-realignment-master-plan]]
(87 lines) and reformatted
[[../Tickets/Active/refactor-align-the-architecture-with-original-design]]
(43 lines). Its report records `git diff --check` PASS and 14 local links
resolved with 0 missing targets. This checkpoint records a reviewable draft,
not architectural approval; independent review follows from this commit.

## Checkpoint 6 — draft fix round 1 — 2026-09-04T03:49:51-03:00

Task review at `1be3c8b` returned spec FAIL / quality needs fixes: 0 Critical,
3 Important. Root accepted the missing mechanical truth gate and weak host-doc
sources, clarified the adapter-smoke sequence, and added three architecture
corrections: remove links to ignored review scratch, restore this ticket's
planning-only acceptance scope, and disposition ADR 0013's conflicting fixed
worker roles. The original drafting agent amended its two owned artifacts;
`git diff --check` passes, the plan is 85 lines, the ticket is 42 lines, and
11 local links resolve. This commit is the fix candidate for scoped re-review.

## Checkpoint 7 — drafting task complete — 2026-09-04T03:51:24-03:00

Scoped re-review of `1be3c8b..71b6624` resolved all six findings: 6 addressed,
0 open, 0 new breakage. Root separately fetched the current official Claude,
Cursor, and Codex subagent pages named by the plan. Task complete across
`1be3c8b` and `71b6624`; review clean, with no deferred minors or parked
findings.

## Checkpoint 8 — final-review fix wave — 2026-09-04T03:57:57-03:00

The whole-ticket architecture review of `e211e45..d184c77` returned 0
Critical, 3 Important, and 2 Minor findings. Root accepted all five. The
single authorized fix wave now places the adapter port/fake before the real
spawn, updates the plan to require proof that discovery/interview inputs
generate the DAG and agent manifests, and requires proof of recoverable and
exhausted retry plus passive-root reply relay. It also changes target behavior
to future tense and deduplicates ticket acceptance. Worker
checks pass: `git diff --check`, 11/11 local links, plan 87 lines, ticket 41
lines. This commit is the candidate for the one scoped final re-review.

## Checkpoint 9 — final re-review adjudication — 2026-09-04T04:00:30-03:00

Scoped re-review resolved the five original findings (5 addressed, 0 open)
and found 0 Critical, 1 new Important, and 1 new Minor. The Important finding
is real and load-bearing: the expanded failure matrix dropped the explicit
requirement that the recoverable two-task dependent DAG reaches `completed`.
The Minor correctly notes that Checkpoint 8 says planned behavior was proved.

Ruling: allow one narrow textual correction beyond the final-review workflow's
usual single fix wave — the owner explicitly required continuous execution,
and parking a known gap in the kernel's defining vertical-slice gate would
defeat the ticket. Cost if wrong: one extra low-cost worker turn and narrow
review are spent instead of surfacing the residual at handoff.

## Checkpoint 10 — dependent-DAG proof restored — 2026-09-04T04:01:42-03:00

The low-cost drafting worker restored the exact model-free completion path:
the emitted two-task dependent DAG carries critique into a passing retry, runs
the dependent task, and reaches `completed`; exhausted retry remains a separate
blocked/awaiting-user-input fixture. Root corrected Checkpoint 8 to describe
future proof requirements rather than claim absent implementation. `git diff
--check` passes and the plan remains 87 lines. Candidate ready for narrow
textual re-review.
