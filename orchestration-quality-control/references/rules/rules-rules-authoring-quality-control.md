---
description: Rule-authoring form for orchestration quality-control rules files
globs:
  - "**/rules/rules-*.md"
alwaysApply: false
---

# Rule: Rules-File Authoring Quality Control

Apply this rule when validating or correcting a rules file's own authoring
form — whether its policy bullets are written as firm, rationale-free,
independently verifiable constraints.

## Scope

- Applies to rules files: any document whose purpose is to state policy for
  another agent or process to follow.
- Does not apply to finished artifacts (a profile's concern, see the selected
  profile's `artifact_rules`), generator-source content coverage (see
  `rules-generator-quality-control.md`), workflow documents, or orchestrator
  documents — those have their own authoring-form checks.

## Required Context

- Read the target rules file in full before judging it.
- Read `rules-template.md` as the baseline shape when the reader needs the
  canonical section set.

## Requirements

### R1 — Firm imperative form

State each constraint as a firm imperative sentence. Flag procedural or
narrative prose that is not a policy constraint.

### R2 — No rationale clauses

Carry no rationale clause in a rule bullet. Flag "because", "so that", "which
allows", "is not findable by", and equivalent explanatory fragments.

### R3 — No sequencing language

Keep sequencing, ordering, and "first/then" language out of the rules file.
Sequencing belongs in the paired workflow file.

### R4 — Actionable without a trailing explanation

Flag a rule bullet that needs a trailing explanation to be actionable as
under-specified. Require a plain assertion, or a split into two rules.

### R5 — Definitional facts only

Keep definitional facts required to identify when a rule applies. Flag
justifications for why the rule exists.

### R6 — Independently verifiable

Require every rule bullet to be independently verifiable without
cross-referencing prose elsewhere in the same file.

## Boundaries

- Do not flag a bullet's definitional facts (the conditions that identify when
  it applies) as rationale under R2; only explanatory fragments about why the
  rule exists are in scope.
- Do not flag a timing or state-based qualifier (e.g. "only after X passes")
  as sequencing under R3 unless it describes a multi-step recipe of actions in
  order.

## Output

- Produce one finding per violation, each naming what is wrong, which
  requirement it breaks in plain words, where it is (path plus line or
  section), and a concrete rewrite.
- Include a clear statement when no problems are found.
- Omit internal rule numbers from the reader-facing report; keep them in
  private notes only.

## Verification

- Walk R1–R6 against the target's rule bullets, quoting the offending text and
  location per finding.
- Confirm the rewrite suggested for each finding would itself pass R1–R6.

## References

@../templates/rules-template.md
