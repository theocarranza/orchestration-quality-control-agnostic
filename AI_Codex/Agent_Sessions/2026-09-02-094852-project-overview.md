---
date: 2026-09-02
type: session
status: open
handoff: cursor-agent
---

# Session — Project overview (read-only)

Previous Session: [[2026-07-17-111000-oqc-2-0-0-release]]
Next Session:

## Handoff — for the next Cursor agent (ongoing, do not open a new session)

**Read this first.** This workstream is still open. Update **this file** only; do not create a new session entry until the user closes this one.

| Field | Value |
| --- | --- |
| **Branch** | `main` (pushed to `origin` as of 2026-09-02T11:50-03:00; HEAD `ef10204`) |
| **Latest commit** | `ef10204` — `docs(ledger): checkpoint 3.1.0 shipped and evals still live-model gated` |
| **Uncommitted** | this session note + ADR 0005 live-model notes (eval workspace is gitignored) |
| **Commit policy** | User must explicitly ask before any commit or push |

### What landed in `83f2981`

- Vault renamed `AI_Codex_OrchestratorQcPlugin/` → `AI_Codex/`
- ADRs moved `docs/adr/` → `AI_Codex/Architecture/ADR/`
- Specs/plans moved out of `docs/superpowers/` → ledger paths
- User doc added: `docs/authoring.md` (3.1.0 specified, not shipped)
- ADR 0012 + greenfield authoring spec; docs/ledger layout spec + plan
- Root README rewritten for new layout; `.gitignore` negates global `AI_Codex/` ignore

### In progress (same session)

User reviewed rendered README and reported three issues:

1. **Sequence diagram** — flow stopped before Human; fixed: added `H-->>U: final reconciliation report` (uncommitted).
2. **Repository layout Mermaid** — overlapping edges from nodes back into subgraph; fixed: descriptions on nodes, no self-edges (uncommitted).
3. **Dead links** — full markdown scan found only `dist/` dead (gitignored generated output); changed to plain text in layout table (uncommitted). `docs/authoring.md` and `AI_Codex/Architecture/ADR/*` are live locally; GitHub 404 until push.

Also removed duplicate checkpoint paragraph in README (uncommitted).

## Sequence diagram layout — 2026-09-02T11:16-03:00

User asked to clean up bottom-of-diagram appearance. Reordered participants (Remediator before Validator so O↔R execution arrows are adjacent), shortened labels, added `Note over U,R: run complete` for visual closure.

### Pending / next steps

- [x] README polish committed with later 3.1.0 docs work
- [x] Push to `origin` (`theocarranza/orchestration-quality-control-agnostic`, `ef10204`)
- [x] Live-model ADR 0005 sets graded: example-pipeline 100% with-skill; core 95.8% (clean run 1 fabricated W13). Item 3 stays open.
- [x] Author evals (8 runs) aggregated 2026-09-02T12:32-03:00: 100% with-skill / 71% without-skill. Extra set — ADR 0005 item 3 still open.
- [x] Human-approval showstopper: canvas kept only `author-outcome`. 3.2.0 auto-continues the rest. Committing and reinstalling the Cursor plugin.

### Key paths

| Audience | Path |
| --- | --- |
| Product users | `docs/authoring.md`, `orchestration-quality-control/` |
| Contributors | `AI_Codex/` (ADRs, specs, plans, sessions) |
| Layout design | `AI_Codex/Architecture/Specs/2026-09-02-docs-and-ledger-layout-design.md` |
| Implementation plan | `AI_Codex/Implementation_Plans/2026-09-02-docs-and-ledger-layout.md` |

### Bootstrap reminder

1. Read workspace `AI_Codex/README.md` (Personal root) if in monorepo context
2. Read **this** session (newest in `AI_Codex/Agent_Sessions/`)
3. Read `AI_Codex/Knowledge/Documentation.md` for docs vs ledger rules
4. Continue same session — append checkpoints, do not spawn a new session file

