---
date: 2026-07-16
type: session
status: closed
---

# Session — Orchestration QC extraction implementation

Previous Session: [[2026-07-16-120000-adversarial-critique-qc-feedback]]
Next Session: [[2026-07-17-010620-eval-parity-benchmark]]

## Scope

Execute [[2026-07-16-orchestration-qc-extraction-plan|the approved implementation plan]] to extract the portable `orchestration-quality-control` skill, honoring both [[2026-07-15-orchestration-qc-openskills-architecture|the architecture report]] and [[2026-07-16-adversarial-critique-qc-architecture-feedback|the adversarial critique]] as governing documents.

## Pivot - 2026-07-16 13:30

Before Phase 0's freeze commit, discovered two directories the original exploration pass missed: repo-root `agents/` (the three subagent definitions the plan assumed were missing — they exist, with tool grants matching the README) and `plugins/e2e-quality-control/` (a legacy v1.2.0 plugin wrapper containing the actual old-shape `.skill` archive the architecture report's Problem 2 describes, plus a second full copy of the shared library with its own stale checkpoint/marker).

User decision: restructure Phase 0 from in-place `git mv` renames to a simpler archival move — everything at repo root except this vault and `.mcp.json` moves into a new `legacy/` folder, used as read-only reference source material for the rest of the build. The `plugins/` folder is not being separately documented in depth right now (noted here only); revisit if its packaging conventions become relevant during Phase 4/6 adapter work.

Filesystem move completed: `agents/`, `.cursor/`, `e2e-quality-control/`, `e2e-quality-control-execute/`, `e2e-quality-control-validate/`, `e2e-quality-control-workspace/`, `plugins/` → `legacy/`. Root now holds only `AI_Codex_OrchestratorQcPlugin/`, `.mcp.json`, `.git/`, and `legacy/`.

**Blocked:** the freeze commit is held pending git identity. `git init` picked up the global identity (`Théo Carranza <theo.carranza@bhave.life>`), which doesn't match the account email on file for this session (`theocarranza@gmail.com`). User selected setting a repo-local override; as of this entry it has not yet been applied (`git config --local --list` shows no `user.*` keys). Waiting before running `git add` / `git commit`.

## Implementation Checkpoint - 2026-07-16 (session close)

All six phases of [[2026-07-16-orchestration-qc-extraction-plan|the implementation plan]] are complete. Repo-local git identity was set by the user (`theocarranza@gmail.com`), unblocking the freeze commit.

**Scope:** Full extraction of `orchestration-quality-control` from the legacy `e2e-quality-control` v3 tree, per the architecture report and adversarial critique.

**Changes (7 commits, tagged `v1.0.0`):**

- **Phase 0** — froze the pre-existing tree as-is, then archived everything except this vault and `.mcp.json` into `legacy/` as read-only reference material (a mid-build pivot from the plan's original in-place `git mv` approach, per direct user instruction). Discovered `legacy/agents/` (the three subagent definitions, assumed missing) and `legacy/plugins/e2e-quality-control/` (the genuine old-shape `.skill` archive, correcting an earlier claim in the adversarial critique that no such archive existed in this repo).
- **Phase 1** — `references/schemas/` (5 JSON Schemas + kind registry) and `scripts/` (6 Python 3 stdlib-only, model-free scripts: classify_targets, derive_finding_id, checkpoint_state, reconcile_decision, render_diff, qc_lib). Content-anchored finding ids proven stable across line drift via a dedicated fixture pair. 53 unit tests.
- **Phase 2** — `SKILL.md` (Agent Skills spec-minimal frontmatter) and the 11 generic rules/workflows files, renamed and de-branded, with the generator-quality-control file decoupled from the hardcoded E2E artifact reference via the profile-manifest indirection.
- **Phase 3** — the `aplicatudo-e2e` profile, with a real bug caught and fixed during verification: the profile's classification globs assumed a stricter file-naming convention than the actual eval fixtures used, silently classifying several as "unknown" until widened.
- **Phase 4** — the Claude adapter: 3 ported subagents (Bash grant added, restricted by instruction to named scripts — see ADR 0004), 2 commands + 2 compatibility aliases, and a freshly authored `PreToolUse` hook (no legacy implementation existed) with 8 offline tests. Verified with a full simulated validate→block→execute→unblock cycle through the real scripts and hook.
- **Phase 5** — `evals/core/` with 4 new non-E2E fixtures, and `docs/adr/0005` recording the definition of done honestly: 3 of 4 criteria verified deterministically; the 4th (profile evals reaching benchmark parity) is explicitly left open since it requires a live model session this implementation pass had no access to.
- **Phase 6** — changelogs at 1.0.0 for both core and profile; confirmed the "retire old sibling skills" step needed no action since Phase 0's `legacy/` pivot already superseded it. Tagged `v1.0.0`.

**Validation:** 61 offline unit tests (53 script + 8 hook) pass at every phase gate; every `@`-reference across the built package resolves (26 checked in the final sweep); every JSON file parses; a full package-wide vocabulary sweep confirms zero Aplicatudo/Maestro/Flutter coupling outside `profiles/aplicatudo-e2e/` and legitimate historical-context mentions.

**Known open item:** ADR 0005 item 3 (profile evals at benchmark parity) requires a live model run and remains unverified — flagged explicitly rather than assumed.
