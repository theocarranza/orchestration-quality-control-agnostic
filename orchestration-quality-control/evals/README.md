# Evaluations

Two eval sets, in the same shape (`skill_name`, `profile`, an `evals` array
of `{id, prompt, expected_output, files, assertions}`, with `injected_failure`
on core eval 1):

- `core/evals.json` — generic orchestration checks only, against fixtures
  in `core/fixtures/`. This is the fixture set
  `AI_Codex/Architecture/ADR/0005-definition-of-done.md` requires to exist for item 2 of the
  extraction's definition of done.
- `author/evals.json` — two scenarios for greenfield authoring (does not
  re-ask brief facts; preview is QC-clean before apply).

```mermaid
flowchart LR
  CORE["evals/core<br/>generic orchestration"] --> GRADE["Live host session"]
  PIPE["profiles/example-pipeline/evals<br/>P1–P6 artifacts"] --> GRADE
  GRADE --> ADR["ADR 0005 item 3"]
```

## How these are run

Neither eval set includes its own grading harness. Running one means
opening a real host session, invoking the skill with each eval's `prompt`
against its `files`, and checking the resulting report and behavior against
that eval's `assertions`.

This step requires a live model and was not run as part of building this
package — see `AI_Codex/Architecture/ADR/0005-definition-of-done.md` for what is verified
today (the deterministic scripts, a full simulated validate/execute cycle,
and fixture classification) versus what is still open (the eval prompts
actually graded against a live run).

## Mailbox assertions

The `m` assertions in every eval are graded from the run's mailbox (via `oqc.py mail verify`)
rather than from the final report. They are currently red until the orchestration engine
ships isolated workers and mailbox persistence. A run whose mailbox does not verify fails
the eval regardless of the quality of its report or findings.
