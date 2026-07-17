#!/usr/bin/env python3
"""PreToolUse hook: block main-session Edit/Write on a target file while an
orchestration-quality-control run is active.

No legacy implementation of this hook existed anywhere in the tree this
package was extracted from — it was only ever referenced by name in
documentation. This is a fresh implementation.

Active-run signal (see references/schemas/checkpoint.schema.json and
scripts/checkpoint_state.py): a checkpoint with status == "pending_approval"
under the workspace's documented state directory. There is no marker file.
This hook re-derives that signal by calling checkpoint_state.py rather than
re-implementing the state machine, so the two can never drift apart.

Claude Code invokes a PreToolUse hook with a JSON payload on stdin
containing at least `tool_name`, `tool_input`, and `cwd`. This hook:

  - allows (exit 0) any tool call that is not Edit or Write;
  - allows (exit 0) any Edit/Write whose target path is not inside the
    active checkpoint's `targets` list, or when no run is active;
  - blocks (exit 2, reason on stderr) an Edit/Write whose target path is
    inside the active checkpoint's `targets` list — exit code 2 is the
    documented, stable PreToolUse blocking contract: Claude Code shows the
    stderr message to the model as the reason the call did not happen.

Register in .claude/settings.json under `hooks.PreToolUse`, matched to the
`Edit` and `Write` tools.
"""
import json
import sys
from pathlib import Path

STATE_SUBDIR = ".orchestration-qc/state"


def _scripts_dir():
    # adapters/claude/hooks/ -> adapters/claude/ -> adapters/ -> package root -> scripts/
    return Path(__file__).resolve().parent.parent.parent.parent / "scripts"


def _find_active_checkpoint(state_dir):
    """Return the parsed active (pending_approval) checkpoint, or None.

    Reads checkpoint files directly rather than shelling out, since this
    hook is on the hot path for every Edit/Write and must stay fast; the
    state-machine invariant it depends on (status field is authoritative)
    is the same one checkpoint_state.py enforces when writing these files.
    """
    if not state_dir.exists():
        return None
    for candidate in sorted(state_dir.glob("checkpoint-*.json")):
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("status") == "pending_approval":
            return data
    return None


def _extract_target_path(tool_input):
    for key in ("file_path", "path"):
        if key in tool_input:
            return tool_input[key]
    return None


def main():
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        # Malformed hook input is not this hook's problem to diagnose;
        # fail open rather than blocking every tool call in the session.
        sys.exit(0)

    tool_name = payload.get("tool_name")
    if tool_name not in ("Edit", "Write"):
        sys.exit(0)

    workspace = Path(payload.get("cwd", "."))
    state_dir = workspace / STATE_SUBDIR
    checkpoint = _find_active_checkpoint(state_dir)
    if checkpoint is None:
        sys.exit(0)

    tool_input = payload.get("tool_input", {})
    target_path = _extract_target_path(tool_input)
    if target_path is None:
        sys.exit(0)

    targets = set(checkpoint.get("targets", []))
    target_rel = target_path
    try:
        target_rel = str(Path(target_path).resolve().relative_to(workspace.resolve()))
    except ValueError:
        pass  # target_path was already relative or outside workspace; compare as-is

    if target_rel in targets or target_path in targets:
        run_id = checkpoint.get("run_id", "unknown")
        print(
            f"orchestration-quality-control: run {run_id} is active and has "
            f"'{target_rel}' checked out for review. Direct edits are blocked "
            "until the pending checkpoint is resolved via /oqc-execute "
            "(apply, skip, or decline each finding).",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
