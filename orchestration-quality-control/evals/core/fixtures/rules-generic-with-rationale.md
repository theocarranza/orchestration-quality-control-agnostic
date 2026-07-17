---
description: Rules for handling deployment credentials
globs:
  - "**/deploy/**"
alwaysApply: false
---

# Rule: Deployment Credential Handling

Apply this rule when a workflow or script needs to read or pass a deployment
credential.

## Scope

- Applies to any step that reads, stores, or forwards a deployment
  credential.

## Requirements

- Never write a credential value to a log file, because logs are often
  retained for months and a leaked credential could be used long after the
  deployment finished.
- First read the credential from the secret store, then pass it directly to
  the deploy command's stdin — never write it to a temporary file, since
  temp files are sometimes left behind and are readable by other processes
  on the same host.
- Rotate a credential immediately after it is used in a manual deployment,
  so that a credential typed into a terminal by a person is not left valid
  longer than necessary.

## Output

- Confirm no credential value appears in any log line before finishing.