## Bootstrap

- **Timestamp:** 2026-09-02T09:48:52-03:00
- **Branch:** `main` (HEAD `ref: refs/heads/main`; working tree may not be a fully usable git checkout in this environment)
- **Carried forward:** Last recorded work was the 2.0.0 release (isolated three-agent topology only, Claude marketplace adapter, tag `v2.0.0`). Session left open since 2026-07-17.
- **Current intent:** Implement the agnostic `example-pipeline` strip (3.0.0). Tokens received: vault deletion authorized, implementation approved.

## Workflow selection

Brainstorming (`using-superpowers` → brainstorming skill). Ticket intake deferred until the design is approved. No Azure DevOps work item supplied.

## Design checkpoint — 2026-09-02T09:55-03:00

Spec drafted at `docs/superpowers/specs/2026-09-02-agnostic-example-pipeline-design.md`. Awaiting user review. Spec not committed (commit only on request). Implementation still locked.

## Implementation checkpoint — 2026-09-02T10:20-03:00

3.0.0 strip executed: `example-pipeline` profile shipped; former product profile, predecessor aliases, archived predecessor tree, and product-only vault notes removed; remaining docs/vault rewritten. Search gate and offline tests pending this checkpoint.

## Authoring spec — 2026-09-02T10:43-03:00

Greenfield authoring specified: audit-then-focused-interview, `author_prepare`/`author_apply`, ADR 0012, `docs/authoring.md`. Specified for 3.1.0, not shipped.

## Docs vs Codex — 2026-09-02T11:01-03:00

Implementation approved. Vault renamed `AI_Codex/`. ADRs/specs/plans moved out of `docs/superpowers` and `docs/adr`. Visual-docs rule in `Knowledge/Documentation.md`. Awaiting search gates.

## Bootstrap (continued)

- **Timestamp:** 2026-09-02T11:13-03:00
- **Branch:** `main`
- **Carried forward:** Docs/ledger layout gate passed; README review in progress (diagram + link fixes).
- **Current intent:** Finish README polish from user review; commit when requested.

## Gate — docs/ledger layout — 2026-09-02T11:09-03:00

Passed. `docs/` is user-facing (`authoring.md` only). Ledger is `AI_Codex/` (versioned; repo `.gitignore` negates a user-global `AI_Codex/` ignore). ADRs, specs, and plans live under the ledger. Mermaid on live user and contributor notes. Offline tests 157 OK (71+8+6+36+19+17). No `docs/superpowers` tree. No live `docs/adr/` pointers. Closing this step with a commit. Next separable gate gets its own checkpoint then commit.

## Gate 1 — discover_workspace + plan_interview — 2026-09-02T11:20-03:00

Passed. 9 new tests. Audit records stack/layout/tests/CI/orchestration/mechanism/profile hints. Interview plan never asks those facts; forks author vs upgrade when something exists.

## Gate 2 — author_state + apply_author — 2026-09-02T11:25-03:00

Passed. 8 tests. Create requires all_passed findings and empty output_root, shares pending_approval, decline writes nothing, approve copies the preview tree.

## Gate 3–5 — 3.1.0 authoring shipped — 2026-09-02T11:40-03:00

Passed. Workflows, SKILL, Claude `/oqc-author`, Cursor `/oqc-author`, Codex `orchestration-author`. Reuses upgrade agents. Two author evals. Version 3.1.0. Offline tests 174 OK (88+8+6+36+19+17).

## README polish — 2026-09-02T11:15-03:00

User review (same session): sequence diagram missing Human return; repository layout Mermaid overlap; `dist/` dead link. Fixed in root README. `docs/authoring.md` is live locally; GitHub will 404 until the restructure is pushed.

## Carried-forward update — 2026-09-02T09:51-03:00

