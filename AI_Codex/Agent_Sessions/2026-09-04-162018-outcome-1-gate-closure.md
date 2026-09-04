---
date: 2026-09-04
timestamp: 2026-09-04T16:20:18-03:00
type: session
status: open
branch: feature/original-design-realignment
previous: "[[2026-09-04-073200-markdown-lint-tooling]]"
next: null
ticket: "[[refactor-align-the-architecture-with-original-design]]"
plan: "[[2026-09-04-original-design-realignment-master-plan]]"
handoff: "[[2026-09-04-claude-original-design-implementation-handoff]]"
skill: root-architect-execution
---

# Session — Outcome 1 gate closure

Previous Session: [[2026-09-04-073200-markdown-lint-tooling]]
Next Session: (none)

## Mandate

Close Outcome 1 Task 3 — the Outcome 1 gate — under `root-architect-execution`,
on owner instruction to proceed. The Outcome 1 workstream ledger remains
[[2026-09-04-055932-outcome-1-truth-reset]]; gate checkpoints are recorded
there, and this note carries the session chain and the environment rulings that
were specific to this sitting.

## Bootstrap — 2026-09-04T16:20:18-03:00

- Branch: `feature/original-design-realignment` at `0eeea67`, in sync with
  `origin`. Worktree clean apart from untracked `.superpowers/`, which stays
  excluded.
- Gate evidence gathered before any write: 216 tests across the six suites
  (98 scripts, 8 Claude hooks, 6 Claude adapter, 36 Codex adapter, 19 Cursor
  adapter, 49 eval-harness), `check_documentation_truth.py` exit 0, and
  `git diff --check` clean both in the worktree and across `75663be..HEAD`.

## Environment rulings this sitting

### Checkout ownership

The checkout was owned by `monolith:monolith` while this session runs as
`bhave`, leaving `.git` and most tracked files read-only to it. No write or
commit was possible. Root did not attempt a privileged fix on its own: `sudo`
required a password and this session has no terminal. The owner ran
`chgrp -R ricks` plus `chmod -R g+rwX` over the checkout, which granted the
`ricks` group write access without altering owner permissions. Verified
writable before proceeding.

### Session-gate deadlock

The `codex-workflows-plugin` session gate blocked every write because
[[2026-09-04-073200-markdown-lint-tooling]] was `next: null` and older than the
eight-hour window, while the remedy it named — editing that note — was itself a
write. Reading `scripts/policy/engine.py` resolved it rather than guesswork: the
gate is bypassed when the event's `file_path` contains `Agent_Sessions`, which a
Bash `sed -i` does not populate but a file-tool write does. This note and the
`next` link on the lint session were therefore written with the file tools, and
no policy was skipped or disabled to do it.

## Owner rulings carried into this session

- The three handoff-designated owner-owned paths committed at `5f6ac4f` and
  `3c10fe5` are ratified as in scope, and come off the protected list.
- `docs/2026-09-04-master-plan-review.md` is repaired: twelve verified
  path-depth corrections, and the three `architecture-ruling.md` citations
  demoted to plain prose rather than retargeted to an inferred file.
- Testing cost is reduced by cutting repetition, never by skipping tests or
  validations.

## Checkpoint — validation-scope rule — 2026-09-04T17:10:57-03:00

Owner instruction: only run checks for what changed or is indirectly affected;
keep on-the-fly validation targeted, and reserve the expensive full pass for
before an outcome is declared complete.

Written into both host copies of `root-architect-execution` as a new
**Validation scope** section, with supporting changes: two red flags (closing an
outcome gate on targeted evidence; reusing evidence without labelling it), a
brief instruction to scope `acceptance commands` to reachable code and put the
reachability argument in `constraints`, a checkpoint instruction to mark
carried-over counts as `reused`, and three new rows in the Common Mistakes
table. The rule is deliberately phrased so targeted scope is a claim root must
defend — if you cannot argue what is unaffected, you run the full set.

Root made this edit directly rather than briefing an implementer. It is
governance text the owner dictated, not product code, and delegating a
two-paragraph insertion would have cost more quota than it saved — which is the
same principle the rule encodes.

```text
time: 2026-09-04T17:10:57-03:00
task: add the validation-scope rule to root-architect-execution
attempt: 1 of 3
worker model: none; governance text, edited at root
spec validator: not dispatched; the owner dictated the rule verbatim
quality reviewer: not dispatched; no product-code diff
commands:
  command: diff -r .claude/skills/... .cursor/skills/...
  counts: identical, byte for byte
  command: npx --no-install markdownlint-cli2
  counts: 155 files, 0 issues
  command: six baseline suites
  counts: not run — reused from Checkpoint 7; no non-Markdown file changed since
commit hash: pending
next: Outcome 2 — executable kernel slice
```

### Applying the rule to itself

This change touches Markdown only, confirmed with `git diff --name-only`, so the
six Python suites were not re-run; their Checkpoint 7 evidence stands at an
unchanged code HEAD and is labelled reused above. The check the change *does*
reach is markdownlint, which was run.

Worth recording for future targeting: **markdownlint-cli2 cannot be narrowed by
passing file paths.** It appends its configured globs to any arguments, so a
"targeted" invocation still linted all 155 files. That full sweep takes seconds,
so nothing is lost here, but the tool is not a place where targeting is
available.

### Two lint errors, found and fixed

- `MD012` in [[2026-09-04-055932-outcome-1-truth-reset]] — a double blank line
  introduced by this session's own Checkpoint 7 append. Root's error, corrected.
- `MD038` in ADR 0013 at line 112 — pre-existing and **failing the branch's CI
  markdownlint job**. Backticks cannot nest, so the inner pairs around
  `language` and `en` split one intended code span into three, leaving a span
  with interior spaces. Removing the inner backticks restores a single span. The
  diff is markup only; no word of the superseded decision changed.
