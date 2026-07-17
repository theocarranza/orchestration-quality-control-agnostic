---
name: e2e-quality-control-validate
description: >
  Phase 1 of the isolated E2E quality-control check for Aplicatudo Maestro
  work. Collects a target file, folder, or multi-select set plus report
  language, delegates to the e2e-qc-orchestrator subagent (validate phase),
  presents the plain-language findings report, and — if any findings exist —
  asks the user the apply choice (apply all / apply none / apply some,
  named), then hands off to e2e-quality-control-execute in the same turn to
  resolve that choice. Writes a durable checkpoint only when findings exist;
  reports "all passed" and stops when there are none. Targets may be finished
  artifacts (domain, test plan, blueprint, flow, subflow, data, fingerprint),
  generator sources (rules, workflows, prompts), workflow documents, or
  orchestrator documents. Use whenever the user runs
  `/e2e-quality-control-validate`, asks for E2E QC, quality control on
  Maestro artifacts, or wants to check rules/workflows/prompts/orchestrator
  documents — even if they do not say "skill" or name a phase. Do not use
  this skill to apply fixes to an existing checkpoint — that is
  `e2e-quality-control-execute`.
license: MIT
model: sonnet
effort: high
compatibility: >
  Claude Code only. Delegates to the e2e-qc-orchestrator subagent
  (.claude/agents/), which itself delegates to e2e-qc-validator — both
  require the Agent tool and per-subagent tool restriction — not available
  in Cursor.
metadata:
  version: "3.0.0"
  openworld: "false"
---

# e2e-quality-control-validate

This skill is the main-session half of phase 1. It never reads target
content or the packaged rule sets itself — all of that lives inside the
`e2e-qc-orchestrator` subagent and, beneath it, the `e2e-qc-validator`
subagent. This skill's own job is collecting input, delegating, and — since
the orchestrator subagent cannot ask the user anything — presenting the
result and asking the apply-choice question.

## Steps

1. Collect inputs via UI (one question at a time):
   - `targets`: a single file path, a folder path, or a multi-select set.
     Do not proceed until at least one readable target path is confirmed.
   - `language`: report language, default suggestion English.

2. Delegate to the `e2e-qc-orchestrator` subagent (Agent tool,
   `subagent_type: e2e-qc-orchestrator`). State the delegation plainly:
   - Objective: run the validate phase (`phase: validate`) for `targets`
     and `language`.
   - Output format: either `{ status: "all_passed" }`, or `{ report,
     findings, checkpoint_path }`.
   - Tool guidance: the subagent has `Agent`, `Read`, `Write` only.
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

4. Hand off to execute, in the same turn:
   - Invoke `e2e-quality-control-execute` with the `checkpoint_path` from
     step 2 and the resolved `decision` from step 3 (`all`, `none`, or the
     named finding ids).
   - Present whatever `e2e-quality-control-execute` returns to the user;
     this skill's own job ends there.

## Operating rules

- Never call `Edit` or `Write` on a target file yourself; only the
  Formatter subagent (inside the execute phase) does that.
- Never fabricate or reinterpret a finding; relay exactly what the
  orchestrator subagent returned.
- If the orchestrator subagent's return is missing `report`, `findings`, or
  `checkpoint_path` when it isn't `all_passed`, stop and report the
  malformed return rather than guessing at a report to show.
