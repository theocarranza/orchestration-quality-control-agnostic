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

Produce and execute the concise [master plan](../../Implementation_Plans/2026-09-04-original-design-realignment-master-plan.md). First implement the smallest executable kernel: contracts, append-only mailbox, pure reducer/routing/compiler/gate/retry behavior, replay/verify, and a model-free two-task proof. Follow with one real host orchestration slice before broad migration or benchmarking.

## Acceptance

- The master plan records five outcomes, exit evidence, non-goals, fixed-vs-generated distinction, and required sources.
- Kernel and adapter slices have executable tests and captured evidence; agents cannot mutate state directly.
- Root lifecycle, legal envelope pairs, hashes, retries, blockers, and adapter enforcement are observable and replayable.
- Documentation describes install → discover → interview → build/run; prose or line-count gates do not substitute for code evidence.

## References

- Binding [architecture ruling](../../../.superpowers/sdd/refactor-align-the-architecture-with-original-design/architecture-ruling.md)
- [ADR 0013](../../Architecture/ADR/0013-three-agent-parameterized-code-gated.md)
- Paused [4.0.0 plan](../../Implementation_Plans/2026-09-02-return-to-intention-4-0-0.md) and [ledger](../../Implementation_Plans/2026-09-02-return-to-intention-ledger.md)
- [Current session](../../Agent_Sessions/2026-09-04-032820-architecture-realignment.md) and prior [implementation session](../../Agent_Sessions/2026-09-02-212024-implement-4-0-0-orchestration.md)
- [agentic-e2e-test-workflow@775e57b](https://github.com/theocarranza/agentic-e2e-test-workflow/tree/775e57beaa28441be6657aebba9bb655d717d3c9) and [hierarchical-multi-agent-orchestrator@3efc011](https://github.com/theocarranza/hierarchical-multi-agent-orchestrator/tree/3efc011eef3c38d5e239a46fdac79b8d011cf0fa)
- Current host references: [Claude agents](https://github.com/anthropics/claude-code/blob/main/plugins/plugin-dev/skills/agent-development/SKILL.md), [Cursor subagents](https://cursor.com/docs/subagents), [OpenAI GPT-5.4 Mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