User asked to strip every the former product reference so the tool is truly agnostic. Exploration shows the **profile mechanism is already generic**; the only shipped profile is `former-product-profile`. References also live in docs, ADRs, evals, Claude compatibility aliases (`predecessor-skill-*`), `legacy/`, and the vault.

## New origin — 2026-09-02T10:27-03:00

Parallel investigation: keep history, rename original remote to `upstream` (push disabled), create GitHub repo `orchestration-quality-control-agnostic` as `origin`, commit and push 3.0.0 work there only.

## Bootstrap (continued)

- **Timestamp:** 2026-09-02T11:30-03:00
- **Branch:** `main` at `92fd5c1`, ahead of `origin/main` by 5
- **Carried forward:** 3.1.0 authoring shipped locally; live-model evals still open
- **Current intent:** Commit remaining work if any; explain evals. Working tree was clean except this note.

## Commit + evals briefing — 2026-09-02T11:30-03:00

User asked to commit and explain evals. No product code was uncommitted. This ledger handoff was stale (still described README polish as uncommitted and `main` as 1 commit ahead). Updating this note, then committing it.

Eval briefing delivered in chat: three live-model sets (core 4, example-pipeline 4, author 2); `eval-harness/` stages and integrity-checks them; ADR 0005 item 3 still open; author evals are extra and not yet in that ADR gate.

## Push + live evals — 2026-09-02T11:50-03:00

User asked for both push and live benchmark.

- Pushed `main` to origin `https://github.com/theocarranza/orchestration-quality-control-agnostic.git` (`3be979f..ef10204`). Did not push `upstream`.
- Staged gitignored workspaces under `orchestration-quality-control-workspace/{core,example-pipeline,author}/iteration-1/`. Author evals used unique slugs `eval-author-1` / `eval-author-2` because `convert_evals.py` would collide on `README.md`.
- Launched 32 Cursor executor subagents (3 with-skill + 1 without-skill × 8 ADR 0005 evals). Author wave waits until this wave finishes, then integrity, grade, aggregate, gate.

## Grading checkpoint — 2026-09-02T11:56-03:00

- **Timestamp:** 2026-09-02T11:56-03:00
- **Branch:** `main`
- **Carried forward:** Live-model eval executors in flight; integrity/grade/aggregate still pending for the rest of the wave.
- **Current intent:** Grade `example-pipeline` eval `missing-gates-pipeline` without_skill run-1 only (do not re-execute the skill).

Graded `orchestration-quality-control-workspace/example-pipeline/iteration-1/eval-missing-gates-pipeline/without_skill/run-1/` → `grading.json`. Result: **2 passed / 3 failed / 5 total** (pass_rate 0.4). Failed: missing bounded retry; missing/invalid approval field (process-gate wording, not the field contract); reader-facing abbreviations/decorative symbols. Passed: English report exists; fixture unedited (`integrity.json` `unedited: true`).

## Grade — example-pipeline missing-gates with_skill run-1 — 2026-09-02T11:58-03:00

Graded existing outputs only (skill not re-executed). `grading.json` written beside `outputs/`.

- **Result:** 5/5 passed (pass_rate 1.0). No failed assertions.
- **Integrity:** `unedited=true`, `changed_files=[]`. `isolation_ok=false` is skill-file reads; not treated as an edit fail.
- **Timing:** executor 420s (`timing.json`); grader ~230s.

## Grading checkpoint — 2026-09-02T11:56-03:00

Graded `example-pipeline` eval `missing-gates-pipeline` with_skill run-2 from existing artifacts (skill not re-run). Wrote `orchestration-quality-control-workspace/example-pipeline/iteration-1/eval-missing-gates-pipeline/with_skill/run-2/grading.json`. Result: 5/5 passed. Fixture unedited per `integrity.json`.

Graded with_skill run-3 the same way. Wrote `.../with_skill/run-3/grading.json`. Result: 5/5 passed. No failed assertions.

## Grade — example-pipeline inline-env with_skill run-3 — 2026-09-02T12:00-03:00

