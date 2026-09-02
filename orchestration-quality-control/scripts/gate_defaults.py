"""Packaged defaults for removed human approval gates.

See references/defaults/gate-defaults.json for the human-readable catalog.
Only author ``outcome`` remains without a default — the root session must ask it.
"""

from __future__ import annotations

import json
from pathlib import Path

import qc_lib
from qc_lib import Blocked

STAGE = "gate_defaults"
DEFAULTS_PATH = Path(__file__).resolve().parents[1] / "references" / "defaults" / "gate-defaults.json"
AUTHOR_OUTPUT_ROOT = "authored-orchestration"
STATE_DIRECTORY = ".orchestration-qc/state"
STOP_CONDITIONS = (
    "Stop on audit failure, blocked checkpoint, concurrent run, or scope boundary "
    "violation. Ask for human approval only when an unforeseen serious event is not "
    "covered by packaged defaults."
)


def _load_catalog() -> dict:
    return json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))


def _language(brief: dict) -> str:
    hints = brief.get("doc_language_hints") or []
    if len(hints) == 1 and hints[0] in {"en", "pt-br"}:
        return hints[0]
    return "en"


def _profile(brief: dict) -> str:
    hints = brief.get("profile_hints") or []
    if hints == ["example-pipeline"]:
        return "example-pipeline"
    return "core"


def author_fields(brief: dict, overrides: dict | None = None) -> dict:
    overrides = overrides or {}
    base = {
        "output_root": AUTHOR_OUTPUT_ROOT,
        "profile": _profile(brief),
        "language": _language(brief),
        "shape": "single-agent",
        "approval": "required",
        "state": {"directory": STATE_DIRECTORY},
        "stop": STOP_CONDITIONS,
        "named_inputs": [],
        "outcome_involves_test_tree": False,
        "intent": "author",
    }
    return {**base, **overrides}


def validate_fields(brief: dict, overrides: dict | None = None) -> dict:
    overrides = overrides or {}
    base = {
        "profile": _profile(brief),
        "language": _language(brief),
        "decision": "all",
    }
    return {**base, **overrides}


def upgrade_fields(brief: dict, mechanism_path: str | None = None, overrides: dict | None = None) -> dict:
    overrides = overrides or {}
    mechanism = mechanism_path or _infer_mechanism_path(brief)
    basename = Path(mechanism.rstrip("/")).name or "orchestration"
    output_root = f"{basename}-oqc-next"
    base = {
        "mechanism_path": mechanism,
        "profile": _profile(brief),
        "language": _language(brief),
        "template_id": "isolated-three-agent",
        "apply_mode": "side-by-side",
        "output_root": output_root,
        "documentation_path": f"{output_root}/ARCHITECTURE.md",
        "manifest_confirm": True,
        "decision": "approve",
    }
    return {**base, **overrides}


def _infer_mechanism_path(brief: dict) -> str:
    mechanisms = brief.get("existing_mechanism") or []
    orchestrations = brief.get("existing_orchestration") or []
    if len(mechanisms) == 1:
        return mechanisms[0]
    if len(orchestrations) == 1:
        return str(Path(orchestrations[0]).parent)
    if mechanisms:
        return mechanisms[0]
    if orchestrations:
        return orchestrations[0]
    raise Blocked(
        stage=STAGE,
        reason_code="missing_target",
        detail="cannot infer mechanism_path from workspace brief",
        recovery_action="name mechanism_path in the invocation or add it to .orchestration-qc/defaults.json",
    )


def infer_validate_targets(brief: dict, explicit: list[str] | None = None, workspace: Path | None = None) -> list[str]:
    if explicit:
        return explicit
    config_path = (workspace or Path(".")) / ".orchestration-qc" / "defaults.json"
    if config_path.is_file():
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        configured = ((payload.get("validate") or {}).get("targets") or [])
        if configured:
            return list(configured)
    orchestrations = brief.get("existing_orchestration") or []
    if orchestrations:
        return list(orchestrations)
    raise Blocked(
        stage=STAGE,
        reason_code="missing_target",
        detail="cannot infer validate targets from brief or workspace defaults",
        recovery_action="name targets in the invocation or set validate.targets in .orchestration-qc/defaults.json",
    )


def defaults_confirmation(scope: str, fields: dict) -> dict:
    catalog = _load_catalog()
    labels = (catalog.get("labels") or {}).get(scope) or {}
    presented = {
        key: {"value": value, "label": labels.get(key, key)}
        for key, value in sorted(fields.items())
        if key != "outcome"
    }
    return {
        "scope": scope,
        "fields": presented,
        "accept_action": "accept packaged defaults and continue",
        "update_action": "update one or more defaults, then continue",
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    author = sub.add_parser("author-fields", help="Packaged author_prepare defaults from a brief")
    author.add_argument("--brief-json", required=True)
    author.add_argument("--overrides-json", default="{}")

    validate = sub.add_parser("validate-fields", help="Packaged validate/execute defaults from a brief")
    validate.add_argument("--brief-json", required=True)
    validate.add_argument("--overrides-json", default="{}")

    upgrade = sub.add_parser("upgrade-fields", help="Packaged upgrade defaults from a brief")
    upgrade.add_argument("--brief-json", required=True)
    upgrade.add_argument("--mechanism-path", default=None)
    upgrade.add_argument("--overrides-json", default="{}")

    targets = sub.add_parser("infer-validate-targets", help="Infer validate targets without asking")
    targets.add_argument("--brief-json", required=True)
    targets.add_argument("--workspace", default=".")
    targets.add_argument("--explicit-json", default="[]")

    args = parser.parse_args()

    def body():
        brief = qc_lib.load_json_file(args.brief_json, stage=STAGE)
        if args.command == "author-fields":
            overrides = json.loads(args.overrides_json)
            fields = author_fields(brief, overrides)
            return {
                "fields": fields,
                "defaults_confirmation": defaults_confirmation("author", fields),
            }
        if args.command == "validate-fields":
            overrides = json.loads(args.overrides_json)
            fields = validate_fields(brief, overrides)
            return {
                "fields": fields,
                "defaults_confirmation": defaults_confirmation("validate", fields),
            }
        if args.command == "upgrade-fields":
            overrides = json.loads(args.overrides_json)
            fields = upgrade_fields(brief, args.mechanism_path, overrides)
            return {
                "fields": fields,
                "defaults_confirmation": defaults_confirmation("upgrade", fields),
            }
        explicit = json.loads(args.explicit_json)
        return {
            "targets": infer_validate_targets(
                brief,
                explicit or None,
                Path(args.workspace),
            )
        }

    qc_lib.run_main(STAGE, body)


if __name__ == "__main__":
    main()
