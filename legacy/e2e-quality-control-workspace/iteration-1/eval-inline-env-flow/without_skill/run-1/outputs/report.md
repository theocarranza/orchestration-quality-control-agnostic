# End-to-end flow quality report

**Target:** `flow-with-inline-env.yaml`  
**Mode:** Review only (no edits applied)  
**Language:** English

## Summary

This flow file has several structural and maintainability problems. The most serious issue is that login credentials are defined inside the flow instead of a separate data file, and the `env` block is placed in the wrong part of the file. The flow is also incomplete as a login test and uses brittle selectors.

## Findings

| # | Problem | Where | Rule / rationale | Suggested change |
|---|---------|-------|------------------|------------------|
| 1 | Environment values are embedded in the flow | Lines 4–6 (`env:` with `EMAIL`, `PASSWORD`) | Test data should live in a dedicated data file (for example `common.data.yaml` or `{feature}.data.yaml`), not inline in the flow | Move `EMAIL` and `PASSWORD` to a data file; reference them in steps with `${EMAIL}` and `${PASSWORD}` |
| 2 | `env` block is in the wrong place | Lines 3–6, between `launchApp` and the next `---` | In Maestro flows, `env` is top-level metadata alongside `appId`, before the first `---` separator | Move the entire `env` block above the first `---`, directly under `appId` |
| 3 | File structure is fragmented | Lines 2, 7 (`---` separators) | A standard Maestro flow uses one header section plus one command section | Merge into a single document: header (`appId`, `env`, optional `onFlowStart`, `tags`) then one `---`, then commands |
| 4 | Login steps do not use the environment variables | Lines 8–9 | Credentials declared in `env` are never consumed; the flow only taps a button | Use a reusable login subflow or explicit `inputText: ${EMAIL}` / `inputText: ${PASSWORD}` steps before submit |
| 5 | Assertion is text-based and vague | Line 10 (`assertVisible: "Home"`) | Prefer stable semantic element identifiers over visible text labels | Replace with `assertVisible` on a known element id (for example a page-level id) |
| 6 | Selector may not match project conventions | Line 9 (`id: login_button`) | Flows should use documented semantic ids consistent with the app | Verify and use the correct submit control id (for example `login_submit_button`) |
| 7 | Missing flow header comments | Top of file | Flows should document purpose, preconditions, selector rationale, and required env inputs | Add a short comment block describing what the flow tests and which data file supplies env values |
| 8 | No standardized app launch setup | Line 3 (`launchApp`) | End-to-end flows should start from a known clean state via a shared launch subflow | Replace bare `launchApp` with `onFlowStart` running a clean-launch subflow |
| 9 | `appId` value looks incorrect | Line 1 | `appId` must match the build under test | Confirm and set the correct application id for the target environment |

## Questions answered

- **Report language:** English  
- **Apply suggested changes:** No — no files were modified.

## Next step

If you want these fixes applied, confirm and I can update the flow file (or produce a corrected draft for review).
