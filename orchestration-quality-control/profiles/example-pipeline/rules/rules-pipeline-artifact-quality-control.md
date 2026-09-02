---
description: Quality-control rules for finished example-pipeline artifacts
globs:
  - "**/*.pipeline.yaml"
  - "**/*.pipeline.yml"
  - "**/*.pipeline.data.yaml"
  - "**/*.pipeline.data.yml"
alwaysApply: false
---

# Rule: Pipeline Artifact Quality Control

Apply this rule when validating a finished pipeline artifact or its companion
data file. This rule belongs to the `example-pipeline` profile; it is loaded
only when that profile is selected, via its `profile.json` manifest's
`artifact_rules`.

## Scope

- Applies to finished `*.pipeline.yaml` / `*.pipeline.yml` files and optional
  `*.pipeline.data.yaml` / `*.pipeline.data.yml` companions.
- Does not apply to generator sources that produce these artifacts (see the
  core's `rules-generator-quality-control.md`, which consumes this file via
  the profile manifest), to a rules file's own authoring form, or to workflow
  or orchestrator documents.

## Required Context

- Read the target artifact in full before judging it.
- Judge only from the selected target set; do not open sibling files outside
  the selection to confirm a finding.

## Requirements

### P1 — Bounded retry

Every job must declare `retry` as a non-negative integer.

### P2 — Explicit approval

Pipeline `approval` must be present and must be exactly `required` or `none`.

### P3 — Secret references only

Job `secrets` entries must use `ref:` names. Flag a literal `value:` (or any
inline secret string) as a violation.

### P4 — No disconnected jobs

In a target set with more than one job, flag a job that has no `needs` and is
not listed in any other job's `needs`. A normal graph has exactly one root
(no `needs`) that other jobs reference; a second job with no `needs` and no
incoming reference is disconnected.

### P5 — Env data placement

Env and config values belong in a companion `*.pipeline.data.yaml` file, not
inline on the pipeline file. Flag a pipeline-level `env:` mapping on a
`*.pipeline.yaml` target.

### P6 — Named durable state

`state.store` must be a non-empty path. Omitting `state`, omitting `store`,
or pointing the store at `conversation` or `memory` is a violation.

## Suggested change shape

Each finding's `suggested_change` is a `{before, after}` span quoting
verbatim text from the target. Do not invent a rewrite that cannot be
located in the file.
