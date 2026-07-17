# Orchestration Quality Control

This package checks the quality of the documents that define and coordinate
an agentic process — not the code an agent writes, but the workflow files,
orchestrator documents, and rules files that tell an agent system how to
delegate work, validate results, ask for approval, keep state, and stop
safely.

Given one or more target files, it classifies each one, checks it against a
packaged set of rules, and produces two things: a list of specific findings
(what is wrong, where, and a proposed fix) and a short plain-language report
a non-technical reader can follow. Nothing is changed until a person
explicitly approves which findings to apply.

## Why this exists

This package started as part of a larger, Aplicatudo-specific system called
`e2e-quality-control`, which checked both generic orchestration problems
(missing approval gates, non-durable state, unbounded retry loops) and
Aplicatudo-specific problems (malformed Maestro test flows, misplaced
Firestore field names, and similar). Those two kinds of checks do not belong
in the same package: the generic orchestration checks are useful to anyone
building an agent workflow, while the Aplicatudo checks are useful only to
that one project.

This package keeps the generic checks as the reusable core, and moves the
Aplicatudo-specific checks into an optional add-on called a profile (see
`profiles/aplicatudo-e2e/`). Running the core with no profile selected
performs only the generic checks and has no dependency on Aplicatudo,
Maestro, or Flutter.

## How it is used

Two operations, always in this order:

1. **`validate`** — point the skill at one or more target files. It reports
   back either "nothing wrong" or a list of findings plus a durable record
   of the run (called a checkpoint) that a person can review and act on
   later, even after the conversation ends.
2. **`execute`** — given that checkpoint and a decision (apply every
   finding, apply none of them, or apply a specific named subset), the skill
   applies exactly the approved fixes and reports what changed. Anything it
   could not safely apply is reported as skipped, with a reason — never
   silently dropped and never falsely claimed as done.

## What makes the checks trustworthy

A quality-control tool is only useful if running it twice on the same input
gives the same answer, and if a fix it claims to have applied was actually
applied. Two design choices in this package exist specifically to guarantee
that:

- **The mechanical parts are ordinary code, not a language model.** Deciding
  what kind of document a file is, computing a stable identifier for each
  finding, tracking whether a review is still pending or has been resolved,
  and turning a proposed fix into an actual diff are all handled by small
  Python scripts under `scripts/`, not by asking a model to be consistent.
  Those scripts have their own automated tests that run with no model
  involved at all. A model is only ever asked to do the two things a script
  cannot: judge whether a specific passage violates a specific rule, and
  write the plain-language explanation.
- **A proposed fix must quote the file it is fixing.** Every finding has to
  include the exact text it is pointing at. If that text cannot be found in
  the file — because the finding was invented, or because someone already
  fixed it — the finding is rejected automatically, before a person ever
  sees it. This also means a target file cannot trick the system into
  approving an unwanted edit by phrasing something persuasively: proposed
  changes are always shown to the person approving them as an actual before
  and after comparison of the real file, never as a description someone has
  to take on faith.

## What is in this package

- `SKILL.md` — the entry point a host agent reads to learn how to use this
  skill.
- `scripts/` — the small, dependency-free Python programs described above,
  along with their tests.
- `references/rules/` and `references/workflows/` — the packaged policy and
  procedures the checks are built from.
- `references/schemas/` — the exact shape every finding, checkpoint, and
  input must take.
- `references/templates/` and `references/plain-language/` — shared
  document skeletons and report-writing guidance, including support for
  Brazilian Portuguese reports.
- `profiles/` — optional add-ons, such as the Aplicatudo E2E profile, that
  extend the core with domain-specific checks.
- `adapters/claude/` — how this skill runs inside Claude Code specifically,
  including the option to isolate the checking, editing, and coordinating
  roles into three separate, narrowly-permissioned agents for stronger
  guarantees than a single agent can offer on its own.

## Where runtime data lives

A checkpoint created while running this skill is never stored inside this
package. It lives in the workspace being checked, under
`.orchestration-qc/state/`, and is deleted or superseded once a review is
resolved. This keeps the package itself a fixed, shareable set of rules and
code, separate from the record of any particular run.
