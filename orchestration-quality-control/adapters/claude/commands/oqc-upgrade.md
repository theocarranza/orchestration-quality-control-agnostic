---
name: oqc-upgrade
description: >
  Guided orchestration upgrade. Collects a mechanism path, profile, language,
  apply mode, and documentation path, confirms the discovery manifest,
  delegates to the oqc-upgrade-orchestrator subagent (operation:
  upgrade_prepare), presents the plain-language report and literal preview,
  asks for an atomic approve/decline decision, then delegates upgrade_apply
  in the same turn. Use whenever the user runs `/oqc-upgrade`, asks to
  upgrade, redesign, version, normalize, or template an orchestration
  mechanism. Do not use this command for ordinary finding-by-finding QC —
  that is `oqc-validate`.
license: MIT
model: sonnet
effort: high
compatibility: >
  Claude Code only. Delegates to the oqc-upgrade-orchestrator subagent
  (.claude/agents/), which itself delegates to oqc-validator,
  oqc-proposal-author, and oqc-upgrade-applier — all require the Agent tool
  and per-subagent tool restriction. See adapters/claude/README.md for the
  capability matrix.
---

# oqc-upgrade

This skill is the main-session half of the guided-upgrade operations. It
never reads target content or drafts proposals itself — that lives inside
the `oqc-upgrade-orchestrator` subagent and its workers. This skill collects
input, confirms discovery, delegates, presents results, and records the
atomic approval decision.

## Steps

1. Collect inputs via UI (one question at a time):
   - `mechanism_path`: workspace-relative file or folder for the existing
     orchestration mechanism.
   - `profile`: rule profile, default `core`.
   - `language`: report language, default English.
   - `apply_mode`: `side-by-side` or `in-place`.
   - `output_root`: required when `apply_mode` is `side-by-side`.
   - `documentation_path`: default `<output_root or mechanism>/ARCHITECTURE.md`.

   `template_id` is fixed to `isolated-three-agent` — the only shipped
   reference architecture — and is not asked as a question.

2. Confirm discovery:
   - Run `scripts/discover_structure.py` with the workspace and
     `mechanism_path`.
   - Present the candidate count, total bytes, and file list summary.
   - Ask via UI whether to continue with this manifest. Stop on decline.

3. Delegate prepare to the `oqc-upgrade-orchestrator` subagent (Agent tool,
   `subagent_type: oqc-upgrade-orchestrator`):
   - Objective: run `operation: upgrade_prepare` with the collected inputs
     and the confirmed manifest from step 2.
   - Output format: `{ report, preview, manifest, checkpoint_path }` or a
     `blocked` payload.
   - Boundaries: it must not ask the user anything.

4. Handle the prepare return:
   - Present the plain-language report and literal preview in chat.
   - Ask via UI: approve the complete proposal / decline.
   - Relay any `blocked` payload verbatim.

5. Delegate apply in the same turn:
   - Invoke the `oqc-upgrade-orchestrator` again with `operation:
     upgrade_apply`, the `checkpoint_path`, and `decision` (`approve` or
     `decline`).
   - Present application outcomes and verification status.

## Operating rules

- Never call `Edit` or `Write` on a target or proposed destination yourself.
- Never subset or expand the proposal; the decision is atomic.
- If prepare returns without `checkpoint_path`, `preview`, or `report`, stop
  and report the malformed return.
