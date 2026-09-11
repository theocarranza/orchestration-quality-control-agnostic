---
title: 4.0.0 implementation ledger
date: 2026-09-02
handoff: "[[2026-09-02-handoff-implementation-orchestration]]"
plan: "[[2026-09-02-return-to-intention-4-0-0]]"
---

# 4.0.0 implementation ledger

One row per step. The root agent fills columns; nobody else writes here.
Status vocabulary: `pending` · `in progress` · `done <timestamp>` ·
`blocked <timestamp>` · `skipped: <owner reason>`.

Model substitutions (if a configured ID was not accepted by the host):

- **Host is Claude Code, not Cursor.** The handoff names Cursor slugs; the
  subagent definitions therefore live in `.claude/agents/` and take the
  nearest model in each tier, never `inherit`.
- Root: `opus`. Executor `impl-executor`: `haiku` (tier match for
  Composer 2.5 standard — cheapest capable coding model on this host).
  Validator `impl-validator`: `sonnet` (mid-tier, distinct from executor and
  from root, tier match for GPT-5.5).
- The validator is spawned as the host's read-only agent type, which has no
  Edit/Write/NotebookEdit tool at all, so `readonly: true` is mechanical
  rather than prompted.
- Escalation if a role's model tier — not the brief — causes repeated
  failure: executor `haiku` → `sonnet`, and the validator then moves
  `sonnet` → `fable` so the three stay distinct. Never `inherit`.
- `T_scripts` in every brief is prefixed
  `PYTHONPATH=orchestration-quality-control/scripts:orchestration-quality-control/scripts/tests`;
  the handoff's shorthand omits it and the suite errors without it.

## Phase 0 — freeze and baseline

| Step | Deliverable                             | Model | Attempts | Verdict          | Decision                                                                                                                                                                                       | Status                | Commit  |
| ---- | --------------------------------------- | ----- | -------- | ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------- | ------- |
| 0.1  | Tag `v3.2.0-final` (root + owner)       | —     | —        | tag present      | approved — root action                                                                                                                                                                         | done 2026-09-02 21:24 | 525e398 |
| 0.2  | `measure_package.py` + test             | haiku | 3        | PASS (attempt 3) | approved — attempts 1-2 failed on shared-state mutation and a non-discriminating fixture                                                                                                       | done 2026-09-02 21:40 | 9bf7eae |
| 0.3  | `measure_run.py` + test                 | haiku | 2        | PASS (attempt 2) | approved — attempt 1 passed validation but crashed on two author runs with a prose line under '## Files read'; attempt 2 made the existence test total and dropped the literal exclusions (F6) | done 2026-09-02 22:02 | 9bf7eae |
| 0.4  | Plan "3.2.0" column filled from scripts | haiku | 1        | PASS (attempt 1) | approved — executor returned blocked on a defective acceptance command in the brief (unscoped `git diff --stat`); root rescoped the check, edits were already correct                          | done 2026-09-02 22:12 | 9bf7eae |
| gate | Phase 0 exit gate                       | —     |          | PASS             | approved — committed                                                                                                                                                                           | done 2026-09-02 22:16 | 9bf7eae |

## Phase 1 — contract truth

| Step | Deliverable                                                                        | Executor model | Attempts | Validator verdict | Root decision                                                                                                                                                                                                            | Status                | Commit                     |
| ---- | ---------------------------------------------------------------------------------- | -------------- | -------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------- | -------------------------- |
| 1.1  | ADR status lines and amendments (0013, 0008, 0010, 0012, 0005)                     | haiku          | 1        | PASS (attempt 1)  | approved — 33 insertions / 2 deletions across the five ADRs, no prose rewritten                                                                                                                                          | done 2026-09-02 22:24 | 87ba5dc |
| 1.2  | `input.schema.json` three operations, `decision`, `language`, `stop_after_prepare` | haiku          | 1        | PASS (attempt 1)  | approved — enum pinned exactly, conditional reasoned through as non-inert, 98 tests                                                                                                                                      | done 2026-09-02 22:31 | 87ba5dc |
| 1.3  | SKILL.md + READMEs: interview statement replaces approval wording                  | haiku          | 1        | PASS (attempt 1)  | approved — gate returns 0; `references/rules/` W11/O9 excluded as rule content (plan: new rule content out of scope). Carried to 6.1/6.2: both READMEs' sequence diagrams and README.md:161 still show the two-call gate | done 2026-09-02 22:45 | 87ba5dc |
| 1.4  | Core and author `evals.json` rewritten                                             | haiku          | 1        | PASS (attempt 1)  | approved — all six prompts and every m-assertion matched the brief character for character; validator confirmed each m-assertion is mechanically decidable                                                               | done 2026-09-02 22:58 | 87ba5dc |
| 1.5  | `VERSION = "4.0.0-dev"`                                                            |                |          |                   |                                                                                                                                                                                                                          | pending               |                            |
| gate | Phase 1 exit gate                                                                  | —              |          |                   |                                                                                                                                                                                                                          | pending               |                            |

## Phase 2 — the engine

