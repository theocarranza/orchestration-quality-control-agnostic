---
date: 2026-07-17
type: report
tags: [report, guide, orchestration-quality-control, evals, benchmark, definition-of-done]
---

# Next step: confirm the extracted skill matches its old test results

## What this guide covers

The team recently finished pulling a reusable quality-check tool, called
`orchestration-quality-control`, out of an older tool it was bundled inside.
That work is done and tagged as version 1.0.0. Before calling the extraction
fully finished, one open item remains, and this guide explains what it is and
how to close it.

## Background

The decision record for this work, `docs/adr/0005-definition-of-done.md`
(a short document that states when a piece of work counts as complete),
lists four conditions that must all be true. Three are already confirmed
by automated checks that run without needing an active session with a
model: they cover the tool's own internal tests, a full dry run against a
sample project, and a check that a particular tracking number stays stable
even when unrelated lines of a file move around.

The fourth condition is different. It requires the tool to be tried out in
a live session, not just checked by a script, so it cannot be ticked off
automatically.

## The one open condition

The tool ships with two files of test prompts: one for its general-purpose
checks (`orchestration-quality-control/evals/core/evals.json`) and one for
the specific checks used on end-to-end test flows
(`orchestration-quality-control/profiles/former-product-profile/evals/evals.json`).
Each entry in these files pairs a prompt, a sample file to check, and a list
of pass/fail conditions the response must meet — for example, "flags login
details left inside the flow file" or "does not edit anything before asking
first."

The older tool this was extracted from was tested the same way, and its
results were saved in
`legacy/predecessor-skill-workspace/iteration-1/benchmark.json`. That file
shows the older tool passing all of its checks every time it was given the
tool to use, versus a lower pass rate when a model was asked to do the same
review without it. The open condition is to repeat that same exercise for
the newly extracted tool and confirm it matches — a 100 percent pass rate on
each test when the tool is available.

No script exists to run this automatically: the actual grading was done by
reading each response and judging it against the listed pass/fail
conditions, the same way a person would grade an open-ended answer.

## Steps

### 1. Open a session with the tool available

Start a Claude Code session in a context where the
`orchestration-quality-control` skill can be invoked, with the profile named
in each prompt (`core` or `former-product-profile`).

### 2. Run each prompt against its listed sample file

For every entry in both test files, use the exact prompt text and give the
model only the sample file (called a "fixture" — a small file created
purely for testing, not real project content) that entry names. Let the
tool run to completion and keep the full record of what happened, known as
the transcript.

### 3. Grade each transcript

For every pass/fail condition listed under an entry, decide whether the
transcript satisfies it, using the same judgment the earlier grading used
for the older tool. A condition passes only if the transcript clearly shows
it being met.

### 4. Compare against the old result

Add up the pass/fail outcomes for each entry. The open condition is only
satisfied if every entry reaches a full pass, matching the 100 percent
result recorded for the older tool.

### 5. Record the outcome and close the item

Save the results in the same shape as the earlier benchmark file, so future
readers can compare the two directly. Then edit the status line at the top
of `docs/adr/0005-definition-of-done.md`, which currently reads "Item 3
below is open," to reflect that the condition has been checked and passed
(or, if it does not pass, to record what fell short instead of leaving the
status unresolved).

## Troubleshooting

If a test entry falls short of a full pass, the right response is to record
exactly which pass/fail condition failed and why, rather than adjusting the
grading to force a match. The decision record is meant to state the true
result, not a desired one.

## Decision recorded

A repeatable automation was built rather than grading fully by hand: the
older tool's own testing plugin (skill-creator, already installed) turned
out to produce exactly the file shapes referenced above, so the new
automation reuses that plugin's grading and results-aggregation machinery
instead of writing a second one from scratch. A small amount of new,
purpose-built checking was added on top for the two conditions that do not
need human judgment at all — whether the sample file was left unedited, and
whether only the intended file was opened — since those can be answered by
comparing files before and after, rather than by reading the transcript.

## References

- `docs/adr/0005-definition-of-done.md`
- `orchestration-quality-control/evals/core/evals.json`
- `orchestration-quality-control/profiles/former-product-profile/evals/evals.json`
- `legacy/predecessor-skill-workspace/iteration-1/benchmark.json`
