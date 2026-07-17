---
name: run-qc-benchmark
description: >
  Run the orchestration-quality-control eval-benchmark harness end to end:
  stage both evals.json sets (core and aplicatudo-e2e) into a skill-creator
  workspace, spawn 3 with_skill + 1 without_skill subagent runs per eval,
  grade with deterministic integrity evidence, aggregate into benchmark.json,
  and apply the parity gate from ADR 0005 item 3 honestly — never regrade to
  force a match. Use whenever the user asks to re-run, re-verify, or refresh
  the quality-control skill's benchmark parity.
compatibility: Claude Code only. Requires the skill-creator plugin installed.
---

# run-qc-benchmark

Follow `eval-harness/RUNBOOK.md` in this repository from Step 1 through
Step 9, exactly as written. That file is the source of truth for paths,
run counts, and the parity gate — do not duplicate or paraphrase its
procedure here; read it fresh each time this command runs, since it may
have been updated since this command file was last touched.

If invoked with an argument naming one workspace (`core` or
`aplicatudo-e2e`), run the procedure for that eval set only. With no
argument, run both.
