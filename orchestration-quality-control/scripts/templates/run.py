"""run.py -- this engine's entry point.

Three commands, exactly as the delivery contract requires: `start` opens a run,
`resume` continues an approved one, `status` reports where a run stands.

Standard library only. This file imports `engine_lib` from its own folder and
nothing else, so the engine runs on a machine where the tool that generated it
was never installed.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import engine_lib

COMMANDS = ("start", "resume", "status")

ENGINE_ROOT = Path(__file__).resolve().parents[1]


def _roots(args):
    project_root = Path(args.project_root).resolve()
    settings = engine_lib.constants(ENGINE_ROOT)
    return (
        project_root / settings["state_root"],
        project_root / settings["artifact_root"],
        settings,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run this engine.")
    parser.add_argument("--project-root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="open a new run")
    start.add_argument("--operation", required=True)
    start.add_argument("--run-id", required=True)

    resume = sub.add_parser("resume", help="continue an approved run")
    resume.add_argument("--run-id", required=True)

    status = sub.add_parser("status", help="report where a run stands")
    status.add_argument("--run-id", required=True)

    args = parser.parse_args(argv)
    state_root, artifact_root, settings = _roots(args)

    try:
        if args.command == "start":
            record = engine_lib.start_run(
                state_root,
                run_id=args.run_id,
                operation=args.operation,
                operations=settings["operations"],
            )
            result = {"run_id": record["run_id"], "phase": record["phase"]}
        elif args.command == "status":
            result = engine_lib.status(state_root, args.run_id)
        else:
            result = engine_lib.apply_changes(state_root, args.run_id, artifact_root)
    except engine_lib.EngineError as error:
        print(json.dumps(error.payload(), indent=2, sort_keys=True))
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
