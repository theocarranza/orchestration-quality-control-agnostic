---
description: Quality-control rules for orchestrator documents that coordinate a multi-stage agentic workflow
globs:
  - "**/orchestrator*.prompt.md"
  - "**/rules-*-orchestrator.md"
  - "**/workflows-*-orchestrator*.md"
alwaysApply: false
---

# Rule: Agentic Orchestrator Quality Control

Apply this rule when validating or correcting an orchestrator document — a
standalone orchestrator document, a rules file, a workflow file, or a prompt
that defines the coordinating agent of a multi-stage agentic workflow — or a
generator source that produces such a document.

## Scope

- Applies to documents that define an agent which decomposes work, routes it
  across stages or workers, validates their outputs, and decides progression.
- Applies to generator sources (rules, prompts) whose instructions produce
  those orchestrator documents, checking whether following them yields a
  conforming orchestrator.
- Does not apply to single-stage worker documents, finished artifacts of a
  profile-defined class (see the selected profile's `artifact_rules`), or
  general production code.
- An orchestrator workflow authored against `workflows-template.md` is also
  subject to `rules-workflow-quality-control.md`; this rule set adds the
  orchestration-pattern requirements. A standalone orchestrator document
  authored against `orchestrator-template.md` is subject to this rule set
  alone.

## Required Context

- Read the target orchestrator document in full before judging it.
- Read the paired orchestrator rules or workflow file only when it is in the
  selected target set.
- Preserve the orchestrator's stated stage order, gates, and scope boundaries;
  do not rewrite the pipeline while correcting form.

## Requirements

### O1 — Orchestrator never authors

Require the orchestrator's own actions to be limited to decomposing, routing,
delegating, validating, synthesizing, and deciding. Flag an orchestrator step
that writes or edits an artifact its workers produce.

### O2 — Control returns to the orchestrator

Require control to return to the orchestrator after every delegated step. Flag
a worker granted choice of its own target, mode, or approval. Flag a
worker-to-worker hand-off that bypasses the orchestrator.

### O3 — Complete delegation specs

Require every delegation to state an objective, an output format, tool or
source guidance, and explicit boundaries. Flag a delegation missing any of the
four.

### O4 — Validate before consuming

Require every worker output to be validated before the next stage consumes it.
Require a failed validation to return to the producing stage. Flag an output
that flows downstream unvalidated or a failure the document lets propagate.

### O5 — Capped loops with a defined fallback

Require every iteration or retry loop to state an explicit cap and a defined
fallback (escalate to a human, or stop and report). Flag an uncapped loop and a
cap with no stated fallback.

### O6 — Durable, resumable state

Require state that must persist across stages to live in a file or equivalent
durable store. Require a checkpoint at each human gate such that approval
resumes the pipeline without replaying completed stages. Flag state carried
only in conversation context.

### O7 — Deterministic routing for mechanical decisions

Require decisions the document defines mechanically (stage order, path and
queue derivation, fingerprint or hash computation, suite commands) to be routed
by code or fixed rule. Reserve LLM judgment for decisions the document defines
as open-ended (gate validation, failure classification, regeneration deltas).
Flag LLM routing assigned to a mechanical decision.

### O8 — Least-privilege stage tools

Require each stage or worker to be granted the minimum tool access its task
needs. Flag broad or unspecified tool grants. Flag execution tools granted to
a stage the document defines as non-executing.

### O9 — Approval gates owned by the orchestrator

Require every human approval gate to be held by the orchestrator and to name
the action it guards. Flag a delegated stage that applies or approves a gated
change on a human's behalf.

### O10 — Justified agent count

Require every agent, stage, or coordination pattern beyond a single agent to
carry a stated reason a single agent cannot do the job. Flag an agent whose
task another agent in the same document already covers. Flag handoff or
group-chat coordination patterns.

### O11 — Compacted context between stages

Require stage hand-offs to pass resolved inputs, decisions, and artifact paths.
Flag a hand-off that passes the accumulated transcript or the full prior
conversation to the next stage.

### O12 — Isolated concurrent workers, surfaced errors

Require concurrent workers to share no mutable state. Require worker errors to
be surfaced to the orchestrator. Flag concurrent stages writing to one store
without partitioning. Flag an instruction to suppress, absorb, or silently
retry a failure.

## Boundaries

- Do not flag orchestrator-authored control artifacts (queues, fingerprints,
  state files, checkpoints, reports of its own decisions) under O1; O1 covers
  worker work products only.
- Do not apply O2, O3, O4, O8, O11, or O12 to a document whose delegation is
  stated as "none".
- Do not flag LLM judgment at gate validation, failure classification, or
  regeneration-delta decisions under O7; those are the open-ended joints.
- Do not re-report a passage already recorded under the workflow
  quality-control rules for the same target; record only the
  orchestration-specific violation it adds.
- Do not attribute a defect to an automated pipeline unless the target itself
  shows direct evidence a stage generated it; otherwise report it as a
  manual-authoring defect.
- Escalate or ask for confirmation when it is ambiguous whether the target
  defines an orchestrator or a worker stage.

## Output

- Produce one finding per violation, each naming what is wrong, which rule it
  breaks in plain words, where it is (path plus line or section), and a
  concrete change.
- For a generator source, state whether the finding is a contradiction (the
  text pushes toward a violation) or a gap (the text omits a needed
  protection).
- Include a clear statement when no problems are found.
- Omit internal rule numbers from the reader-facing report; keep them in
  private notes only.

## Verification

- Walk O1–O12 against the target, quoting a snippet and location per finding.
- Report any requirement the target set lacks evidence to judge as skipped,
  stated as "not verifiable from selected targets".

## References

@../templates/orchestrator-template.md
@rules-workflow-quality-control.md