- **Timestamp:** 2026-09-02T12:00-03:00
- **Branch:** `main`
- **Carried forward:** Live-model eval grading in flight.
- **Current intent:** Grade `example-pipeline` eval `inline-env-pipeline` with_skill run-3 from existing artifacts (do not re-execute the skill).

Wrote `orchestration-quality-control-workspace/example-pipeline/iteration-1/eval-inline-env-pipeline/with_skill/run-3/grading.json`. Result: **5 passed / 0 failed / 5 total** (pass_rate 1.0). No failed assertions. Fixture unedited per `integrity.json`. `isolation_ok=false` weighed as skill/harness path heuristic, not an unrelated-project read.

## Grade — core rules-generic-with-rationale with_skill run-2 — 2026-09-02T12:02-03:00

- **Timestamp:** 2026-09-02T12:02:29-03:00
- **Branch:** `main`
- **Carried forward:** Live-model eval grading in flight; remaining integrity/grade/aggregate still pending.
- **Current intent:** Grade `core` eval `rules-generic-with-rationale` with_skill run-2 from existing artifacts (do not re-execute the skill).

Wrote `orchestration-quality-control-workspace/core/iteration-1/eval-rules-generic-with-rationale/with_skill/run-2/grading.json`. Result: **5 passed / 0 failed / 5 total** (pass_rate 1.0). No failed assertions. Integrity: `unedited=true`; `isolation_ok=false` weighed as skill-relative paths, not a sandbox leak.

## Grade — core rules-generic-with-rationale with_skill run-1 — 2026-09-02T12:05-03:00

- **Timestamp:** 2026-09-02T12:05-03:00
- **Branch:** `main`
- **Carried forward:** Live-model eval grading wave in flight.
- **Current intent:** Grade `core` eval `rules-generic-with-rationale` with_skill run-1 from existing artifacts (skill not re-executed).

Wrote `orchestration-quality-control-workspace/core/iteration-1/eval-rules-generic-with-rationale/with_skill/run-1/grading.json`. Result: **5 passed / 0 failed / 5 total** (pass_rate 1.0). Fixture unedited (`integrity.json` `unedited: true`). `isolation_ok=false` weighed as heuristic skill-file basename reads, not an isolation fail.

## Grade — core workflows-generic-clean without_skill run-1 — 2026-09-02T12:02-03:00

- **Timestamp:** 2026-09-02T12:02-03:00
- **Branch:** `main`
- **Carried forward:** Live-model eval grading still in flight for remaining runs.
- **Current intent:** Grade `core` eval `workflows-generic-clean` without_skill run-1 from existing artifacts (do not re-execute the skill).

Wrote `orchestration-quality-control-workspace/core/iteration-1/eval-workflows-generic-clean/without_skill/run-1/grading.json`. Result: **4 passed / 0 failed / 4 total** (pass_rate 1.0). No failed assertions. Fixture unedited (`integrity.json` `unedited: true`); `isolation_ok=false` only for harness `run_config.json`, weighed as not a fail.

## Grade — core workflows-generic-clean with_skill run-3 — 2026-09-02T11:59-03:00

- **Timestamp:** 2026-09-02T11:59-03:00
- **Branch:** `main`
- **Carried forward:** Live-model eval grading wave; remaining core/example-pipeline runs still to grade.
- **Current intent:** Grade `core` eval `workflows-generic-clean` with_skill run-3 from existing artifacts (do not re-execute the skill).

Wrote `orchestration-quality-control-workspace/core/iteration-1/eval-workflows-generic-clean/with_skill/run-3/grading.json`. Result: **4 passed / 0 failed / 4 total**. `integrity.json`: `unedited=true`; `isolation_ok=false` weighed as skill-script basename / `.orchestration-qc` heuristic noise, not a sandbox leak.

## Grade — core deploy-orchestrator with_skill run-3 — 2026-09-02T12:01-03:00

