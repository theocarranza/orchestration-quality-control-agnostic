# ADR 0004 — Orchestrator, Validator, and Remediator subagents gain a restricted Bash grant

## Status

Accepted, 2026-07-16.

## Context

The legacy v3 subagents' tool grants were `Agent, Read, Write`
(Orchestrator), `Read, Grep, Glob` (Validator), and `Read, Edit` (Formatter)
— no subagent had Bash. That was sufficient when the checkpoint state
machine, finding identity, and decision reconciliation were all described in
prose for a model to follow by instruction. Phase 1 of this extraction moved
every one of those responsibilities into deterministic Python scripts under
`scripts/`, specifically so their behavior does not depend on a model
following instructions consistently (see the original system's Problem 5:
non-deterministic Validator/Formatter results on identical input).

A subagent that cannot execute those scripts cannot benefit from them — it
would fall back to producing the same values by instruction-following alone,
which reintroduces exactly the non-determinism the scripts exist to remove.

## Decision

All three Claude adapter subagents gain `Bash` in their tool grant, each
restricted by instruction to a named subset of `scripts/`:

- `oqc-orchestrator`: `scripts/checkpoint_state.py`, `scripts/reconcile_decision.py`.
- `oqc-validator`: `scripts/classify_targets.py`, `scripts/derive_finding_id.py`.
- `oqc-remediator`: `scripts/render_diff.py`.

This restriction is enforced by the subagent's own operating instructions
(see each agent file's "Bash restriction" section and its paired rules
file), not by a host mechanism — Claude Code's tool-grant system does not
support scoping Bash to a specific command allowlist. This is a real,
disclosed gap: a subagent could in principle run something other than the
named scripts. It is narrower than the alternative of granting broader
tools, and the subagent's role otherwise remains as constrained as before
(Validator still cannot Edit or Write; Remediator still cannot Grep, Glob,
or invoke Agent).

## Consequences

- The determinism guarantees from Phase 1 (stable finding ids, a real state
  machine, complete decision reconciliation, literal diffs) apply inside the
  Claude adapter exactly as they do in the core's single-agent default —
  the subagent split changes who calls the scripts, not whether they are
  called.
- Future adapters for other hosts must grant whatever their host's
  equivalent of "run this script" mechanism is, or fall back to the core's
  single-agent shape if they cannot.
- If a host later supports scoping Bash to an allowlist of specific
  commands, that mechanism should replace the instruction-only restriction
  described here.
