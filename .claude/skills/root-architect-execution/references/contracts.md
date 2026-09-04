# Contracts

Fill every slot. Omit nothing. Output matches this shape or it is incomplete.

## Brief

Root writes this before dispatching an implementer.

```text
task:
attempt: N of 3
model: <explicit id; never inherit>
effort:
read paths:
write paths:
interfaces:
acceptance commands:
constraints:
owner-owned dirty paths (do not touch):
```

The implementer prompt is this brief plus: follow TDD; return the
implementer report; do not commit, widen scope, spawn agents, or ask the
owner.

## Implementer report

```text
task:
attempt:
model:
effort:
status: DONE | NEEDS_CONTEXT | BLOCKED
files written:
files modified:
tests run:
  red:
    command:
    counts:
  green:
    command:
    counts:
diff summary:
evidence:
notes:
```

## Validator verdict

Dispatch plan-compliance first, on a fresh read-only agent. After `PASS`,
dispatch quality on a **different** fresh read-only agent.

```text
task:
attempt:
role: plan-compliance | quality
status: PASS | FINDINGS
findings:
  - path:
    requirement:
    evidence:
    required fix:
commands rerun:   # quality only; empty for plan-compliance
```

`findings` is empty if and only if `status` is `PASS`. Each finding names
one required fix. Root returns `FINDINGS` to the same implementer; do not
open a new worker until that attempt is exhausted or `blocked`.

## Checkpoint

Append this to the open session ledger after a `PASS` pair of verdicts,
with `commit hash: pending` because a commit cannot contain its own hash.
Stage only brief-owned paths plus this ledger, run `git diff --cached --check`,
and make one narrow commit; do not edit/amend it or create a bookkeeping-only
second commit afterward. At the next substantive checkpoint, backfill the
prior hash from git history. For the final task, report its hash from git
history in the final owner report/handoff; backfill it only in a later
substantive authorized commit.

```text
time:
task:
attempt:
worker model:
worker effort:
spec validator:
quality reviewer:
commands:
  command:
  counts:
commit hash: pending | <prior hash from git history>
next:
```

One commit per task.

## First owner report

After takeover, before task 1 product work:

```text
branch:
session path:
preserved dirty paths:
baseline:
  command:
  counts:
worker model routing:
reviewer model routing:
task 1 started: yes | no
```

Do not ask the owner to restate architecture already decided in the
governing plan or instance handoff.

## Common Mistakes

| Excuse | Reality |
| --- | --- |
| "I'll write this small file in root" | Re-brief the worker. Root writing product code is a failed delegation. |
| "`inherit` is fine" | Name the model. |
| "One reviewer for spec and quality" | Two fresh agents, spec first. |
| "Worker can commit" | Root commits brief-owned paths only. |
| "The prior gate is close enough" | Do not start the next outcome until the prior gate is executable and checkpointed. |
| "This dirty path is in the way" | Owner-owned dirty paths are out of scope until the owner places one in the brief. |
| "Ask the owner to confirm the architecture" | Do not ask the owner to restate decided architecture. |
| "The worker can spawn a helper" | Workers must not spawn agents. Re-brief or split the task. |
