---
date: 2026-07-17
type: session
status: closed
---

# Session — Eval parity benchmark (ADR 0005 item 3)

Previous Session: [[2026-07-16-133000-orchestration-qc-extraction-implementation]]
Next Session: [[2026-07-17-070500-agent-skills-standards-and-aplicatudo-deployment]]

## Scope

Close the one open item from [[2026-07-16-133000-orchestration-qc-extraction-implementation|the extraction session]]: ADR 0005 item 3, profile evaluations at benchmark parity. Three deliverables, per the approved plan:

1. Save the plain-language next-step guide to `Agent_Reports/` (done this session — see [[2026-07-17-eval-parity-next-step]]).
2. Build a repeatable eval-benchmark automation: a repo-local `eval-harness/` (evals converter, deterministic run-integrity checker, runbook) plus a `/run-qc-benchmark` command, reusing the skill-creator plugin's benchmark harness — confirmed this session to be the same harness that produced `legacy/e2e-quality-control-workspace/iteration-1/benchmark.json` (identical workspace layout and output schema).
3. Execute the benchmark live: 8 evals (4 core + 4 aplicatudo-e2e profile) at 3 with_skill runs + 1 without_skill run each (32 runs), grade with deterministic integrity evidence for the edit/isolation assertions, aggregate with skill-creator's `aggregate_benchmark.py`, and update ADR 0005 from the real results only.

User decisions recorded: build and run in this session; 3 with_skill / 1 without_skill runs per eval.
