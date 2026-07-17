# End-to-end quality report

## What was checked

The file `flow-with-inline-env.yaml` — a Maestro flow that launches the app, sets login credentials, taps a login button, and checks that the Home screen appears.

## Summary

Two problems were found. The flow stores login credentials inside the flow file instead of in a separate data file. The credential values look made up and are not tied to any known test data source.

## Findings

### Finding 1. Login credentials are stored inside the flow file

What is wrong: The flow defines an environment block with email and password values directly in the flow file (lines 4 through 7).

Rule: Environment values must live in a dedicated data file, not inside the flow itself.

Where: `flow-with-inline-env.yaml`, lines 4 through 7

Suggested change: Move the email and password values into a dedicated data file (for example, a file named after this flow with a `.data.yaml` extension, or a shared `common.data.yaml`). Remove the inline environment block from the flow and reference the data file from the flow instead.

### Finding 2. Credential values look invented

What is wrong: The email `teacher@example.com` and password `secret123` read like placeholder values. The flow does not cite a seed file, reference a data file, or include a comment explaining where these values come from.

Rule: Test data values should come from a known source or be clearly tied to fixture data, not appear invented.

Where: `flow-with-inline-env.yaml`, lines 5 and 6

Suggested change: Replace these values with credentials taken from an approved test data source, or add a data file reference that points to the source. Document the origin of the values in the data file or in a short comment if the workflow allows it.
