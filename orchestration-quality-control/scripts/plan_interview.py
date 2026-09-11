#!/usr/bin/env python3
"""Decide which authoring interview fields to ask, skip, or fork."""

from __future__ import annotations

import argparse

import gate_defaults
import qc_lib

STAGE = "plan_interview"
NEVER_ASK = ("languages", "layout", "tests_exist")


def plan(brief: dict) -> dict:
    fields = gate_defaults.author_fields(brief)
    skip = [{"field": key, "value": value, "reason": "packaged_default"} for key, value in fields.items()]
    return {
        "always_ask": ["outcome"],
        "ask": [],
        "skip": skip,
        "never_ask": list(NEVER_ASK),
        "fork": None,
        "defaults_confirmation": gate_defaults.defaults_confirmation("author", fields),
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
