---
title: Decision 6 brief — worker model on Cursor and Codex
date: 2026-09-02
status: awaiting owner decision
sources:
  - https://cursor.com/docs/context/subagents
  - https://cursor.com/docs/models
  - https://developers.openai.com/codex/subagents
  - https://developers.openai.com/codex/models
  - https://github.com/openai/codex/issues/26363
  - https://github.com/openai/codex/issues/40131
related:
  - "[[2026-09-02-intention-vs-outcome-reconciliation]]"
  - "[[2026-09-02-return-to-intention-4-0-0]]"
  - "[[0013-three-agent-parameterized-code-gated]]"
---

# Decision 6 — which model runs the Validator and Remediator on Cursor and Codex

Claude already tiers (`oqc-orchestrator` `opus`, workers `sonnet`). Cursor and
Codex ship every agent as `inherit`. This brief puts the host documentation
next to the three roles; the decision taken on it is in section 3. Everything
under "What the host documents" is quoted or paraphrased from the official
pages fetched 2026-09-02; nothing is inferred.

## 1. What each role needs in 4.0.0

| Role | Work after the engine takes over (ADR 0013 decision 0) | Judgment load |
| --- | --- | --- |
| Orchestrator | Runs `oqc.py next/compile/gate/mail`, spawns two workers, forwards results. Never reads targets or rules. | Low. Procedure-following. |
| Validator | Reads one compiled prompt (rules, report style, lint findings) and the targets; judges the **semantic** remainder (W1, W5, W9–W11, O1, O2, O4, O7–O9, R1, R4–R6, G*); writes findings + report in the interview language. | High. This is the only place model quality changes the outcome. |
| Remediator | Reads one compiled prompt (approved findings, exact before/after diffs, or a draft brief) and applies exactly that; `draft` mode writes documents from a brief. | Medium for `draft`; low for `apply-findings` / `apply-preview` (mechanical). |

## 2. What the host documents

### 2.1 Cursor

**Frontmatter** (`.cursor/agents/*.md`):

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `model` | string | `inherit` | `inherit` = parent's model; or a specific model ID, e.g. `composer-2`, `gpt-5.6-sol`, `claude-opus-5`. |
| `readonly` | boolean | `false` | Restricted write permissions: no file edits, no state-changing shell commands. |
| `is_background` | boolean | `false` | Runs without blocking the parent. |

**Per-model parameters** are appended in square brackets, `id=value` pairs,
comma-separated: `composer-2.5[fast=false]`, `claude-opus-5[effort=high]`,
`claude-opus-5[effort=high,context=300k]`. `composer-2.5[]` pins the standard
(non-fast) variant.

**When the configured model is not used** — Cursor "falls back to a compatible
model" without failing if: the team admin blocked the model; a legacy
request-based plan requires Max Mode and it is off; the plan does not include
the model. On legacy request-based plans without Max Mode, subagents run
Composer regardless of `model`. Consequence for us: a configured tier can be
silently replaced. The agent cannot observe its own model; disclosure is the
only mitigation.

**Tools** — subagents inherit all tools from the parent, including MCP.
`readonly: true` is the write restriction; there is no per-subagent tool
allowlist (hence the hook in P4).

**Pricing** (USD per million tokens, input / output; from `cursor.com/docs/models`):

| Pool | Model ID (as printed or as named) | Input | Output | Notes |
| --- | --- | --- | --- | --- |
| Cursor Models | Composer 2.5 (`composer-2.5`) | 0.50 | 2.50 | Larger included usage; exempt from the Teams/Enterprise Cursor Token Rate |
| Cursor Models | Grok 4.6 | 2.00 | 6.00 | same pool |
| Other | GPT-5.6 Luna | 0.20 | 1.20 | cheapest listed |
| Other | Gemini 3.8 Flash | 0.75 | 3.50 | |
| Other | Claude Sonnet 5 | 2.00 | 10.00 | |
| Other | GPT-5.6 Terra | 2.00 | 12.00 | |
| Other | GPT-5.6 Sol (`gpt-5.6-sol`) | 4.00 | 20.00 | |
| Other | Claude Opus 5 (`claude-opus-5`) | 5.00 | 25.00 | |
| Other | Claude Fable 5.1 | 10.00 | 50.00 | the model writing this brief |

On Teams and Enterprise, third-party ("Other") models add a Cursor Token Rate
of $0.25 per million tokens; Composer and Grok are exempt. The doc prints IDs
only for `composer-2`, `composer-2.5`, `gpt-5.6-sol`, `claude-opus-5`; other
IDs must be confirmed in the model picker before they go into frontmatter
(P4 smoke item).

### 2.2 Codex

**Custom agent TOML** (`~/.codex/agents/*.toml` or `.codex/agents/*.toml`):

| Field | Required | Meaning |
| --- | --- | --- |
| `name`, `description`, `developer_instructions` | yes | identity, spawn guidance, system prompt |
| `model` | no | overrides parent |
| `model_reasoning_effort` | no | `low`, `medium`, `high`, `xhigh`, `max`, `ultra` (model-dependent) |
| `sandbox_mode` | no | `read-only`, `workspace-write`, `danger-full-access`; inherits parent if omitted |
| `mcp_servers`, `skills.config` | no | inherit parent if omitted |

**Precedence** — Codex resolves each setting from an explicit spawn value, then
the `[agents]` default (`agents.default_subagent_model`,
`agents.default_subagent_reasoning_effort`), then the parent. A custom agent
file's `model` / `model_reasoning_effort` **take precedence over all three**.
A file that sets only `model` keeps the effort resolved above, so set both.

