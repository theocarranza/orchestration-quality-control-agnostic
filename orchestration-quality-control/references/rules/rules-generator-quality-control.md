---
description: Quality-control rules for generator sources (rules, workflows, prompts) that produce profile-defined artifacts
globs:
  - "**/rules/rules-*.md"
  - "**/workflows/workflows-*.md"
  - "**/*.prompt.md"
alwaysApply: false
---

# Rule: Generator-Source Quality Control

Apply this rule when validating a generator source — a rules file, workflow
file, or prompt that instructs an agent to produce artifacts — for whether
following it would cause the produced artifacts to break the applicable
artifact quality rules.

## Scope

- Applies to rules files, workflow files, and prompt files whose content
  instructs the creation of any artifact class a selected profile defines.
- Does not apply to the finished artifacts themselves (judge those against the
  selected profile's `artifact_rules`), to a rules file's own authoring form
  (`rules-rules-authoring-quality-control.md`), or to a workflow's own
  authoring form (`rules-workflow-quality-control.md`).
- Requires a profile to be selected for its G2/G3 checks to apply to any
  artifact class: the core alone packages no artifact rules of its own. When
  no profile is selected, a generator source that produces only core document
  types (workflows, orchestrator documents, rules files) is still checked —
  against `rules-workflow-quality-control.md`, `rules-orchestrator-quality-control.md`,
  and `rules-rules-authoring-quality-control.md` respectively — but a generator
  claiming to produce a profile-defined artifact type with no profile selected
  returns `blocked` (`unknown_profile`) rather than being judged against no
  rule set.

## Required Context

- Read the target generator source in full before judging it.
- When a profile is selected, read every rule file the profile's
  `profile.json` manifest lists under `artifact_rules` — that is the packaged
  set a produced artifact of that profile's classes must satisfy. This is the
  only place a generator-source artifact rule set is named; it is never
  hardcoded to one profile in this file.
- Judge from the generator text alone; do not open example output files unless
  those outputs were also selected as targets.

## Requirements

### G1 — Produced-type inventory

Identify every artifact type the generator is meant to produce or shape before
judging it against any downstream rule.

### G2 — Contradiction

Flag an instruction that would lead an agent to break a packaged artifact
rule — drawn from the selected profile's `artifact_rules` — for a type this
generator produces.

### G3 — Gap

Flag a generator responsible for an artifact type covered by a packaged rule
in the selected profile's `artifact_rules`, when the text never requires or
protects that rule and nothing in the text prevents the resulting violation.

### G4 — Alignment has no invented gaps

Do not record a contradiction or a gap for an artifact type the generator does
not claim to produce.

## Boundaries

- Do not fail a generator only because it is short, if it does not produce the
  risky artifact type.
- Do not require the generator to restate every packaged rule word for word;
  enough guidance that a careful agent would not break the rule satisfies G3.
- Do not open other generator stages unless the user selected them too.
- Do not judge G2/G3 against any profile's `artifact_rules` other than the
  one currently selected; a generator source is judged against exactly one
  profile's artifact vocabulary per run.

## Output

- For each finding, state whether it is a contradiction (G2) or a gap (G3),
  quote the generator passage, and suggest a concrete rewrite of the generator
  text — not of a missing output file.
- State clearly when a generator is aligned, with no material contradiction or
  gap, for every type it produces.

## Verification

- Walk G1–G4 against the target, quoting a passage and location per finding.
- Report any packaged artifact rule skipped because the generator's produced
  types do not cover it.

## References

@../templates/rules-template.md
@../schemas/profile-manifest.schema.json
