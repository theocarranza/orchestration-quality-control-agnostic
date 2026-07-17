---
template_id: isolated-three-agent
template_version: 1
description: Host-isolated Orchestrator, Validator, and Remediator architecture
derived_from:
  - adapters/claude/agents/oqc-orchestrator.md
  - adapters/codex/agents/oqc_codex_orchestrator.toml
  - adapters/cursor/agents/oqc_cursor_orchestrator.md
  - docs/adr/0006-codex-nested-adapter.md
  - docs/adr/0007-cursor-native-adapter.md
---

# Reference Architecture: Isolated Three-Agent

Use this template only when the host can enforce separate capabilities and the
caller records why a single agent is insufficient.

## Inputs

- Explicit target set, workspace boundary, profile, and output contract.
- A written isolation reason tied to tool or context boundaries.
- Human decisions collected by the root session and passed as data.

## Workers

| Worker | Responsibility | Minimum tools | Returns |
| --- | --- | --- | --- |
| Orchestrator | Routing, gates, durable state, structural validation | Worker delegation, checkpoint scripts | Structured operation result |
| Validator | Read and judge untrusted targets | Read/search plus classification/id scripts | Findings and report |
| Remediator | Apply exact approved changes | Read/edit plus diff/application script | One outcome per approved item |

The root session owns user interaction. It spawns exactly one Orchestrator;
the Orchestrator invokes Validator or Remediator and receives control after
every worker return. Workers never hand work directly to each other.

## Control

- The Orchestrator never reads or authors worker artifacts.
- Every delegation states objective, output shape, tool guidance, and boundaries.
- Mechanical routing is code-enforced; semantic judgment stays with Validator.
- Validator is mechanically read-only. Remediator receives no approval authority.

## Gates

1. Adapter gate — named agents and required nesting/tool isolation are available.
2. Validation gate — every Validator return is schema-conformant; one corrective
   retry is allowed.
3. Approval gate — only the root session asks; a durable checkpoint protects it.
4. Application gate — Remediator receives exactly the approved set.
5. Reconciliation gate — every approved item is applied or skipped with reason.
6. Verification gate — the resulting orchestration is validated again.

## State

- The Orchestrator alone creates and closes durable checkpoints.
- `pending_approval` is the only active-run signal.
- Hand-offs contain resolved inputs, decisions, artifact paths, and hashes—not
  accumulated transcripts.

## Steps

1. Root collects inputs and delegates a complete operation to Orchestrator.
2. Orchestrator delegates validation and structurally gates the return.
3. Root presents the result and collects the human decision.
4. Orchestrator resolves the decision and delegates exact application.
5. Orchestrator reconciles outcomes and closes state.
6. Root presents the final and post-verification reports.

## Stop Conditions

- Block rather than fall back when named roles or isolation are unavailable.
- Stop on malformed worker output after one retry.
- Stop before mutation without an explicit root-owned decision.
- Never allow worker-to-worker handoff, broad tool grants, or unbounded retries.
