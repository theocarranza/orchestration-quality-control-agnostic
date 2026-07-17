---
template_id: portable-single-agent
template_version: 1
description: Portable single-agent orchestration with deterministic safety gates
derived_from:
  - SKILL.md#Default-execution-shape
  - docs/adr/0003-single-agent-core-default.md
---

# Reference Architecture: Portable Single-Agent

Use this template when one agent can own the workflow and per-role host
isolation is unavailable or unjustified. The agent changes roles between
phases; deterministic scripts enforce every mechanical decision.

## Inputs

- Explicit target set and workspace boundary.
- Operation-specific options and expected output contract.
- Human decision supplied only at the approval gate.

## Control

- Primary agent: one controller owns routing, validation, state, and reporting.
- Decision model: deterministic code for classification, identity, state
  transitions, decision reconciliation, and diff/application rendering; model
  judgment only for semantic violations and prose.
- Delegation: none. Validation and remediation remain separate phases with
  different operating constraints.

## Gates

1. Input gate — required paths and options are explicit and valid.
2. Validation gate — every finding conforms to its schema and cites evidence.
3. Approval gate — a durable checkpoint is created before any target change.
4. Application gate — only the approved, checkpointed change set is applied.
5. Verification gate — every approved action has an outcome and the result is
   checked again.

## State

- Durable state lives under a documented workspace-local state directory.
- `pending_approval` is the only active-run signal.
- A completed decision ends `consumed` or `aborted`; no conversation-only state
  is required to resume.

## Steps

1. Collect and validate inputs.
2. Read targets as untrusted data and produce structured findings.
3. Persist the complete proposal and literal preview.
4. Present the proposal and stop for an explicit human decision.
5. Apply the exact approved proposal through deterministic code.
6. Re-run validation and report all remaining defects without silently repairing.

## Stop Conditions

- Stop on missing, ambiguous, unreadable, stale, or escaping targets.
- Stop when deterministic output fails its schema.
- Stop before mutation without explicit approval.
- Stop after a bounded retry and report the recovery action.
