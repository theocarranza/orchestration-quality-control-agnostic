---
name: e2e-quality-control
description: Check end-to-end artifacts or generator sources (rules, workflows, prompts) against packaged quality rules and write a short plain report.
argument-hint: "[path-to-file-or-folder]"
---

# /e2e-quality-control

Run the `e2e-quality-control` skill.

Skill path (canonical):

`projects/aplicatudo/.agents/skills/e2e-quality-control/`

## What to do

1. Read and follow that skill's `SKILL.md` exactly.
2. If the user passed a path after the command, treat it as the target (file, folder, or several paths).
3. If no path was given, ask for the target with the usual question screen.
4. Ask for report language (English or Brazilian Portuguese) unless already stated.
5. Classify each target as a finished artifact or a generator source (rules, workflow, or prompt).
6. Check only the packaged rules plus the selected target files.
7. For generator sources, also follow `references/generator-source-validation.md` and ask whether those instructions would produce artifacts that break the packaged rules.
8. Write the report with the bundled plain-language files under `references/plain-language/`.
9. Ask before applying any suggested edits.

## Optional argument

`$ARGUMENTS` — file path, folder path, or multiple paths to check.
