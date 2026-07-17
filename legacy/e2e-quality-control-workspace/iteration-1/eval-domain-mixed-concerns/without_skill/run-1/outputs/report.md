# Domain Description Quality Report

**File evaluated:** `domain-mixed-concerns.domain.md`  
**Evaluation mode:** Baseline (no packaged rules / no skill)  
**Apply changes:** No  
**Language:** English

---

## Summary

The file mixes business-domain knowledge with test automation, UI implementation, and database details. Only one section (`Business rules`) belongs in a domain description. The remaining sections should live in separate artifacts (test data, flow files, or persistence configuration). The domain coverage itself is also very thin.

**Overall assessment:** Needs rework — separation of concerns is the primary issue.

---

## Findings

### 1. Mixed concerns — test credentials in a domain file

**Severity:** High  
**Location:** `## Test credentials` (lines 7–8)

The file stores a login email and plaintext password. Credentials are environment/test-setup data, not business-domain knowledge. Putting them here:

- Blurs what the *Students* domain means versus how tests authenticate
- Risks copying secrets into the wrong context
- Makes the domain file unusable for non-test readers (product, QA planning, onboarding)

**Suggested change:** Move credentials to a dedicated test-data or environment file (for example, a Maestro env file, `.env` test fixture, or secrets store). Reference that artifact from flows instead of embedding secrets in the domain description.

---

### 2. Mixed concerns — UI identifiers and timing in a domain file

**Severity:** High  
**Location:** `## UI identifiers` (lines 10–12)

This section contains:

- A Flutter semantics identifier (`student_list_tile_primary`)
- A hard-coded wait time (`wait 800ms after save`)

Neither describes *what* the Students domain is or *how* the business behaves. They are test-automation implementation details. Hard-coded waits are especially fragile because they couple tests to animation/network timing rather than observable outcomes.

**Suggested change:** Move semantics identifiers into flow/subflow YAML or a UI map referenced by tests. Replace fixed waits with assertions on visible state (snackbar text, navigation, list update). Keep the domain file free of selectors and timing.

---

### 3. Mixed concerns — database schema in a domain file

**Severity:** Medium  
**Location:** `## Firestore` (lines 14–15)

`collection: students`, `field unitId` is persistence-layer detail. While it may relate to the business rule “a student belongs to exactly one school unit,” the collection name and field name are implementation choices, not domain language.

**Suggested change:** Express the rule in domain terms only (for example, “each Student is assigned to exactly one School Unit”). If persistence mapping is needed for tests, document it in a data blueprint, fixture README, or repository contract — not in the domain description.

---

### 4. Insufficient domain coverage

**Severity:** Medium  
**Location:** `## Business rules` (lines 3–4)

Only one business rule is documented. A useful domain description for E2E or agentic workflows typically also clarifies:

- Core entities and key attributes (Student, School Unit)
- Allowed states or lifecycle (enrollment, transfer, inactive)
- Important constraints beyond unit membership
- Primary user-facing workflows (create, edit, list, delete)
- Terminology and boundaries (what counts as a “student” vs other personas)

**Suggested change:** Expand `Business rules` (and optionally add focused sections like `Entities`, `Workflows`, or `Glossary`) with behavior the tests must respect. Keep each statement at the business level.

---

### 5. Security — plaintext password in source

**Severity:** Medium  
**Location:** line 8

Even for QA accounts, storing `Passw0rd!` inline in a committed artifact is a poor practice. Test passwords should be injected via secrets management or local-only config excluded from version control.

**Suggested change:** Remove the password from the domain file. Use environment variables or a gitignored secrets file consumed only by test runners.

---

### 6. Structural inconsistency

**Severity:** Low  
**Location:** entire file

Section headings jump between abstraction levels: business rules, credentials, UI automation, database. There is no framing paragraph explaining scope, audience, or how sections relate. Readers cannot tell which parts are normative domain truth versus incidental test notes.

**Suggested change:** Restructure so the domain file contains only business-facing sections. Add a one-line purpose statement at the top (for example, “Business rules and vocabulary for the Students area, used to author E2E scenarios.”).

---

## What is acceptable

- The title `# Students domain` clearly names the bounded context.
- The single business rule (“A student belongs to exactly one school unit”) is stated in plain language and is testable in principle.
- Markdown structure is readable and short.

---

## Recommended next steps (pending your approval)

1. Strip `Test credentials`, `UI identifiers`, and `Firestore` from this domain file.
2. Relocate each removed concern to its proper artifact type.
3. Flesh out domain entities, rules, and workflows needed for E2E scenario design.
4. Re-run quality review after edits.

**No edits were made to the source file.**
