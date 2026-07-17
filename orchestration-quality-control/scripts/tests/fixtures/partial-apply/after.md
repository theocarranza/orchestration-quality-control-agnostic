# Deploy orchestrator

## Steps

1. Build the artifact.
2. Run the smoke tests.
   2a. Run the smoke tests against the staging environment first.
   2b. Only proceed once staging smoke tests are green.
3. Publish the artifact to the registry.

## Stop conditions

The orchestrator halts and reports on any worker failure.
