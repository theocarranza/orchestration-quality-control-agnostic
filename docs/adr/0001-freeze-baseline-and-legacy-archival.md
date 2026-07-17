# ADR 0001 — Freeze baseline and legacy archival

## Status

Accepted, 2026-07-16.

## Context

This repository began as a partial, uncommitted copy of a v3
`e2e-quality-control` system originally built inside the Aplicatudo
monorepo. Before extracting a portable core from it, the starting state
needed to be committed and separated from the new package being built, so
every later change is reviewable as a diff against something real.

Exploration during planning missed two directories at the repository root:
`agents/` (the three subagent definitions referenced everywhere but assumed
missing) and `plugins/e2e-quality-control/` (a legacy v1.2.0 plugin wrapper,
including the actual old-shape `.skill` archive the original architecture
report's Problem 2 describes, plus a second copy of the shared library with
its own stale checkpoint and marker file). Both were found only after `git
init`, while inspecting the tree before the first commit.

## Decision

Everything present at the repository root except this vault
(`AI_Codex_OrchestratorQcPlugin/`) and the live MCP configuration
(`.mcp.json`) was moved into `legacy/` and committed as-is, in a single
initial commit, before any restructuring began. `legacy/` is read-only
reference source material for the rest of the build — nothing in later
phases edits it in place; content that survives moves into
`orchestration-quality-control/` by copy-then-transform, or into a profile.

This is a freeze baseline, not contamination: the evaluations and the
`legacy/e2e-quality-control-workspace/iteration-1/` benchmark results (100%
pass with the skill vs. 67% without) validate the copied tree's behavior.
Runtime state under `legacy/` — two stale checkpoints with a marker file
each — is kept as historical evidence rather than deleted, but neither ships
in the new package; a root `.gitignore` excludes any new runtime state going
forward.

The `plugins/e2e-quality-control/` discovery is not analyzed in depth here;
see the session record in the vault
(`AI_Codex_OrchestratorQcPlugin/Agent_Sessions/2026-07-16-133000-orchestration-qc-extraction-implementation.md`)
for what was found. It may be revisited if its packaging conventions become
relevant during the Claude adapter or versioning phases.

## Consequences

- Every later phase's file moves are `git diff`-able against a real
  starting point.
- The three subagent definitions found in `legacy/agents/` are ported and
  adapted in the Claude adapter phase rather than authored from nothing.
- The genuine old-shape `.skill` archive found in `legacy/plugins/` confirms
  the original architecture report's Problem 2 was accurate, correcting an
  earlier adversarial-critique claim that no such archive could be found in
  this repository.
