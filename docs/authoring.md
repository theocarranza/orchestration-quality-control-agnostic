# Greenfield authoring

This skill can **write** the documents that run an agentic process, not
only check or upgrade ones that already exist.

Use `/oqc-author` (Codex: `orchestration-author`).

```mermaid
flowchart TD
  START["You want a new workflow / rules / orchestrator"] --> AUDIT["Skill audits the repo<br/>stack, layout, tests, existing orchestration"]
  AUDIT --> BRIEF["workspace_brief"]
  BRIEF --> OUT["Root session asks outcome only"]
  OUT --> DEF["Confirm packaged defaults<br/>accept or update"]
  DEF --> DRAFT["Draft process documents<br/>not host agents"]
  DRAFT --> QC{"Internal validate<br/>all_passed?"}
  QC -->|no, first fail| DRAFT
  QC -->|no, second fail| BLOCK["blocked"]
  QC -->|yes| AUTO["Auto-apply into empty output_root"]
```

## What ships conceptually

`author_prepare` then `author_apply`, matching the upgrade split.

1. **Audit the workspace** (no questions yet): stack, top-level layout,
   test and end-to-end trees, CI, existing workflow/rules/orchestrator
   files, existing host agents. Deterministic discovery plus README and
   package manifests — not a free-form repo tour.
2. **Ask outcome only** in the root session: what the orchestration should
   achieve. Every other authoring field uses packaged defaults from
   `references/defaults/gate-defaults.json`, confirmed once (accept or
   update) before nested work starts.
3. **Draft** workflow, rules, optional orchestrator, and
   `ARCHITECTURE.md` from the packaged templates.
4. **Run the same quality-control rules** on that draft. On pass, **auto-apply**
   with packaged `decision: approve` unless `blocked`.
5. **Write** the tree under the default or overridden `output_root`
   (`authored-orchestration` by default).

It does not install Claude/Cursor/Codex agents. That is still guided
upgrade. It does not guess the outcome from the README.

```mermaid
flowchart LR
  subgraph never["Never asked — already in the audit"]
    N1["Stack / language"]
    N2["Do tests or e2e exist?"]
    N3["Describe the folder layout"]
  end
  subgraph always["Root session only"]
    A1["What should this orchestration achieve?"]
  end
  subgraph defaults["Packaged defaults — confirm once"]
    D1["Output folder, shape, approval, state, language, …"]
  end
```

## Root session UI (Cursor)

Nested Task subagents cannot surface `AskQuestion` to the parent chat. The
**outcome** question and defaults confirmation must run in the root Cursor
session before spawning `oqc_cursor_upgrade_orchestrator`. See
`references/workflows/workflows-root-session-interview.md`.

## Planned host entry

| Host | Entry |
| --- | --- |
| Claude Code, Cursor | `/oqc-author` |
| Codex | `orchestration-author` |

## Authority

- [ADR 0012](../AI_Codex/Architecture/ADR/0012-greenfield-orchestration-authoring.md)
- `references/defaults/gate-defaults.json`