- **Timestamp:** 2026-09-02T12:01-03:00
- **Branch:** `main`
- **Carried forward:** Live-model eval grading wave; remaining core/example-pipeline runs still pending.
- **Current intent:** Grade `core` eval `deploy-orchestrator` with_skill run-3 from existing artifacts (do not re-execute the skill).

Wrote `orchestration-quality-control-workspace/core/iteration-1/eval-deploy-orchestrator/with_skill/run-3/grading.json`. Result: **5 passed / 0 failed / 5 total** (pass_rate 1.0). No failed assertions. Fixture unedited (`integrity.json` `unedited: true`); `isolation_ok=false` weighed as skill/output path-token noise, not an edit fail.

## Grade — core workflows-generic-clean with_skill run-2 — 2026-09-02T12:00-03:00

- **Timestamp:** 2026-09-02T12:00-03:00
- **Branch:** `main`
- **Carried forward:** Live-model eval grading wave; remaining core/example-pipeline runs still pending.
- **Current intent:** Grade `core` eval `workflows-generic-clean` with_skill run-2 from existing artifacts (do not re-execute the skill).

Wrote `orchestration-quality-control-workspace/core/iteration-1/eval-workflows-generic-clean/with_skill/run-2/grading.json`. Result: **4 passed / 0 failed / 4 total** (pass_rate 1.0). No failed assertions. `integrity.json`: `unedited=true`; `isolation_ok=false` weighed as skill-package/executor-bootstrap path tokens, not a sandbox leak.

## Grade — example-pipeline rules-with-rationale without_skill run-1 — 2026-09-02T12:01-03:00

- **Timestamp:** 2026-09-02T12:01-03:00
- **Branch:** `main`
- **Carried forward:** Live-model eval grading wave in flight.
- **Current intent:** Grade `example-pipeline` eval `rules-with-rationale` without_skill run-1 from existing artifacts (do not re-execute the skill).

Wrote `orchestration-quality-control-workspace/example-pipeline/iteration-1/eval-rules-with-rationale/without_skill/run-1/grading.json`. Result: **5 passed / 0 failed / 5 total** (pass_rate 1.0). No failed assertions. `integrity.json`: `unedited=true`; `isolation_ok=false` weighed as harness/output paths (`EXECUTOR_WITHOUT_SKILL.md`, `outputs/report.md`, `run_config.json`), not a sandbox leak.

## Grade — example-pipeline inline-env-pipeline with_skill run-1 — 2026-09-02T12:02-03:00

- **Timestamp:** 2026-09-02T12:02-03:00
- **Branch:** `main`
- **Carried forward:** Live-model eval grading wave; remaining core/example-pipeline runs still pending.
- **Current intent:** Grade `example-pipeline` eval `inline-env-pipeline` with_skill run-1 from existing artifacts (do not re-execute the skill).

Wrote `orchestration-quality-control-workspace/example-pipeline/iteration-1/eval-inline-env-pipeline/with_skill/run-1/grading.json`. Result: **5 passed / 0 failed / 5 total** (pass_rate 1.0). No failed assertions. Fixture unedited (`integrity.json` `unedited: true`). `isolation_ok=false` weighed as skill/harness path heuristic, not an unrelated-project read.

## Author evals aggregated — 2026-09-02T12:32-03:00

- **Timestamp:** 2026-09-02T12:32-03:00
- **Branch:** `main` (HEAD `ef10204`, origin in sync)
- **Carried forward:** ADR 0005 item 3 still open (core clean-fixture W13 on with-skill run 1). Author evals were extra, not that gate.
- **Current intent:** Aggregate author iteration-1 and record results. Do not close item 3.

All eight author runs graded. Aggregated with skill-creator `aggregate_benchmark.py`. Viewer: `orchestration-quality-control-workspace/author/iteration-1/review.html` (also generated for core and example-pipeline).

