---
date: 2026-09-02
timestamp: 2026-09-02T21:20:24-03:00
closed: 2026-09-02T23:42:25-03:00
type: session
status: closed
branch: feature/4-0-0-return-to-intention
next: "[[2026-09-04-032820-architecture-realignment]]"
---

# Session — Implement 4.0.0 as an orchestration

Previous Session: [[2026-09-02-094852-project-overview]]
Next Session: [[2026-09-04-032820-architecture-realignment]]

## Bootstrap

- **Timestamp:** 2026-09-02T21:20:24-03:00
- **Branch:** `feature/4-0-0-return-to-intention`, cut from `main` at
  `f34404d`. The repository policy hook blocks commits on `main`, so the
  plan's "one commit per phase" lands on this ticket branch; merging back to
  `main` is an owner decision at P8.
- **Carried forward:** Six ledger documents from the reconciliation
  workstream were uncommitted at handoff: the drift report, the
  reconciliation, the worker-model brief, ADR 0013, the 4.0.0 plan, the
  ledger and the handoff. ADR 0005 item 3 open. 3.2.0 shipped locally.
- **Current intent:** Execute
  [[2026-09-02-handoff-implementation-orchestration]] — run the 4.0.0 plan as
  an orchestration: root holds the plan and delegates each step to one
  executor and one read-only validator, filling
  [[2026-09-02-return-to-intention-ledger]] one row per step.
- **Why a new session file:** the previous note asked the next agent to
  continue it, but the workspace write gate requires an open session younger
  than eight hours whose branch matches the workspace. That note is closed
  and linked forward; its handoff content is carried above.

## Baseline — offline suites at handoff

`PYTHONPATH=orchestration-quality-control/scripts:orchestration-quality-control/scripts/tests`
is required for the scripts suite; the handoff's `T_scripts` shorthand omits
it and every brief restores it.

| Suite | Tests |
| --- | --- |
| scripts | 91 |
| claude hooks | 8 |
| claude | 6 |
| codex | 36 |
| cursor | 19 |
| eval-harness | 17 |
| **total** | **177 OK** |

## Roles for this session

Host is Claude Code, not Cursor, so the handoff's Cursor slugs take the
nearest model in each tier and the definitions live in `.claude/agents/`
(globally gitignored — session tooling, not product). Root `opus`, executor
`haiku`, validator `sonnet` spawned as the host's read-only agent type so
`readonly: true` is mechanical. Recorded in the ledger header.

## Gate — Phase 0 freeze and baseline — 2026-09-02T22:15-03:00

PASS. Ledger rows 0.1–0.4. Tag `v3.2.0-final` is at `f34404d`, an ancestor
of HEAD, and touches no product code. `measure_package.py` reproduces
131 / 3694 / 181 / 18 / 15 / 6; `measure_run.py` aggregated over the 40
workspace runs reproduces 15–20 packaged reads (median 17) over the 7 of 30
with-skill runs whose transcript lists files, and 0–13 state files
(median 3). All 17 budget rows are now either script output or explicitly
attributed to `timing.json`, `benchmark.json`, unittest, a hand count, or
"not available in 3.2.0"; the validator reproduced the 570 s median and the
95.8% pass rate independently from the raw artifacts. Nothing under
`orchestration-quality-control/` changed. Six suites green: 91+8+6+36+19+32
= 192 (177 at the tag, plus the 15 new measurement tests).

## Checkpoint — closed for a development break — 2026-09-02T23:42:25-03:00

**Reason:** development break; resume on the next session.

**Checkpoint commit:** `87ba5dc` (`87ba5dcff3f7fad4ae7d9b58755c9aded751c7f6`)
— `feat(4.0.0): pin the interview contract (phase 1)` on
`feature/4-0-0-return-to-intention`. Working tree was clean after that
commit, before this session-close note.

**What that commit holds:** ADR 0013 Accepted plus amendments on 0005 / 0008
/ 0010 / 0012; `input.schema.json` `operation ∈ {qc, upgrade, author}` with
`language` and `decision`; interview wording in SKILL.md and READMEs; core
and author evals rewritten; adapter `VERSION = "4.0.0-dev"`. Ledger rows
1.1–1.4 point at `87ba5dc`.

**Resume here:**

1. Confirm step 1.5 (`VERSION = "4.0.0-dev"`). The adapter strings already
   landed in `87ba5dc`; the ledger row and Phase 1 exit gate are still
   `pending`.
2. Then Phase 2 — `oqc.py` engine (`lint` · `mail` · `next` · `compile` ·
   `gate`), per [[2026-09-02-return-to-intention-ledger]].

**Cursor orchestrator contract (checked this session, not yet coded):**
`readonly: true` is wrong for the Orchestrator. Under ADR 0013 the role
only mutates via `oqc.py` (`mail send`, `compile`, `next`/checkpoint,
`gate`). Put `readonly: true` on the Validator only. `model` must not be
`inherit`; Cursor orchestrator is `grok-4.6[effort=high]`.
`oqc_cursor_upgrade_orchestrator.md` is deleted in 4.0.0.
