---
name: oqc-validate
description: >
  Validate operation of orchestration quality control. Collects a target
  file, folder, or multi-select set, a profile (default core), and a report
  language, delegates to the oqc-orchestrator subagent (operation: validate),
  presents the plain-language findings report, and — if any findings exist —
  asks the user the apply choice (apply all / apply none / apply some,
  named), then hands off to oqc-execute in the same turn to resolve that
  choice. Writes a durable checkpoint only when findings exist; reports "all
  passed" and stops when there are none. Use whenever the user runs
  `/oqc-validate`, asks for orchestration quality control, or wants to check
  a workflow, orchestrator, rules, or generator-source document — even if
  they do not say "skill" or name an operation. For Aplicatudo E2E/Maestro
  artifact checks, pass `profile: aplicatudo-e2e`. Do not use this skill to
  apply fixes to an existing checkpoint — that is `oqc-execute`.
license: MIT
model: sonnet
effort: high
compatibility: >
  Claude Code only. Delegates to the oqc-orchestrator subagent
  (.claude/agents/), which itself delegates to oqc-validator — both require
  the Agent tool and per-subagent tool restriction — not available in
  Cursor. See adapters/claude/README.md for the capability matrix and what a
  reduced-capability host must disclose instead.
---

# oqc-validate

This skill is the main-session half of the validate operation. It never
reads target content or the packaged rule sets itself — all of that lives
inside the `oqc-orchestrator` subagent and, beneath it, the `oqc-validator`
subagent. This skill's own job is collecting input, delegating, and — since
the orchestrator subagent cannot ask the user anything — presenting the
result and asking the apply-choice question.

## Steps

1. Collect inputs via UI (one question at a time):
   - `targets`: a single file path, a folder path, or a multi-select set.
     Do not proceed until at least one readable target path is confirmed.
   - `profile`: rule profile, default `core`. Offer `aplicatudo-e2e` when
     the user's phrasing suggests Aplicatudo/Maestro E2E work.
   - `language`: report language, default suggestion English.

2. Delegate to the `oqc-orchestrator` subagent (Agent tool,
   `subagent_type: oqc-orchestrator`). State the delegation plainly:
   - Objective: run the validate operation (`operation: validate`) for
     `targets`, `profile`, and `language`.
   - Output format: either `{ status: "all_passed" }`, or `{ report,
     findings, checkpoint_path }`, findings conforming to
     `references/schemas/finding.schema.json`.
   - Tool guidance: the subagent has `Agent`, `Read`, `Write`, and `Bash`
     restricted to the package's `scripts/`.
   - Boundaries: it may read only `targets` and the packaged rule files; it
     must not be asked to decide anything or ask the user anything.

3. Handle the return:
   - `all_passed` → report this to the user in chat. Stop; there is nothing
     further to do.
   - `report` + `findings` + `checkpoint_path` → present the plain-language
     report in chat (do not save it to a file unless the user asks). Then
     ask via UI: apply all suggested changes / apply none / apply some (I
     will name which findings). If there are no findings, this branch
     cannot occur — see `all_passed` above.
   - Anything else (a `blocked` payload, or a return missing `report`,
     `findings`, or `checkpoint_path`) → stop and relay the blocked
     payload's `reason_code`, `detail`, and `recovery_action` verbatim
     rather than guessing at a report to show.

4. Hand off to execute, in the same turn:
   - Invoke `oqc-execute` with the `checkpoint_path` from step 2 and the
     resolved `decision` from step 3 (`all`, `none`, or the named finding
     ids).
   - Present whatever `oqc-execute` returns to the user; this skill's own
     job ends there.

## Operating rules

- Never call `Edit` or `Write` on a target file yourself; only the
  Remediator subagent (inside the execute operation) does that.
- Never fabricate or reinterpret a finding; relay exactly what the
  orchestrator subagent returned.
- If the orchestrator subagent's return is missing `report`, `findings`, or
  `checkpoint_path` when it isn't `all_passed`, stop and report the
  malformed return rather than guessing at a report to show.
