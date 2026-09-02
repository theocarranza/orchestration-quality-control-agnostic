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
| **Branch** | `main` (ahead of `origin/main` by 1 commit as of 2026-09-02T11:14-03:00) |
| **Latest commit** | `83f2981` — `docs: split the contributor ledger from user docs and specify authoring` |
| **Uncommitted** | `README.md` (diagram + link polish), this session note |
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

### Pending / next steps

- [ ] User review of README fixes (preview Mermaid + links)
- [ ] Commit README polish if user asks (can amend into docs commit or separate — ask user)
- [ ] Push to `origin` when user asks (fixes GitHub dead links)
- [ ] **New origin** (user intent, not executed): rename current remote to `upstream`, create `orchestration-quality-control-agnostic` as `origin`, push 3.0.0+ work there only — see checkpoint below
- [ ] Live-model eval parity (ADR 0005 item 3) still open from 2.0.0 era

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

## README polish — 2026-09-02T11:15-03:00

User review (same session): sequence diagram missing Human return; repository layout Mermaid overlap; `dist/` dead link. Fixed in root README. `docs/authoring.md` is live locally; GitHub will 404 until the restructure is pushed.

## Carried-forward update — 2026-09-02T09:51-03:00

User asked to strip every the former product reference so the tool is truly agnostic. Exploration shows the **profile mechanism is already generic**; the only shipped profile is `former-product-profile`. References also live in docs, ADRs, evals, Claude compatibility aliases (`predecessor-skill-*`), `legacy/`, and the vault.

## New origin — 2026-09-02T10:27-03:00

Parallel investigation: keep history, rename original remote to `upstream` (push disabled), create GitHub repo `orchestration-quality-control-agnostic` as `origin`, commit and push 3.0.0 work there only.