| Step | Deliverable                                     | Executor model | Attempts | Validator verdict | Root decision | Status  | Commit |
| ---- | ----------------------------------------------- | -------------- | -------- | ----------------- | ------------- | ------- | ------ |
| 2.1  | `lint_rules.py` + tests + expected fixtures     |                |          |                   |               | pending |        |
| 2.2  | `envelope.schema.json` + schema test            |                |          |                   |               | pending |        |
| 2.3  | `mailbox.py` send / read / verify + tests       |                |          |                   |               | pending |        |
| 2.4  | `mailbox.py` reduce / next / `--replay` + tests |                |          |                   |               | pending |        |
| 2.5  | `compile_prompt.py` + prompt bodies + tests     |                |          |                   |               | pending |        |
| 2.6  | `gate.py` + tests                               |                |          |                   |               | pending |        |
| 2.7  | `oqc.py` front door + tests                     |                |          |                   |               | pending |        |
| 2.8  | `checkpoint_state.py` `created_at`, `run_type`  |                |          |                   |               | pending |        |
| 2.9  | End-to-end fixture test; no `input(`            |                |          |                   |               | pending |        |
| gate | Phase 2 exit gate                               | —              |          |                   |               | pending |        |

## Phase 3 — three templates

| Step | Deliverable                                                                 | Executor model | Attempts | Validator verdict | Root decision | Status  | Commit |
| ---- | --------------------------------------------------------------------------- | -------------- | -------- | ----------------- | ------------- | ------- | ------ |
| 3.1  | `templates/orchestrator.md`                                                 |                |          |                   |               | pending |        |
| 3.2  | `templates/validator.md`, `templates/remediator.md`                         |                |          |                   |               | pending |        |
| 3.3  | Script merges (`interview`, `apply_preview`, `findings_lib`, `upgrade_lib`) |                |          |                   |               | pending |        |
| 3.4  | `rules/` with `## Lint-owned`; `report-style.md`                            |                |          |                   |               | pending |        |
| 3.5  | `schemas/`, `defaults/` moves and merges                                    |                |          |                   |               | pending |        |
| 3.6  | Delete **D** rows (root confirms tag first)                                 |                |          |                   |               | pending |        |
| 3.7  | `SKILL.md` ≤ 150 lines                                                      |                |          |                   |               | pending |        |
| 3.8  | Remove `references/`; fix string references                                 |                |          |                   |               | pending |        |
| gate | Phase 3 exit gate                                                           | —              |          |                   |               | pending |        |

## Phase 4 — host enforcement

| Step | Deliverable                                        | Executor model | Attempts | Validator verdict | Root decision | Status  | Commit |
| ---- | -------------------------------------------------- | -------------- | -------- | ----------------- | ------------- | ------- | ------ |
| 4.1  | Claude wrappers, command, hook, tests              |                |          |                   |               | pending |        |
| 4.2  | Cursor wrappers, skill, hook, tests                |                |          |                   |               | pending |        |
| 4.3  | Codex wrappers, hook, installer depth check, tests |                |          |                   |               | pending |        |
| 4.4  | Adapter READMEs enforcement matrices               |                |          |                   |               | pending |        |
| 4.5  | Manual Cursor smoke (root + owner)                 | —              |          |                   |               | pending |        |
| gate | Phase 4 exit gate                                  | —              |          |                   |               | pending |        |

## Phase 5 — author emits the machine

| Step | Deliverable                               | Executor model | Attempts | Validator verdict | Root decision | Status  | Commit |
| ---- | ----------------------------------------- | -------------- | -------- | ----------------- | ------------- | ------- | ------ |
| 5.1  | `draft` mode writes three agent templates |                |          |                   |               | pending |        |
| 5.2  | `draft-check` in the validator path       |                |          |                   |               | pending |        |
| 5.3  | `docs/authoring.md` ≤ 60 lines            |                |          |                   |               | pending |        |
| 5.4  | Author evals assertion                    |                |          |                   |               | pending |        |
| gate | Phase 5 exit gate                         | —              |          |                   |               | pending |        |

## Phase 6 — documentation as a descriptive model

| Step | Deliverable                    | Executor model | Attempts | Validator verdict | Root decision | Status  | Commit |
| ---- | ------------------------------ | -------------- | -------- | ----------------- | ------------- | ------- | ------ |
| 6.1  | Root `README.md`               |                |          |                   |               | pending |        |
| 6.2  | Package `README.md` ≤ 80 lines |                |          |                   |               | pending |        |
| 6.3  | `test_docs_truth.py`           |                |          |                   |               | pending |        |
| 6.4  | `RUNBOOK.md`                   |                |          |                   |               | pending |        |
| gate | Phase 6 exit gate              | —              |          |                   |               | pending |        |

## Phase 7 — benchmark (root + owner)

| Step | Deliverable                                                        | Executor model | Attempts | Validator verdict | Root decision | Status  | Commit |
| ---- | ------------------------------------------------------------------ | -------------- | -------- | ----------------- | ------------- | ------- | ------ |
| 7.1  | Core set: 3 with-skill + 1 without × 4 evals                       | —              |          |                   |               | pending |        |
| 7.2  | Author set: 3 with-skill + 1 without × 2 evals                     | —              |          |                   |               | pending |        |
| 7.3  | `measure_run.py` aggregate; budget columns filled; ADR 0005 item 3 | —              |          |                   |               | pending |        |
| gate | Phase 7 exit gate (escalation rule applied if needed)              | —              |          |                   |               | pending |        |

## Phase 8 — release (root + owner)

| Step | Deliverable                                                            | Executor model | Attempts | Validator verdict | Root decision | Status  | Commit |
| ---- | ---------------------------------------------------------------------- | -------------- | -------- | ----------------- | ------------- | ------- | ------ |
| 8.1  | CHANGELOG 4.0.0, `VERSION = "4.0.0"`, builds, reinstall, scratch smoke |                |          |                   |               | pending |        |
| 8.2  | Session directory move; session note closed                            | —              |          |                   |               | pending |        |
| 8.3  | Push `main` + tag `v4.0.0` to `origin` (owner's explicit word)         | —              |          |                   |               | pending |        |
| gate | Phase 8 exit gate                                                      | —              |          |                   |               | pending |        |
