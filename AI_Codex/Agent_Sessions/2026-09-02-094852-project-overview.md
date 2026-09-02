---
date: 2026-09-02
type: session
status: open
---

# Session — Project overview (read-only)

Previous Session: [[2026-07-17-111000-oqc-2-0-0-release]]
Next Session:

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

## Gate — docs/ledger layout — 2026-09-02T11:09-03:00

Passed. `docs/` is user-facing (`authoring.md` only). Ledger is `AI_Codex/` (versioned; repo `.gitignore` negates a user-global `AI_Codex/` ignore). ADRs, specs, and plans live under the ledger. Mermaid on live user and contributor notes. Offline tests 157 OK (71+8+6+36+19+17). No `docs/superpowers` tree. No live `docs/adr/` pointers. Closing this step with a commit. Next separable gate gets its own checkpoint then commit.

## Carried-forward update — 2026-09-02T09:51-03:00

User asked to strip every the former product reference so the tool is truly agnostic. Exploration shows the **profile mechanism is already generic**; the only shipped profile is `former-product-profile`. References also live in docs, ADRs, evals, Claude compatibility aliases (`predecessor-skill-*`), `legacy/`, and the vault.

## New origin — 2026-09-02T10:27-03:00

Parallel investigation: keep history, rename original remote to `upstream` (push disabled), create GitHub repo `orchestration-quality-control-agnostic` as `origin`, commit and push 3.0.0 work there only.
