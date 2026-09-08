"""Native Claude PreToolUse policy seam for exact engine-issued workers."""
import json
import re
import sys
import subprocess
from pathlib import Path
from types import MappingProxyType

_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_TOP_LEVEL = {"hook_event_name", "session_id", "transcript_path", "cwd", "permission_mode", "tool_name", "tool_input", "tool_use_id"}
_TOOL_INPUT = {"prompt", "description", "subagent_type", "model"}
POLICY_DISCLOSURE = MappingProxyType({
    "native_hook_intent": "admit only the exact engine-issued Agent worker",
    "command_hook_timeout_or_error_fail_closed": False,
    "load_bearing_validation": "deterministic adapter request/worker/session/result validation",
})

def _valid_identity(value):
    return isinstance(value, str) and bool(_IDENTITY.fullmatch(value)) and value != "inherit"

def decide(payload, expected_worker):
    allowed = False
    if _valid_identity(expected_worker) and isinstance(payload, dict):
        allowed = (set(payload) <= _TOP_LEVEL and {"tool_name", "tool_input", "tool_use_id"} <= set(payload)
                   and payload.get("tool_name") == "Agent"
                   and isinstance(payload.get("tool_input"), dict)
                   and set(payload["tool_input"]) <= _TOOL_INPUT
                   and "subagent_type" in payload["tool_input"]
                   and payload["tool_input"].get("subagent_type") == expected_worker
                   and isinstance(payload.get("tool_use_id"), str)
                   and bool(payload["tool_use_id"].strip()))
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow" if allowed else "deny"}}

def local_cli_smoke():
    """No-model smoke: CLI version/help plus real hook subprocess fixtures."""
    help_run = subprocess.run(["claude", "--help"], text=True, capture_output=True, check=True)
    version_run = subprocess.run(["claude", "--version"], text=True, capture_output=True, check=True)
    flags = all(flag in help_run.stdout for flag in ("--settings", "--tools", "--allowed-tools", "--agents", "--include-hook-events"))
    if not flags or not version_run.stdout.strip():
        raise RuntimeError("installed Claude CLI lacks required no-model capability")
    script = str(Path(__file__).resolve())
    fixtures = {
        "allow": {"tool_name": "Agent", "tool_input": {"subagent_type": "author"}, "tool_use_id": "u1"},
        "deny": {"tool_name": "Bash", "tool_input": {}, "tool_use_id": "u1"},
        "malformed": {"tool_name": "Agent", "tool_input": {"subagent_type": "author"}},
    }
    outcomes = {}
    for name, payload in fixtures.items():
        run = subprocess.run([sys.executable, script, "author"], input=json.dumps(payload), text=True, capture_output=True, check=True)
        outcomes[name] = json.loads(run.stdout)["hookSpecificOutput"]["permissionDecision"]
    return {"flags": flags, "fixtures": outcomes, "version": version_run.stdout.strip()}

def generated_settings(expected_worker):
    if not _valid_identity(expected_worker):
        raise ValueError("expected_worker must be a validated identity")
    return {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{
        "type": "command", "command": sys.executable,
        "args": [str(Path(__file__).resolve()), expected_worker], "timeout": 3,
    }]}]}}

def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        payload = json.load(sys.stdin) if len(argv) == 1 else None
    except (json.JSONDecodeError, OSError):
        payload = None
    sys.stdout.write(json.dumps(decide(payload, argv[0] if len(argv) == 1 else ""), sort_keys=True, separators=(",", ":")) + "\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
