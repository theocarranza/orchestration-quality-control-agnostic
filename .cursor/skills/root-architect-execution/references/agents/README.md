# Agent role definitions

Canonical definitions for the three subagent roles the per-task loop uses. The
host files under `.claude/agents/` are thin wrappers carrying host-specific
frontmatter and pointing here for the prose, so this directory is the only place
the role text exists.

That is the shape ADR 0014 mandates for the product's own host agent files —
declare once, generate per host — applied to the skill itself.

## Roles

| Role | Writes code? | Permission | File |
| --- | --- | --- | --- |
| Implementer | yes, only brief-owned paths | full tools | [impl-executor.md](impl-executor.md) |
| Spec validator | never | genuinely read-only | [spec-validator.md](spec-validator.md) |
| Quality validator | never | read plus run commands | [quality-validator.md](quality-validator.md) |

Spec runs first. Quality runs only after spec passes, on a **different** fresh
agent. Combining them is a red flag.

## Host capability matrix

Confirmed against each host's own documentation on 2026-09-04.

| | Claude Code | Cursor | Codex |
| --- | --- | --- | --- |
| Location | `.claude/agents/*.md` | `.cursor/agents/`, also reads `.claude/` and `.codex/` | `.codex/agents/*.toml` |
| Format | Markdown plus YAML frontmatter | Markdown plus YAML frontmatter | TOML |
| Required | `name`, `description` | none; `name` defaults to filename | `name`, `description`, `developer_instructions` |
| Model values | `sonnet` `opus` `haiku` `fable` `inherit` | `inherit` or a model id | any `config.toml` model |
| Model default | **`inherit`** | **`inherit`** | **inherits from parent** |
| Effort | **not expressible** | in the model string, `claude-opus-5[effort=high]` | `model_reasoning_effort` |
| Tool control | `tools` allowlist, `disallowedTools` denylist | not documented | `mcp_servers` |
| Read-only | omit write tools from `tools` | `readonly: true` | `sandbox_mode = "read-only"` |

Two consequences the loop must respect.

**Every host defaults to inheriting the parent model.** That is why the
governing plan forbids `inherit`: without an explicit `model`, a cheap worker
silently becomes as expensive as root. Every wrapper sets `model`.

**Effort is not settable on Claude Code.** Neither the subagent frontmatter nor
the spawn tool exposes it; Cursor encodes it in the model string and Codex has
`model_reasoning_effort`. On Claude a checkpoint must therefore record effort as
`not settable on this host` rather than naming a level nothing applied.
Recording a level you did not set is a false claim about the run.
