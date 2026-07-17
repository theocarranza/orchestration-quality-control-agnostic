# End-to-end quality report

## What was checked

The file `domain-mixed-concerns.domain.md` — a domain description for the Students area that states one business rule and also lists test login details, screen identifiers, wait timing, and database field notes.

## Summary

Four problems were found. The domain file mixes business rules with test credentials, screen identifiers, wait timing, and database mapping details that belong in other artifact types. Several of the listed values look invented and are not tied to any known test data source.

## Findings

### Finding 1. Test login credentials are stored in the domain file

What is wrong: The file has a "Test credentials" section with an email and password alongside the business rules.

Rule: A domain description must contain only business rules. Login credentials belong in a dedicated data file, not in the domain file.

Where: `domain-mixed-concerns.domain.md`, lines 7 through 9

Suggested change: Remove the Test credentials section from this domain file. Move the email and password into a dedicated data file and reference that file from flows that need them.

### Finding 2. Screen identifiers and wait timing are stored in the domain file

What is wrong: The file has a "UI identifiers" section that lists a Semantics identifier for a list tile and a snackbar wait time of 800 milliseconds after save.

Rule: A domain description must contain only business rules. Screen identifiers and timing values belong in flow, subflow, or blueprint artifacts, not in the domain file.

Where: `domain-mixed-concerns.domain.md`, lines 11 through 13

Suggested change: Remove the UI identifiers section from this domain file. Place the Semantics identifier in the flow or blueprint that taps the list tile. Place the wait timing in the flow step that waits for the snackbar.

### Finding 3. Database field mapping is stored in the domain file

What is wrong: The file has a "Firestore" section that names the students collection and the unitId field.

Rule: A domain description must contain only business rules. Database collection and field mapping details belong in blueprint or data artifacts, not in the domain file.

Where: `domain-mixed-concerns.domain.md`, lines 15 through 16

Suggested change: Remove the Firestore section from this domain file. Keep only the business rule that a student belongs to exactly one school unit. Move collection and field details to the blueprint or data file that the relevant flows use.

### Finding 4. Several values look invented

What is wrong: The email qa.teacher@example.com, the password Passw0rd!, the collection name students, the field name unitId, and the 800 millisecond wait time read like placeholder values. The file does not cite a seed file, reference a data file, or include a comment explaining where these values come from.

Rule: Test data values should come from a known source or be clearly tied to fixture data, not appear invented.

Where: `domain-mixed-concerns.domain.md`, lines 8 through 9 and lines 12 through 16

Suggested change: When these values are moved to their proper artifact types, replace them with values taken from an approved test data source, or add a data file reference that points to the source. Document the origin of each value in the data file or in a short comment if the workflow allows it.