**With-skill: 100% ± 0%** (mean 1.0, min 1.0, max 1.0). **Without-skill: 71% ± 6%**. Delta **+0.29**.

| Eval | W1 | W2 | W3 | Without |
| --- | --- | --- | --- | --- |
| author-1 (audit / no-write-until-approve) | 4/4 | 4/4 | 4/4 | 3/4 |
| author-2 (apply into empty output folder) | 3/3 | 3/3 | 3/3 | 2/3 |

Without-skill misses (not a gate):

- author-1: “Runs internal quality control on the draft before offering apply” — reviewed fixture stubs, not a drafted process-document tree.
- author-2: “Emits architecture, rules, and workflow documents” — wrote `WORKFLOW.md` / `checks.json` / `run-core-checks.py` instead of architecture + rules + workflow.

Artifacts: `orchestration-quality-control-workspace/author/iteration-1/benchmark.json`. ADR 0005 Consequences notes this set is extra; item 3 stays open. Uncommitted ledger only; eval workspace gitignored. Commit/push only if the user asks.

## Grade — core workflows-generic-missing-delegation-spec with_skill run-2 — 2026-09-02T12:03-03:00

- **Timestamp:** 2026-09-02T12:03-03:00
- **Branch:** `main`
- **Carried forward:** Live-model eval grading wave; remaining core/example-pipeline runs still pending.
- **Current intent:** Grade `core` eval `workflows-generic-missing-delegation-spec` with_skill run-2 from existing artifacts (do not re-execute the skill).

Wrote `orchestration-quality-control-workspace/core/iteration-1/eval-workflows-generic-missing-delegation-spec/with_skill/run-2/grading.json`. Result: **5 passed / 0 failed / 5 total** (pass_rate 1.0). No failed assertions. Fixture unedited (`integrity.json` `unedited: true`; sha256 matches baseline). `isolation_ok=false` weighed as skill-file reads, not an edit fail.

## ADR 0005 gate — 2026-09-02T12:12-03:00

example-pipeline aggregated at **100% with-skill** / 75% without-skill. Core aggregated at **95.8% with-skill** / 85% without-skill. Fail: `eval-workflows-generic-clean` with-skill run 1 invented a W13 finding and proposed an edit. Item 3 stays open; recorded in ADR 0005 Consequences.

Author evals later aggregated at **100% with-skill** / 71% without-skill (see checkpoint 2026-09-02T12:32-03:00). That set is extra and does not close item 3.

## Human-approval UI showstopper — 2026-09-02T12:47-03:00

- **Timestamp:** 2026-09-02T12:47-03:00
- **Branch:** `main`
- **Carried forward:** ADR 0005 item 3 still open. Author evals aggregated.
- **Current intent:** Inventory every human wait; do not change product code until keep/remove and UI approach are chosen.

User found `eval-author-1` `apply_decision.md` = `waiting_for_approval`. Nested Task asked for approval; Cursor OS notifications opened the parent chat with no question card. Designed contract: root session owns UI; nested agents never ask. Host does not bubble AskQuestion.

Author-1 wait is the **author_apply write gate** (eval also said write nothing until approve). Distinct from interview field `approval` (whether the authored process includes a human stop).

Canvas: keep/remove toggles for all runtime waits. No skill mutation yet. Next: user decisions, then host UI so remaining Keep gates appear in the parent session.

## 3.2.0 auto-continue — 2026-09-02T13:46-03:00

- **Timestamp:** 2026-09-02T13:46-03:00
- **Branch:** `main`
- **Carried forward:** ADR 0005 item 3 still open.
- **Current intent:** Commit 3.2.0 and the live-model ledger notes; reinstall the Cursor plugin. Do not push unless asked.

User kept only `author-outcome` on the canvas. Packaged defaults auto-continue every other former gate. Root session asks outcome, then confirms defaults; nested agents must not ask. Offline script tests: 91 OK.
