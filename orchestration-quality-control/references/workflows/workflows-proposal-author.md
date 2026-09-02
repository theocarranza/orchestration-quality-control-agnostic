---
description: Draft one complete, traceable orchestration upgrade without writing project files
---

# Workflow: Proposal Author

## Inputs

- Frozen target snapshots and structure manifest.
- Structured QC findings and template gaps.
- Selected versioned template, apply mode, output root, and documentation path.

## Control

- Primary agent: Proposal Author.
- Decision model: model judgment for preservation and architecture synthesis;
  deterministic validation occurs after return.
- Delegation: none.

## Steps

1. Load @../rules/rules-proposal-author.md.
2. Map every finding and template gap to the selected template invariants.
3. Build the complete target file set while preserving source intent.
4. Add the complete architecture document and traceability.
5. Return one `upgrade-proposal.schema.json` object, or for authoring one
   `author-proposal.schema.json` object.

## Stop Conditions

- Stop when source intent or an output path is ambiguous.
- Never write files, choose approval, or emit delete/move actions.
