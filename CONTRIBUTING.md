# Contributing

Keep changes small and focused. This repository is easiest to review when each
change has one clear purpose.

## Before you open a pull request

- Check whether the change belongs in the portable package, an adapter, the
  evaluation harness, or a release artifact.
- Avoid editing generated output by hand unless the generated output is the
  thing you are intentionally changing.
- Run the relevant test suites and include the commands you used.
- Update `orchestration-quality-control/CHANGELOG.md` if the change affects
  published behavior.

## What we expect in a pull request

- A short summary of the change.
- The reason for the change.
- The exact tests you ran.
- Any follow-up work that is still open.

## Working style

- Prefer the smallest possible diff.
- Do not rename or reshuffle files unless the change needs it.
- Keep machine-specific local state out of commits.
