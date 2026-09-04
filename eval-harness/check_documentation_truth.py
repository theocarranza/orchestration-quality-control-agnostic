#!/usr/bin/env python3
"""Verify that references to unbuilt components do not appear in documentation.

The product roadmap describes components — scripts like oqc.py, mailbox.py,
compile_prompt.py, gate.py, and schemas like envelope.schema.json — that do
not yet exist in the repository. Documentation must not claim these components
are present as if they exist today.

This checker scans a fixed set of product-facing documentation files for
references to those absent components. When a document names a component that
has not yet been built, it reports a finding that can be acted on: either
build the component or remove the false present-tense claim.

A finding exists when a scanned document names any accepted spelling of a core
target AND that target's path does not exist. Findings print in sorted order
by (document, token) for stable byte-ordered output.

## Limitations

This check detects only the literal filename and path spellings in CORE_TARGETS;
a description of a component by its architectural role (e.g., "the gate filters
requests") is not detected, so this check is a regression guard against named
claims, not a semantic truth detector.

Naming one of these components is a finding even when the sentence denies its
existence — e.g., "scripts/gate.py does not exist yet" or a roadmap row
"| scripts/gate.py | Not built |" both produce findings. The governing
decision (ADR 0014, decision 7) forbids product-facing documents from naming
these components at all; a roadmap belongs in the contributor tree, not in
the three scanned documents.

The scan is case-sensitive.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence


SCANNED_DOCUMENTS = (
    "README.md",
    "orchestration-quality-control/README.md",
    "orchestration-quality-control/SKILL.md",
)

CORE_TARGETS = {
    "scripts/oqc.py": (
        ("scripts/oqc.py", "oqc.py"),
        "orchestration-quality-control/scripts/oqc.py",
    ),
    "scripts/mailbox.py": (
        ("scripts/mailbox.py", "mailbox.py"),
        "orchestration-quality-control/scripts/mailbox.py",
    ),
    "scripts/compile_prompt.py": (
        ("scripts/compile_prompt.py", "compile_prompt.py"),
        "orchestration-quality-control/scripts/compile_prompt.py",
    ),
    "scripts/gate.py": (
        ("scripts/gate.py", "gate.py"),
        "orchestration-quality-control/scripts/gate.py",
    ),
    "schemas/envelope.schema.json": (
        ("schemas/envelope.schema.json", "envelope.schema.json"),
        "orchestration-quality-control/schemas/envelope.schema.json",
    ),
}


def _build_pattern(spelling: str) -> str:
    """Build a regex pattern for a spelling with word-boundary checks.

    The pattern matches the spelling only when it appears as a whole token:
    the character immediately before and after must not be [A-Za-z0-9_].

    Args:
        spelling: The literal string to match (e.g., "oqc.py").

    Returns:
        A regex pattern with lookbehind and lookahead assertions.
    """
    # Escape special regex characters in the spelling
    escaped = re.escape(spelling)
    # Add word-boundary constraints
    return rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_]|\.[A-Za-z0-9_])"


def find_untrue_claims(root: Path) -> list[str]:
    """Scan documents for references to absent components.

    Checks each scanned document for references to core targets. When a
    reference is found and the target does not exist, returns a finding.

    Args:
        root: The repository root to scan.

    Returns:
        A list of findings in sorted order, each in the form:
            <document>:<token>:missing-target

    Raises:
        FileNotFoundError: When a scanned document does not exist.
    """
    findings_set = set()

    for doc_path_str in SCANNED_DOCUMENTS:
        doc_path = root / doc_path_str

        if not doc_path.exists():
            raise FileNotFoundError(f"Scanned document not found: {doc_path_str}")

        doc_content = doc_path.read_text(encoding="utf-8")

        for token, (spellings, target_path_str) in CORE_TARGETS.items():
            target_path = root / target_path_str

            # Check if any spelling of this token is mentioned in the document
            for spelling in spellings:
                pattern = _build_pattern(spelling)
                if re.search(pattern, doc_content):
                    # Found a reference to this token in the document
                    if not target_path.exists():
                        # The target doesn't exist - this is a finding
                        finding = f"{doc_path_str}:{token}:missing-target"
                        findings_set.add(finding)
                    # Stop checking other spellings of this token for this document
                    break

    return sorted(findings_set)


def main(argv: Sequence[str] | None = None) -> int:
    """Check documentation truth and report findings.

    Args:
        argv: Command-line arguments. If None, uses sys.argv[1:].
              Accepts an optional positional argument for the scan root,
              defaulting to the repository root.

    Returns:
        0 if no findings, 1 if findings found, 2 if a scanned document
        is missing.
    """
    parser = argparse.ArgumentParser(
        description="Verify that references to unbuilt components do not appear in documentation."
    )
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=None,
        help="Repository root to scan (defaults to repo root derived from script location)",
    )

    args = parser.parse_args(argv)

    # Determine the scan root
    if args.root is None:
        # Derive from script location: parent of parent
        args.root = Path(__file__).resolve().parents[1]

    try:
        findings = find_untrue_claims(args.root)
    except FileNotFoundError as e:
        sys.stderr.write(f"{e}\n")
        return 2

    # Print findings to stdout
    for finding in findings:
        print(finding)

    # Return appropriate exit code
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
