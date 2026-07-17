# ADR 0002 — Anchor portability on the Agent Skills open standard, not OpenSkills

## Status

Accepted, 2026-07-16.

## Context

The original architecture report cited the OpenSkills project
(`github.com/numman-ali/openskills`) as the portability target, including
two links into an `_autodocs/` directory for the `SKILL.md` format and
installation conventions. Both links returned HTTP 404 when checked during
the adversarial critique. OpenSkills' own README describes itself as an
implementation of Anthropic's Agent Skills specification — a separate,
published open standard (`github.com/agentskills/agentskills`, released
December 2025) that defines `SKILL.md`'s required frontmatter (`name` and
`description` only), the progressive-disclosure loading model, and the
optional `scripts/`, `references/`, and `assets/` directories a skill may
contain.

## Decision

This package's `SKILL.md` frontmatter carries only `name`, `description`,
and `license` — the fields the Agent Skills specification actually
requires or the license convention it documents — rather than the fuller
Claude-specific frontmatter (`model`, `effort`, `compatibility`, versioned
`metadata`) the legacy v3 skills carried. Host-specific concerns (model
selection, tool grants, subagent definitions) move to `adapters/claude/`
instead of living in the portable `SKILL.md`.

OpenSkills remains a valid, and currently the most common, way to install
this package into a non-Claude host. It is treated as one supported
installer implementing the open standard, not as the standard itself.

## Consequences

- The core `SKILL.md` should remain loadable by any host that implements
  the Agent Skills specification, not only OpenSkills-based hosts.
- The `scripts/` directory's presence and role (deterministic Python,
  called by the skill's own instructions) follows a convention the open
  standard explicitly documents, rather than being a bespoke addition this
  package invented.
- Future changes to `SKILL.md`'s frontmatter should be checked against the
  Agent Skills specification, not against Claude Code's superset of it.
