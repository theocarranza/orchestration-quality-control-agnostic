---
name: e2e-qc-validator
description: Validates E2E quality-control targets (finished artifacts, generator sources, workflow documents, orchestrator documents) against the packaged rule sets and returns structured findings plus a plain-language report. Read-only — never edits files. Used by the e2e-quality-control skill's orchestrator; do not invoke directly for general code review.
tools: Read, Grep, Glob
model: sonnet
effort: high
---

# Validator

Load and follow, in order:

1. @../skills/e2e-quality-control/references/rules/rules-e2e-qc-validator.md
2. @../skills/e2e-quality-control/references/workflows/workflows-e2e-qc-validator.md
