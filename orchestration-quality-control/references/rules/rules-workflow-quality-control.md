---
description: Quality-control rules for agentic workflow documents authored against workflows-template.md
globs:
  - "**/workflows/workflows-*.md"
  - "**/*.workflow.md"
alwaysApply: false
---

# Rule: Agentic Workflow Quality Control

Apply this rule when validating or correcting a workflow document authored
against `workflows-template.md`, or a generator source that produces such a
workflow document.

## Scope

- Applies to workflow files that declare an outcome, inputs, control model,
  ordered steps, and stop conditions (the `workflows-template.md` shape).
- Applies to generator sources (rules, prompts) whose instructions produce those
  workflow files, checking whether following them yields a conforming workflow.
- Does not apply to rules files, finished artifacts of a profile-defined class
  (see the selected profile's `artifact_rules`), or general production code.

## Required Context

- Read the target workflow file in full before judging it.
- Read `workflows-template.md` as the baseline shape when the reader needs the
  canonical section set.
- Preserve the workflow's stated outcome, ownership, and scope boundaries; do not
  rewrite intent while correcting form.

## Requirements

### W1 — Procedure, not policy

Flag firm "must" / "never" constraint bullets that carry no step action and
belong in a paired rules file. Keep only ordered steps and the definitional
facts a step needs to run.

### W2 — Single outcome

Require one clear outcome, stated in the frontmatter `description` and the
opening "Use this workflow to..." line. Flag a workflow that bundles several
unrelated outcomes into one file.

### W3 — Template section conformance

Require the sections `Inputs`, `Control`, `Steps`, and `Stop Conditions`, plus a
frontmatter `description`. Flag missing or renamed required sections and residual
template stubs (`<...>` angle-bracket placeholders, `TODO`, `TBD`, `FIXME`).

### W4 — Operating contract loaded first

Require the first step to bind the workflow to its governing rule or reference
before any other action. Flag a workflow whose steps act before loading a rules
contract.

### W5 — Delegation spec completeness

Require every delegated step to state an objective, an output format, tool or
source guidance, and explicit boundaries. Flag a hand-off that names a worker
without stating all four.

### W6 — Validation at transitions

Require every intermediate step output to be validated before the next step
consumes it, with a failed validation returning to the producing step. Flag a
hand-off whose output flows downstream with no validation.

### W7 — Bounded loops

Require every iteration or retry loop to state an explicit cap and a defined
fallback (escalate to a human, or stop and report). Flag an uncapped
"repeat until" loop.

### W8 — Durable cross-stage state

Require state that later steps depend on to live in a file or durable store. Flag
a step that relies on conversation context to carry state across a hand-off.

### W9 — Deterministic routing default

Require mechanical decisions to route deterministically and reserve LLM judgment
for open-ended choices. Flag a `Control` decision model that assigns LLM routing
to a decision the workflow describes as mechanical.

### W10 — Least-privilege tools

Require each delegated step to grant the minimum tool access its task needs. Flag
a delegation that grants broad or unspecified tool access.

### W11 — Approval gates owned by the orchestrator

Require human approval gates to be stated as stop conditions owned by the primary
agent. Flag a delegated step that applies or approves a gated change on a human's
behalf.

### W12 — Explicit stop conditions

Require the `Stop Conditions` section to name blocking conditions,
approval-gated actions, and scope boundaries. Flag an empty or placeholder stop
conditions section.

### W13 — No over-agentification

Require each added agent, stage, or parallel delegation to carry a stated reason
a single agent cannot do the job. Flag added delegation or parallelism with no
such justification.

## Boundaries

- Do not flag a linear single-agent workflow for absent delegation specs when its
  `Control` delegation is stated as "none"; W5–W6 apply only to hand-offs that
  exist.
- Do not treat definitional facts a step needs to run as policy leakage under W1;
  only unattached firm constraints are policy leakage.
- Do not demand validation on the `Finish` step's own returned output; W6 governs
  intermediate transitions, and the Finish step's stated verification satisfies
  it.
- Do not require a durable-state file for state fully produced and consumed inside
  a single step.
- Do not attribute a defect to an automated pipeline unless the target itself
  shows direct evidence a stage generated it; otherwise report it as a
  manual-authoring defect.
- Escalate or ask for confirmation when the target's declared type is ambiguous
  between a workflow and a rules file.

## Output

- Produce one finding per violation, each naming what is wrong, which rule it
  breaks in plain words, where it is (path plus line or section), and a concrete
  change.
- For a generator source, state whether the finding is a contradiction (the text
  pushes toward a violation) or a gap (the text omits a needed protection). When
  the generator produces a profile-defined artifact class, judge that dimension
  against the selected profile's `artifact_rules`, not against any rule packaged
  in the core.
- Include a clear statement when no problems are found.
- Omit internal rule numbers from the reader-facing report; keep them in private
  notes only.

## Verification

- Walk W1–W13 against the target, quoting a snippet and location per finding.
- Report any requirement skipped because the target set lacks the evidence to
  judge it, stated as "not verifiable from selected targets".

## References

@../templates/workflows-template.md
@rules-generator-quality-control.md
