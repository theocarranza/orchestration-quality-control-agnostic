# e2e-quality-control

Isolated quality gate for Aplicatudo E2E (Maestro) work. Checks a selected
target — a finished artifact, a generator source, a workflow document, or an
orchestrator document — against packaged rule sets, reports findings in plain
language, and applies only the fixes the user explicitly approves.

This directory is a **shared library**, not an invocable skill itself. It
holds the rule sets, templates, and plain-language pass shared by the two
skills that actually run: `e2e-quality-control-validate` and
`e2e-quality-control-execute` (their own directories, siblings of this one).

## Document taxonomy

The skill enforces exactly two document shapes on everything it produces or
consults.

```text
        rules file                     workflow file
   (rules-template.md)             (workflows-template.md)
   ---------------------           ---------------------
   states policy:                  states procedure:
   firm constraints,                ordered steps,
   no rationale,                    one outcome,
   no sequencing                    stop conditions
```

A **rules file** and a **workflow file** are always paired — one names the
policy, the other names the steps that apply it. This includes the
orchestrator itself: `rules-e2e-qc-orchestrator.md` pairs with two workflow
files (`workflows-e2e-qc-orchestrator-validate.md` and `-execute.md`, one per
phase — see below for why two, not one). An earlier revision of this skill
had a third, standalone "orchestrator document" shape with no rules pair;
that shape is retired for this skill (see "Why the orchestrator became a
subagent" below), though `orchestrator-template.md` remains in
`templates/` for any hypothetical future use elsewhere in this repo.

## What gets checked, and by what

| Target class                                                                       | Rule file                                            | What it checks                                                    |
| ---------------------------------------------------------------------------------- | ---------------------------------------------------- | ----------------------------------------------------------------- |
| Finished artifact (domain, test plan, blueprint, flow, subflow, data, fingerprint) | `rules-e2e-artifact-quality-control.md` (R1–R9)      | Structure and content of the artifact itself                      |
| Rules file                                                                         | `rules-e2e-rules-quality-control.md` (R1–R6)         | Whether the rules file is authored as firm, rationale-free policy |
| Generator source (a rules/workflow/prompt that produces artifacts)                 | `rules-e2e-generator-quality-control.md` (G1–G4)     | Whether following it would break the artifact rules               |
| Workflow document                                                                  | `rules-e2e-workflow-quality-control.md` (W1–W13)     | Authoring form and orchestration-adjacent design                  |
| Orchestrator document                                                              | `rules-e2e-orchestrator-quality-control.md` (O1–O12) | Orchestration pattern: delegation, gates, state, tool scope       |

A target may belong to more than one class at once (a workflow file that is
also the orchestrator is checked against both W-rules and O-rules, with a
one-passage-one-record rule to avoid double-reporting).

## Component architecture

Three tool-scoped subagents, coordinated across **two separate skill
invocations**. No component can do another's job — the restriction is
enforced by the harness (`tools:` frontmatter), not just written as a rule.
This includes the orchestrator itself now, which is why the run is split
into two phases: subagents have no `AskUserQuestion` access, so the
orchestrator cannot hold the apply gate itself — the calling main session
does, between the two invocations.

```text
        user runs /e2e-quality-control-validate
                       |
                       v
        +---------------------------+
        | e2e-quality-control-validate|  main session:
        | SKILL.md                   |  collects targets + language,
        +---------------------------+  delegates, then asks the gate
                       |
                       v  phase: validate
        +---------------------------+
        |   e2e-qc-orchestrator      |  subagent
        |   tools: Agent, Read, Write|  model: opus, high
        |   never reads/edits targets|
        |   never asks the user      |
        +---------------------------+
             |                  ^
             | delegate         | findings + report
             | targets          |
             v                  |
        +---------------------------+
        |   e2e-qc-validator         |  subagent
        |   tools: Read, Grep, Glob  |  model: sonnet, high
        +---------------------------+
                       |
                       v  (findings exist)
        +---------------------------+
        |  write checkpoint + marker |
        |  to state/                 |
        +---------------------------+
                       |
                       v
        +---------------------------+
        |  UI gate (main session):   |
        |  apply all / some / none   |
        +---------------------------+
                       |
                       v  same-turn hand-off
        user runs /e2e-quality-control-execute
                       |
                       v
        +---------------------------+
        | e2e-quality-control-execute |  main session:
        | SKILL.md                   |  resolves decision,
        +---------------------------+  delegates, shows final report
                       |
                       v  phase: execute
        +---------------------------+
        |   e2e-qc-orchestrator      |  subagent (same identity as above)
        |   reads checkpoint,        |
        |   resolves approved subset |
        +---------------------------+
             |                  ^
             | approved findings| edit summary
             v                  |
        +---------------------------+
        |   e2e-qc-formatter         |  subagent
        |   tools: Read, Edit        |  model: sonnet, high
        +---------------------------+
                       |
                       v
        delete checkpoint + marker -> final report to user
```

A `PreToolUse` hook (`<repo-root>/.claude/hooks/e2e-qc-block-main-edits.py`)
blocks the main session's own `Edit`/`Write` calls while the marker file
exists — so the main session can never "help" by editing a target directly
instead of properly delegating through the two skills.

## Folder layout

```text
e2e-quality-control/                    shared library, no SKILL.md
|-- README.md                           this file
|-- state/                              durable run state (marker + checkpoints; gitignored)
|-- evals/                              fixture-based eval cases (unchanged)
`-- references/
    |-- templates/                      assimilated from e2e_test/agentic-workflow/templates/
    |   |-- rules-template.md           (copy; source untouched)
    |   |-- workflows-template.md       (copy; source untouched)
    |   `-- orchestrator-template.md    (kept for hypothetical future standalone use; unused by this skill now)
    |-- rules/
    |   |-- rules-e2e-qc-validator.md            validator's own behavior rules
    |   |-- rules-e2e-qc-formatter.md            formatter's own behavior rules
    |   |-- rules-e2e-qc-orchestrator.md         orchestrator's own behavior rules
    |   |-- rules-e2e-artifact-quality-control.md      R1-R9
    |   |-- rules-e2e-rules-quality-control.md         R1-R6 (rules-file authoring)
    |   |-- rules-e2e-generator-quality-control.md     G1-G4
    |   |-- rules-e2e-workflow-quality-control.md      W1-W13
    |   `-- rules-e2e-orchestrator-quality-control.md  O1-O12
    |-- workflows/
    |   |-- workflows-e2e-qc-validator.md               validator's procedure
    |   |-- workflows-e2e-qc-formatter.md               formatter's procedure
    |   |-- workflows-e2e-qc-orchestrator-validate.md   orchestrator's validate-phase procedure
    |   `-- workflows-e2e-qc-orchestrator-execute.md    orchestrator's execute-phase procedure
    `-- plain-language/                 report-writing pass (unchanged)

e2e-quality-control-validate/SKILL.md   phase 1 entry point (sibling directory)
e2e-quality-control-execute/SKILL.md    phase 2 entry point (sibling directory)
```

## Why the orchestrator became a subagent

A single inline main-session orchestrator (this skill's original shape)
already worked. Two live QC runs against real files surfaced the reason it
had to change: every rule this skill enforces on _other_ orchestrators (O8 —
least-privilege tools) was violated by its own — its "never edits a file"
guarantee was pure written discipline, never harness-enforced, precisely
because it ran unrestricted in the main session rather than as a tool-scoped
subagent like its two workers.

Converting it outright ran into one hard blocker: subagents have no
`AskUserQuestion` access, and the orchestrator's entire reason for existing
is holding that gate. The resolution is the two-phase split above — the
orchestrator subagent never asks anything; it produces an artifact (report +
checkpoint, then an edit summary) and stops, while the UI question is asked
entirely by the calling main session, bridging the two skill invocations via
the checkpoint file.

## Why three subagents instead of one skill doing everything

Justified by concrete, checkable gains — not just architectural taste:

- **Real tool scoping**, now across all three roles. The validator
  physically cannot call `Edit`/`Write`; the formatter physically cannot
  browse the repository beyond what it's told to touch; the orchestrator
  physically cannot read or edit target content at all (`tools: Agent, Read,
Write` — `Read`/`Write` scoped in practice to its own checkpoint and
  marker bookkeeping, never a target file).
- **A stronger reasoning tier where it matters.** The orchestrator runs
  `model: opus`, `effort: high` — routing and gating a whole run benefits
  from deeper judgment than either worker's narrower, mechanical task does.
  Validator and formatter stay at `sonnet`, `high`.
- **Reuse.** A formatter that consumes `{ violation, rule, location,
suggested_change }` and nothing else is not specific to E2E quality
  control — the same shape already exists in this repo's `auto-fix-artifact`
  skill for a different domain.

## Extending this skill

To add a new checkable document class: write its rules file against
`references/templates/rules-template.md`, add its row to the table above,
and teach `workflows-e2e-qc-validator.md` to load it for the matching target
class. Do not add a new subagent unless the new work needs a genuinely
different tool grant than validator, formatter, or orchestrator already
have — see `rules-e2e-orchestrator-quality-control.md` § O10 for the bar a
new worker must clear.

## Portability note

Subagent definitions live at `projects/aplicatudo/.agents/agents/` — a flat,
project-scoped directory Claude Code discovers independently of any skill
folder (there is no supported convention for a skill to bundle its own
subagents inside its own directory). Copying just the two
`e2e-quality-control-*` skill folders elsewhere does **not** bring the three
subagents along; they'd need to be copied separately from `.agents/agents/`.
This repo has an existing `.agents/plugins/e2e-quality-control/` bundle for
distribution — packaging this skill as a proper Claude Code plugin (which
bundles skills, agents, commands, and hooks together) is the right fix if
true portability is needed, but is out of scope for this restructure.
