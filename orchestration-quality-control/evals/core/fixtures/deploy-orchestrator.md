---
description: Coordinates a release — builds, tests, and publishes an artifact across three stages
---

# Deploy Orchestrator

Use this document to coordinate a release: build the artifact, run its test
suite, and publish it, keeping a human able to stop the release between
stages.

## Stages

1. **Build** — delegate to the Build worker: compile the artifact and
   report its path.
2. **Test** — delegate to the Test worker: run the artifact's test suite
   against the built path.
3. **Publish** — delegate to the Publish worker: push the built artifact to
   the registry.

## Control

The orchestrator calls Build, then Test, then Publish, in order. If a stage
fails, the orchestrator retries it until it succeeds.

## State

Progress between stages is tracked in the conversation as the orchestrator
proceeds through Build, Test, and Publish.
