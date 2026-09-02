#!/usr/bin/env python3
"""Decide which authoring interview fields to ask, skip, or fork."""

from __future__ import annotations

import argparse

import qc_lib

STAGE = "plan_interview"
NEVER_ASK = ("languages", "layout", "tests_exist")
UNRESOLVED = ("shape", "approval", "state", "stop", "named_inputs")
E2E_TREES = {"e2e", "integration_test"}


def plan(brief: dict) -> dict:
    skip = []
    ask = list(UNRESOLVED)
    hints = brief.get("doc_language_hints") or []
    if len(hints) == 1 and hints[0] in {"en", "pt-br"}:
        skip.append({"field": "language", "value": hints[0], "reason": "workspace_brief"})
    else:
        ask.append("language")
    profile_hints = brief.get("profile_hints") or []
    if profile_hints:
        ask.append("profile")
    else:
        skip.append({"field": "profile", "value": "core", "reason": "workspace_brief"})
    test_trees = set(brief.get("test_trees") or [])
    if test_trees & E2E_TREES or any("integration" in name for name in test_trees):
        ask.append("outcome_involves_test_tree")
    existing = (brief.get("existing_orchestration") or []) or (brief.get("existing_mechanism") or [])
    return {
        "always_ask": ["outcome", "output_root"],
        "ask": ask,
        "skip": skip,
        "never_ask": list(NEVER_ASK),
        "fork": "author_vs_upgrade" if existing else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief-json", required=True)
    args = parser.parse_args()

    def body():
        return plan(qc_lib.load_json_file(args.brief_json, stage=STAGE))

    qc_lib.run_main(STAGE, body)


if __name__ == "__main__":
    main()
