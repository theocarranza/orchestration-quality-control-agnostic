---
date: 2026-09-05
timestamp: 2026-09-05T03:14:18-03:00
type: session
status: open
branch: feature/original-design-realignment
previous: "[[2026-09-04-162018-outcome-1-gate-closure]]"
next: null
ticket: "[[refactor-align-the-architecture-with-original-design]]"
plan: "[[2026-09-04-original-design-realignment-master-plan]]"
handoff: "[[2026-09-04-claude-original-design-implementation-handoff]]"
skill: root-architect-execution
---

# Session — Subagent template reconciliation

Previous Session: [[2026-09-04-162018-outcome-1-gate-closure]]
Next Session: (none)

## Mandate

Owner instruction: the skill must be faithful to the orchestration and use what
it exposes, including the subagent templates. Confirm each host's real subagent
options from its own documentation, then make the skill own the role
definitions instead of restating them inline in every brief.

## Bootstrap — 2026-09-05T03:14:18-03:00

- Branch `feature/original-design-realignment`, in sync with `origin` at
  `0ed1e39`. Untracked: `.superpowers/` only.
- Outcome 2 Tasks 1 and 2 are committed and pushed. Task 2b (consolidate the
  freeze helper) and Task 3 are not started.
- The session gate fired on the predecessor note at the eight-hour boundary.
  Resolved exactly as that note documented: the gate exempts events whose
  `file_path` contains `Agent_Sessions`, which the file tools populate and a
  Bash `sed -i` does not. No policy was skipped or disabled.

## Checkpoint — subagent templates reconciled — 2026-09-05T03:14:18-03:00

```text
time: 2026-09-05T03:14:18-03:00
task: reconcile the subagent templates with the skill and the hosts
attempt: 1 of 3
worker model: none; governance text, edited at root
worker effort: not settable on this host
spec validator: not dispatched; the owner directed the change and the sources
  are each host's own published documentation
quality reviewer: not dispatched; no product-code diff
commands:
  command: diff -r .claude/skills/... .cursor/skills/...
  counts: identical, byte for byte
  command: npx --no-install markdownlint-cli2
  counts: pending below
  command: six baseline suites
  counts: not run — no Python changed; reused from the Task 2 checkpoint
commit hash: pending
next: Task 2b — consolidate the freeze helper — then Task 3
```

### What the hosts actually expose

Confirmed from each host's own documentation rather than from memory. Context7
served the Claude Code subagent reference; Cursor and Codex came from their
published docs, the Codex URL now redirecting to `learn.chatgpt.com`.

| | Claude Code | Cursor | Codex |
| --- | --- | --- | --- |
| Format | Markdown + YAML | Markdown + YAML | **TOML** |
| Model default | `inherit` | `inherit` | inherits from parent |
| Effort | **not expressible** | `model[effort=high]` | `model_reasoning_effort` |
| Read-only | omit write tools | `readonly: true` | `sandbox_mode` |

The `claude-api` skill was loaded first and was the wrong source: it documents
the Anthropic API, SDK and Managed Agents, not Claude Code subagent frontmatter.
Recorded so the next session does not repeat that step.

### Two corrections to this workstream's own record

**Effort was recorded but never set.** The governing plan says to record the
actual model and effort in every checkpoint. Claude Code exposes no effort
control — not in subagent frontmatter, not on the spawn tool. Every
`worker effort: medium` in the Outcome 2 Task 1 and Task 2 checkpoints in
[[2026-09-04-162018-outcome-1-gate-closure]] therefore names a level nothing
applied. Those checkpoints are left as written, since the vault is
non-destructive and they are committed record; this note is the correction. The
contract now requires `not settable on this host` where that is the truth.

**The escalation rule was skipped.** The plan says to prefer the cheapest tier
that can pass and escalate one tier only after evidence of failure.
`impl-executor` pins `model: haiku`, and root overrode it to `sonnet` on every
dispatch without trying haiku or recording any failure. That is not a defensible
reading of the rule on a workstream under quota pressure. The template keeps
`haiku`; escalation now needs recorded evidence.

### What changed

Canonical role definitions now live in
`references/agents/` — `impl-executor.md`, `spec-validator.md`,
`quality-validator.md`, plus a README carrying the host capability matrix. The
files under `.claude/agents/` became thin wrappers holding host frontmatter and
pointing at the canonical text, so the prose exists in exactly one place. That
is the declare-once-generate-per-host shape ADR 0014 mandates for the product's
own host agent files, applied to the skill itself.

The old `impl-validator` is retired via `git rm`, its history preserved. It
claimed to be read-only while holding `Bash`, so it could write. It is replaced
by a genuinely read-only `spec-validator` (`tools: Read, Grep, Glob`) and a
`quality-validator` that keeps `Bash` because rerunning acceptance commands is
its entire purpose.

Its template also mandated "no narrating comments" and forbade `if/else`
ladders, and pointed every implementer at a Flutter/Dart ruleset whose `fpdart`
types do not exist in Python. Both are gone. The comment banned by that rule is
exactly the kind that explains why a recursive freeze must recurse — the absence
of which caused a real defect in Task 1.

Briefs shrink accordingly: standing constraints, the interpreter rule, the two
failure modes and the report shapes are now in the templates, leaving briefs to
carry only task-specific slots.
