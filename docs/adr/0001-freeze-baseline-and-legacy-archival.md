# ADR 0001 — Freeze baseline and later removal of the predecessor tree

## Status

Accepted, 2026-07-16. Amended by [ADR 0011](0011-agnostic-example-pipeline-profile.md), 2026-09-02.

## Context

This repository began as a partial, uncommitted copy of a product-specific
predecessor skill. Before extracting a portable core from it, the starting
state needed to be committed and separated from the new package being built,
so every later change is reviewable as a diff against something real.

Exploration during planning also found extra predecessor plugin and agent
directories at the repository root that had been assumed missing.

## Decision

Everything present at the repository root except this vault
(`AI_Codex_OrchestratorQcPlugin/`) and the live MCP configuration
(`.mcp.json`) was moved into a historical tree and committed as-is, in a
single initial commit, before any restructuring began. That tree was
read-only reference source material for the rest of the 1.x/2.x build.

[ADR 0011](0011-agnostic-example-pipeline-profile.md) later **removed that
historical tree** from the repository so the public project is not coupled
to the predecessor product. The freeze still happened; the files are no
longer shipped.

## Consequences

- Every later phase's file moves were `git diff`-able against a real
  starting point during the extraction.
- Subagent definitions found in the freeze tree were ported into the Claude
  adapter rather than authored from nothing.
- After 3.0.0, do not restore the historical tree. Cite this ADR and ADR
  0011 instead.
