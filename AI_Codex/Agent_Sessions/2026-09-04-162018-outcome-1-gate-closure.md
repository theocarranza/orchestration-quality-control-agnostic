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

## Checkpoint — Outcome 2 Task 1 — 2026-09-04T20:27:18-03:00

```text
time: 2026-09-04T20:27:18-03:00
task: Outcome 2 Task 1 — vendor-neutral records and the envelope contract
attempt: 3 of 3
worker model: claude-sonnet-5
worker effort: medium
spec validator: claude-sonnet-5, read-only, FINDINGS (2) then resolved
quality reviewer: claude-sonnet-5, read-only, fresh agent, FINDINGS (3) then
  resolved; final verification done at root by direct execution, not a fourth
  agent — see "Why no fourth review" below
commands:
  command: PYTHONPATH=... python3 -m unittest discover -s .../scripts/tests
  counts: 127 tests, OK (Python 3.10.12)
  command: PYTHONPATH=... /usr/local/bin/python3.12 -m unittest discover -s .../scripts/tests
  counts: 127 tests, OK (Python 3.12.13) — identical, which is the point
  command: root reproduction script against the fixed module, both interpreters
  counts: 4 of 4 behaviours correct and identical on 3.10.12 and 3.12.13
  command: other five suites
  counts: not run — no file outside scripts/ changed; they belong to the Task 7 gate
commit hash: pending
next: Outcome 2 Task 2 — append-only mailbox and derived run state
```

Delivered `schemas/envelope.schema.json`, `scripts/kernel_specs.py` and
`scripts/tests/test_kernel_specs.py`. `RunSpec`, `AgentSpec` and `Envelope` are
frozen records; `Envelope` validates against the schema file through a narrow
JSON-Schema-subset interpreter so schema and Python cannot drift.

### Three review rounds, and what each caught

Attempt 1 passed its own tests. Plan-compliance then found an unused
`ENVELOPE_KINDS` constant — a second hand-authored copy of the vocabulary the
schema-driven design exists to prevent — and, more importantly, that the
nested-payload immutability proof was **implemented but never tested**: every
payload fixture was flat, so a regression to shallow freezing would have passed
the whole suite.

Attempt 2 fixed both, and proved the new test bites by temporarily making
`_freeze` shallow, watching it fail, and restoring the file byte-identically.

Quality review then found three defects neither earlier pass caught, all
reproduced at root by executing the module:

1. `re.match` instead of `re.fullmatch` at three sites. Python's `$` matches
   before a trailing newline, so `envelope_id="env-0001\n"` constructed happily.
   Affected every identifier and token field on all three records.
2. **Date-time validation was interpreter-dependent.** `datetime.fromisoformat`
   gained `Z` support in 3.11, so `2026-09-04T12:00:00Z` was rejected on 3.10.12
   and accepted on 3.12.13 — the same envelope valid or invalid depending on
   which Python validated it. Fatal for a kernel whose purpose is deterministic
   replay. The inverse hole existed too: bare `2026-09-04` passed as a date-time.
3. `_freeze` returned a `MappingProxyType` unchanged without recursing. Since
   `Envelope` is a public frozen dataclass, direct construction with an
   already-frozen payload left nested dicts mutable — a hole in the very
   invariant attempt 2 had just hardened. The test passed only because
   `from_dict` happens to supply a plain dict.

Attempt 3 fixed all three and went further than asked on the second: rather than
normalising `Z` and re-delegating to `fromisoformat`, it validates date-times
with a fixed regex plus calendar construction, removing every version-dependent
parsing surface rather than only the one that was caught. Root endorses that
widening — it addresses the class, not the instance.

### Why no fourth review

The skill pairs a plan-compliance agent with a separate quality agent per task,
and both ran. After attempt 3 root verified by direct execution on both
interpreters instead of dispatching a fourth agent: every finding was
behavioural, so running the code is stronger evidence than a further reading of
it, and the quota rule forbids repetition that buys nothing. The reproduction
script and its output are recorded above.

### Carried interpretation calls, endorsed by root

- `RunSpec` deliberately does not embed the generated DAG or an agent roster.
  ADR 0014 and Task 6 treat the three as sibling artifacts. This constrains
  Task 6 and is recorded here so it is a decision rather than an accident.
- The JSON-Schema-subset interpreter is intentionally narrow and auditable, not
  a general engine, because the stdlib-only constraint bars `jsonschema`.

### Open item for the owner

`python3` on this machine is **3.10.12**, while the handoff mandates Python
3.12; `/usr/local/bin/python3.12` exists separately. Every suite this session
has run under 3.10, and defect 2 above is exactly the class of bug that hides in
that gap. The delivered code is now interpreter-independent by construction, so
this is no longer urgent, but the packet's acceptance commands still say
`python3` and therefore still exercise an interpreter the plan does not claim.
Recommendation, pending owner decision: pin the Outcome 2 acceptance commands to
`python3.12` so the stated stack and the executed stack agree.
