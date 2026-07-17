---
description: <short action-oriented summary of the workflow outcome>
---

# Workflow: <Workflow Name>

Use this workflow to <produce one clear outcome>.

## Inputs

- `<input_name>`: <required input and expected shape>
- `<input_name>`: <optional input and default behavior>

## Control

- Primary agent: <agent or role responsible for the final output>
- Decision model: <linear sequence, LLM-directed routing, deterministic routing,
  or human-approved checkpoint>
- Delegation: <none, handoff to specialist, specialist as tool, or parallel
  independent work>

## Steps

1. Load the operating contract
   - OBEY <required rule, instruction, or reference> before any other workflow
     action:
   @<required-rule-or-reference>

2. Establish the target
   - Identify <target entity, document, file, task, or system>.
   - Define the expected output as <output path, object, response, or artifact>.
   - Respect <scope boundary or ownership rule>.

3. Gather required context
   - Read <required source of truth>.
   - Inspect <required inputs, files, tools, or prior outputs>.
   - Keep <evidence, decisions, paths, or assumptions> available for later
     steps.

4. Execute the work
   - Perform <main action>.
   - Preserve <required constraints>.
   - Use delegation only when <delegation condition>.

5. Assemble the result
   - Produce <required output format>.
   - Include <required content>.
   - Omit <out-of-scope content>.

6. Finish
   - Run <required verification or omit if this workflow has no validation
     responsibility>.
   - Return <final response, artifact path, summary, or handoff payload>.

## Stop Conditions

- Stop and report <blocking condition>.
- Ask for confirmation before <approval-gated action>.
- Do not continue when <scope boundary is crossed>.
