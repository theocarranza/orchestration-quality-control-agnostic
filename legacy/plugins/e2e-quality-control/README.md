# e2e-quality-control plugin

Installable wrapper around the `e2e-quality-control` skill.

## Workspace (already wired)

Canonical skill:

`projects/aplicatudo/.agents/skills/e2e-quality-control/`

Discovery symlinks:

- `projects/aplicatudo/.claude/skills/e2e-quality-control`
- `projects/aplicatudo/.cursor/skills/e2e-quality-control`
- monorepo `.cursor/skills/e2e-quality-control`
- monorepo `.agents/skills/e2e-quality-control`
- monorepo `.claude/skills/e2e-quality-control`

## Install as Claude plugin (local path)

```bash
claude plugin install /absolute/path/to/projects/aplicatudo/.agents/plugins/e2e-quality-control
```

## Install as Cursor plugin / marketplace entry

Point a marketplace or local plugin root at this folder. The Cursor manifest is
`.cursor-plugin/plugin.json` and loads `./skills/`.

## Install as standalone `.skill` package

Prebuilt package:

`projects/aplicatudo/.agents/plugins/e2e-quality-control/dist/e2e-quality-control.skill`

Or rebuild:

```bash
python3 -m scripts.package_skill \
  projects/aplicatudo/.agents/skills/e2e-quality-control \
  projects/aplicatudo/.agents/plugins/e2e-quality-control/dist
```

Then import the `.skill` file in Claude Code / Cursor.

## Slash command

Type `/e2e-quality-control` in Cursor or Claude Code.

Optional path:

```
/e2e-quality-control path/to/file-or-folder
```
