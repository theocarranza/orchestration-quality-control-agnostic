---
title: Align architecture with original design
date: 2026-09-04
type: ticket
status: active
priority: high
plan: "[[2026-09-04-original-design-realignment-master-plan]]"
session: "[[2026-09-04-032820-architecture-realignment]]"
---

# Align architecture with original design

## Purpose

Realign the product after its core ideas were diluted across several projects. The product must help a user explore a codebase, conduct a short interview, and build and manage an agent-driven workflow.

## Principles

- Deterministic tooling is the central mechanism.
- The fixed control plane is root/interviewer → one Orchestrator → isolated execution agents.
- Workflow DAGs, roles, capabilities, schemas, tools, and model/reasoning tiers are generated from discovery; the product is vendor-agnostic.
- Adapters contain host-specific details and enforce observable boundaries.
- Mailbox envelopes and an event-derived state machine provide isolation, observability, resilience, and self-healing. Root observes after the one Orchestrator is spawned and is contacted only for results, blockers, or engine-declared user input.

## Deliverable

Audit the current design and produce the concise [master plan](../../Implementation_Plans/2026-09-04-original-design-realignment-master-plan.md) that will govern later implementation. The plan must establish the smallest executable kernel first, followed by one real host orchestration slice before broad migration or benchmarking.

## Acceptance

- The master plan records five outcomes, exit evidence, non-goals, fixed-vs-generated distinction, and required sources.
- The plan records the fixed control plane versus generated workflow, five outcomes with exit evidence, explicit non-goals, and required durable and external references.
- The audit identifies the absent engine claims, fixed-output conflict, lifecycle/state, isolation, recovery, hooks, and delivery misalignments without treating prose as implementation evidence.
- The ticket remains active as the planning source; future kernel and adapter implementation is governed by the plan, not required for this ticket's completion.

## References

- [ADR 0013](../../Architecture/ADR/0013-three-agent-parameterized-code-gated.md)
- Paused [4.0.0 plan](../../Implementation_Plans/2026-09-02-return-to-intention-4-0-0.md) and [ledger](../../Implementation_Plans/2026-09-02-return-to-intention-ledger.md)
- [Current session](../../Agent_Sessions/2026-09-04-032820-architecture-realignment.md) and prior [implementation session](../../Agent_Sessions/2026-09-02-212024-implement-4-0-0-orchestration.md)
- [agentic-e2e-test-workflow@775e57b](https://github.com/theocarranza/agentic-e2e-test-workflow/tree/775e57beaa28441be6657aebba9bb655d717d3c9) and [hierarchical-multi-agent-orchestrator@3efc011](https://github.com/theocarranza/hierarchical-multi-agent-orchestrator/tree/3efc011eef3c38d5e239a46fdac79b8d011cf0fa)
- Current host references: [Claude subagents](https://code.claude.com/docs/en/sub-agents), [Cursor subagents](https://cursor.com/docs/subagents), [Codex subagents](https://developers.openai.com/codex/subagents), [OpenAI GPT-5.4 Mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
