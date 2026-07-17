---
date: 2026-07-17
type: session
status: closed
---

# Session — Agent Skills standards research and Aplicatudo deployment plan

Previous Session: [[2026-07-17-010620-eval-parity-benchmark]]
Next Session: [[2026-07-17-111000-oqc-2-0-0-release]]

## Scope

1. Investigate Agent Skills / OpenSkills installation patterns via Context7.
2. Record binding decision: **full-plugin install only** (no skill-only tier).
3. Save analysis to vault and produce a step-by-step Aplicatudo monorepo deployment guide.

## Implementation Checkpoint - 2026-07-17T07:05-03:00

**Scope:** Research synthesis and deployment planning — no code changes.

**Changes:**
- Added [[2026-07-17-agent-skills-standards-analysis]] — Context7-backed standards report with full-plugin-only policy.
- Added [[2026-07-17-aplicatudo-first-deployment-plan]] — six-phase Cursor deployment guide targeting `/home/corporaterick/Documents/Projects/aplicatudo-monorepo`.
- Closed [[2026-07-17-010620-eval-parity-benchmark]]; opened this session.

**Validation:** Live monorepo tree verified (legacy e2e skills present, stale checkpoint at `projects/aplicatudo/.agents/skills/e2e-quality-control/state/`). Installed Cursor plugin confirmed at 1.1.0 — plan documents refresh to 1.2.0 before first run.

**Next:** Execute Phase 0–2 of the deployment plan in Cursor against `login.flow.yaml`.

## Implementation Checkpoint - 2026-07-17T07:16-03:00

**Scope:** Correct document roles — reports vs operator protocol.

**Changes:**
- Restored `Agent_Reports/2026-07-17-agent-skills-standards-analysis.md` to analytical report voice.
- Restored `Agent_Reports/2026-07-17-aplicatudo-first-deployment-plan.md` as deployment plan (objective, context, risks, success criteria).
- Added `Architecture/Protocols/run-oqc-aplicatudo-cursor.md` — operator runbook with execution steps only.

**Validation:** Reports analyze and plan; protocol carries imperative instructions.

## Implementation Checkpoint - 2026-07-17T07:42-03:00

**Scope:** Publish Aplicatudo e2e guided-upgrade Agent prompt.

**Changes:**
- Added `Architecture/Protocols/Upgrade Aplicatudo E2E Workflow Prompt.md` (`isolated-three-agent`, `in-place`).
- Linked it from the Aplicatudo deployment plan execution section.

**Validation:** User approved publish (`proceed`).

## Pivot - 2026-07-17T11:10-03:00

Closing this session. Standards research and deployment plan are recorded;
implementation of the 2.0.0 breaking topology change and Claude marketplace
adapter continues in [[2026-07-17-111000-oqc-2-0-0-release]].