**Sandbox caveat** — "Codex also reapplies the parent turn's live runtime
overrides when it spawns a child. That includes sandbox and approval choices
you set interactively during the session, such as `/permissions` changes or
`--yolo`, even if the selected custom agent file sets different defaults."
Consequence: the Validator's `sandbox_mode = "read-only"` is enforced only
while the parent turn is not running under `--yolo` / a widened
`/permissions`. The enforcement matrix (plan P4) must say so.

**Global `[agents]` settings documented today:** `enabled`,
`max_concurrent_threads_per_session` (`max_threads` legacy alias),
`default_subagent_model`, `default_subagent_reasoning_effort`,
`interrupt_message`. `max_depth` — which our installer writes and our README
calls required — is **not in the current documented table**. P4 must verify
whether `agents.max_depth` is still honored by the installed CLI or drop it.

**Recommended models** (`developers.openai.com/codex/models`, 2026-09-02):

| Model | Positioning (doc wording) | Codex cloud | Suggested for |
| --- | --- | --- | --- |
| `gpt-5.6-sol` | "Flagship … strongest capability for complex coding" | yes | demanding, ambiguous work |
| `gpt-5.6-terra` | "Balanced … competitive with GPT-5.5 at a lower cost"; "works well for parallel workers that return distilled results to the main agent" | no | Validator-shaped work |
| `gpt-5.6-luna` | "Fast and affordable … lowest cost in the family"; "extraction, classification, transformation, and structured summaries" | no | Remediator-shaped work |
| `gpt-5.3-codex-spark` | text-only preview, ChatGPT Pro only, no API | no | not portable enough for a shipped default |

The docs' own review example uses `gpt-5.6-terra` + `high` for the reviewer
and `gpt-5.6-luna` + `medium` for read-only support agents. `gpt-5.4` and
`gpt-5.4-mini` **retired from Codex with ChatGPT sign-in on 2026-08-31**;
the doc says replace them with `terra` and `luna`. Codex pricing under
ChatGPT sign-in is plan credit, not a per-token list on that page; the Cursor
column above gives the family's relative cost (Luna : Terra : Sol ≈ 1 : 10 : 20
on input).

**Known regressions relevant to us:**

- v0.137.0: custom agents were not selectable; spawned subagents inherited
  the parent model silently ([#26363](https://github.com/openai/codex/issues/26363)).
  Fixed in 0.138.0. Same lesson as Cursor's fallback: tiering can vanish
  without an error.
- 0.149.0+: symlinked `*.toml` under `~/.codex/agents/` are rejected
  ([#40131](https://github.com/openai/codex/issues/40131)). Our
  `install_codex_adapter.py` writes file bytes (`write_bytes`), not
  symlinks — unaffected.

## 3. Owner decision — 2026-09-02, 19:30

**No role inherits the root model, on any host.** `inherit` was never the
plan; every agent file names its model (and, on Codex, its reasoning effort).

### The models, as set by the owner

| Role | Claude Code | Cursor | Codex |
| --- | --- | --- | --- |
| Orchestrator | `opus` | `grok-4.6[effort=high]` | `gpt-5.6-terra`, effort `medium` |
| Validator | `sonnet` | `composer-2.5[effort=high]` | `gpt-5.5`, effort `high` |
| Remediator | `haiku` | `composer-2.5[fast=false]` (standard; any low-reasoning model is acceptable) | `gpt-5.6-luna`, effort `low` |

Notes applied when writing the owner's words down:

- Codex remediator: the owner named "gpt low or 5.4". GPT-5.4 and GPT-5.4
  mini retired from Codex with ChatGPT sign-in on 2026-08-31; OpenAI's stated
  replacement for 5.4 mini is `gpt-5.6-luna`. Written as Luna at `low`.
- Codex validator: `gpt-5.5` is listed under "other models" and available in
  the CLI and IDE extension with ChatGPT sign-in; it stands as set.
- Cursor: the docs print IDs only for `composer-2`, `composer-2.5`,
  `gpt-5.6-sol`, `claude-opus-5`. `grok-4.6` and the `effort` switch on
  Composer follow the documented bracket syntax but are not printed as
  examples; the host-enforcement phase confirms each string against the model
  picker, because Cursor substitutes silently when an ID is not honored.
- Claude remediator: the owner allowed `haiku` or `sonnet` at low effort;
  `haiku` is written, `sonnet` with `effort: low` is its first escalation step.

### Escalation if a role fails the release benchmark

That role alone moves up one step; the failure is written into the
definition-of-done record; nothing ever moves to `inherit`.

- Claude: remediator `haiku` → `sonnet` (`effort: low`) → `sonnet`; validator `sonnet` → `opus`.
- Cursor: remediator `composer-2.5` standard → `composer-2.5[effort=high]` → `gpt-5.6-terra`; validator `composer-2.5[effort=high]` → `grok-4.6[effort=high]` → `claude-sonnet-5`.
- Codex: remediator `gpt-5.6-luna` low → `gpt-5.6-luna` medium → `gpt-5.6-terra`; validator `gpt-5.5` high → `gpt-5.6-sol` high.

### Where this lands in the work

- The values above are in the implementation plan's adapter rows and go into
  the nine agent wrapper files when those are created; a test asserts that no
  agent file says `inherit` or omits `model`.
- Host enforcement phase: confirm each Cursor ID against the picker; confirm
  the Codex thread reports the TOML model; verify or drop the Codex depth
  setting; adapter READMEs state the silent-fallback and `--yolo` caveats.
- Release benchmark: run under these models; apply the escalation rule.
