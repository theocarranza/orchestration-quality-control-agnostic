# AI Codex Orchestrator QC Plugin

Software / Agile Project Vault.

This vault is a project knowledge base for agent sessions, ticket ledgers, architecture notes, and distilled implementation knowledge. The governing archetype is recorded in `.codex-vault.json`.

## Taxonomy

- **Knowledge/** — Permanent distilled knowledge notes (patterns, domains, references) + the knowledge MOC
- **Tickets/Active/** — In-flight ticket ledgers
- **Tickets/Ready/** — Groomed, ready-to-start tickets
- **Tickets/Closed/** — Merged/closed, awaiting release
- **Tickets/Resolved/** — Shipped/archived ticket ledgers
- **Features/** — Feature specifications and implementation detail
- **Architecture/** — High-level architecture overviews (subfolders below for ADRs/patterns/etc.)
- **Architecture/ADR/** — Architecture Decision Records
- **Architecture/Patterns/** — Recurring design patterns
- **Architecture/Infrastructure/** — Structural/infra definitions
- **Architecture/Agent-Governance/** — Agent governance protocols and directives
- **Architecture/Protocols/** — Operational protocols
- **Agent_Sessions/** — Operational journal of agent sessions (doubly-linked chain)
- **Agent_Reports/** — Formal agent-generated reports
- **assets/** — Images and binary attachments
- **Meta/** — Templates, scripts, and vault plumbing

## Entry Points

- [[Knowledge/Agent_Orientation]]
- [[Agent_Sessions/README]]
- [[Tickets.base]]
- [[Features.base]]
- [[Agent_Sessions.base]]
