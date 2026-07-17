---
description: <short action-oriented summary of the coordinated outcome>
---

# Orchestrator: <Orchestrator Name>

Use this orchestrator to <coordinate multiple workers to a single outcome>. It
routes, delegates, validates, and decides. It never authors the artifacts its
workers produce.

## Inputs

- `<input_name>`: <required input and expected shape>
- `<input_name>`: <optional input and default behavior>

## Workers

| #   | Worker        | Contract pair                      | Tools              | Returns        |
| --- | ------------- | ---------------------------------- | ------------------ | -------------- |
| 1   | <worker name> | `<rules-file>` + `<workflow-file>` | `<tool allowlist>` | <output shape> |
| 2   | <worker name> | `<rules-file>` + `<workflow-file>` | `<tool allowlist>` | <output shape> |

Each delegation to a worker states an objective, an output format, tool or
source guidance, and explicit boundaries. Control always returns to this
orchestrator after every delegated step.

## Control

- Primary agent: this orchestrator owns routing, gates, and the final verdict;
  it authors nothing.
- Decision model: deterministic routing for <mechanical decisions>; reserve
  judgment for <open-ended decisions the orchestrator itself must weigh>.
- Delegation: <how workers are invoked — subagent, specialist as tool,
  parallel independent work>.

## Gates

- Validate every worker's returned output before the next step consumes it. A
  failed validation returns to the producing worker; it never propagates
  silently.
- Human approval gates belong to this orchestrator alone. No worker applies or
  approves a change on a human's behalf.
- Name each gate: <gate name> — <what it guards> — <who or what resolves it>.

## State

- State that must persist across steps lives in <file or durable store>, never
  only in conversation context.
- Checkpoint at <point> so a human gate resumes without replaying completed
  work.

## Steps

1. Load the operating contract
   - OBEY <required rule or reference> before any other action:
     @<required-rule-or-reference>

2. Collect inputs
   - Gather `<input_name>` via <UI, argument, or prior context>.
   - Stop and ask if <required input is missing>.

3. Delegate to <worker 1>
   - Objective: <what the worker must produce>.
   - Output format: <expected return shape>.
   - Tool or source guidance: <what the worker may read or use>.
   - Boundaries: <what the worker must not do>.

4. Gate the result
   - Validate the returned output against <criteria>.
   - Present the result via <UI or report>.
   - Await the human decision when <approval-gated condition>.

5. Delegate to <worker 2> (only when the gate is passed)
   - Objective: <what the worker must produce>.
   - Output format: <expected return shape>.
   - Tool or source guidance: <what the worker may read or use>.
   - Boundaries: <what the worker must not do>.

6. Finish
   - Report <what was checked, decided, and done>.
   - Update state only after <the defining success condition>.

## Stop Conditions

- Stop and ask if no input was provided.
- Do not delegate to <worker 2> without an explicit affirmative decision at
  the gate in step 4.
- Do not let a worker choose its own target, mode, or approval.
- Escalate and halt on <conflicting or ambiguous condition> until the user
  confirms.
