# Evaluations

Two eval sets, in the same shape (`skill_name`, `profile`, an `evals` array
of `{id, prompt, expected_output, files, assertions}`):

- `core/evals.json` — generic orchestration checks only, against fixtures
  in `core/fixtures/` that contain no Aplicatudo, Maestro, or Flutter
  content. This is the fixture set `docs/adr/0005-definition-of-done.md`
  requires to exist for item 2 of the extraction's definition of done.
- `../profiles/aplicatudo-e2e/evals/evals.json` — the four regression
  scenarios carried over from the retired `e2e-quality-control` 3.0.0
  skill, with byte-identical assertions.

## How these are run

Neither eval set includes its own grading harness. Running one means
opening a real Claude Code (or other host) session, invoking the skill with
each eval's `prompt` against its `files`, and checking the resulting
report and behavior against that eval's `assertions` — the same process
that produced `legacy/e2e-quality-control-workspace/iteration-1/` for the
retired skill (see `benchmark.json` there for the with-skill/without-skill
comparison this package needs to match).

This step requires a live model and was not run as part of building this
package — see `docs/adr/0005-definition-of-done.md` for what is verified
today (the deterministic scripts, a full simulated validate/execute cycle,
and fixture classification) versus what is still open (the eval prompts
actually graded against a live run).
