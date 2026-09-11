# Multi-Model Agentic Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build model-agnostic skill loading, adapter translation, protocol normalization, persistence, event hooks, and MCP integration for the existing functional orchestrator.

**Architecture:** Extend the current `orchestrator_core` modules with focused pure modules instead of replacing the existing reducer/stream/router. The implementation keeps state transitions pure, moves side effects behind hooks and protocol boundaries, and uses local plugin-owned persistence under a `projects/` directory keyed by workspace root.

**Tech Stack:** Python 3 standard library, `dataclasses`, `unittest`, JSON Schema-shaped dictionaries, stdio JSON-RPC MCP server.

---

## File Structure

- Create `tests/`: stdlib `unittest` test suite for all new behavior.
- Create `tests/test_skill_package.py`: validates universal skill loading, manifest validation, and tool discovery.
- Create `tests/test_dialects.py`: validates Markdown-to-target dialect transformations.
- Create `tests/test_tool_binding.py`: validates manifest tool schema mapping to OpenAI and Anthropic shapes.
- Create `tests/test_protocol.py`: validates normalized CLI command extraction from native tool-call responses.
- Create `tests/test_persistence.py`: validates workspace-root hashing and local project state paths.
- Create `tests/test_events_and_reducers.py`: validates new event factories, retry injection, and circuit breaker behavior.
- Create `tests/test_mcp_server.py`: validates MCP list/call integration with loaded universal skills.
- Create `orchestrator_core/skill_package.py`: universal skill package loader for `manifest.json`, `instructions.md`, and executable files under `tools/`.
- Create `orchestrator_core/dialects.py`: pure Markdown transformation functions for generic, OpenAI, and Anthropic prompts.
- Create `orchestrator_core/tool_binding.py`: pure manifest-to-native tool schema mapping.
- Create `orchestrator_core/protocol.py`: pure protocol normalization from model-native tool calls to universal CLI commands.
- Create `orchestrator_core/persistence.py`: local project state path and JSON read/write helpers.
- Create `orchestrator_core/events.py`: typed event factory helpers over the existing immutable `Event` record.
- Create `orchestrator_core/meta_agent.py`: deterministic failure-summary and instruction-update proposal helpers.
- Modify `orchestrator_core/reducers.py`: minimal integration for critique payload appending and circuit breaker event history.
- Modify `orchestrator_core/mcp_server.py`: minimal integration to use `SkillPackage` and normalized MCP tool call handling.
- Mirror changed/new runtime modules into `maestro-e2e-plugin/orchestrator_core/` only after root tests pass, because the plugin package ships its own runtime copy.

### Task 1: Universal Skill Package Loader

**Files:**

- Create: `tests/test_skill_package.py`
- Create: `orchestrator_core/skill_package.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_skill_package.py`:

```python
import json
import stat
import tempfile
import unittest
from pathlib import Path

from orchestrator_core.skill_package import SkillPackage, load_skill_package, list_skill_packages


class SkillPackageTests(unittest.TestCase):
    def test_loads_manifest_instructions_and_executable_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "echo_skill"
            tools_dir = skill_dir / "tools"
            tools_dir.mkdir(parents=True)
            (skill_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "name": "echo",
                        "version": "1.0.0",
                        "description": "Echo input text.",
                        "input_schema": {
                            "type": "object",
                            "properties": {"text": {"type": "string"}},
                            "required": ["text"],
                        },
                        "outputs": {"type": "text"},
                        "tools": [
                            {
                                "name": "echo_text",
                                "description": "Echo text through CLI.",
                                "command": "echo_text",
                                "input_schema": {
                                    "type": "object",
                                    "properties": {"text": {"type": "string"}},
                                    "required": ["text"],
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (skill_dir / "instructions.md").write_text("Return the input text.", encoding="utf-8")
            tool = tools_dir / "echo_text"
            tool.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$1\"\n", encoding="utf-8")
            tool.chmod(tool.stat().st_mode | stat.S_IXUSR)

            package = load_skill_package(skill_dir)

            self.assertIsInstance(package, SkillPackage)
            self.assertEqual(package.name, "echo")
            self.assertEqual(package.version, "1.0.0")
            self.assertEqual(package.instructions, "Return the input text.")
            self.assertEqual(package.tool_paths["echo_text"], tool)

    def test_rejects_missing_required_manifest_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "bad_skill"
            skill_dir.mkdir()
            (skill_dir / "manifest.json").write_text('{"name": "bad"}', encoding="utf-8")
            (skill_dir / "instructions.md").write_text("Do work.", encoding="utf-8")

            with self.assertRaises(ValueError) as ctx:
                load_skill_package(skill_dir)

            self.assertIn("version", str(ctx.exception))
            self.assertIn("input_schema", str(ctx.exception))

    def test_lists_only_valid_skill_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            valid = root / "valid"
            invalid = root / "invalid"
            valid.mkdir()
            invalid.mkdir()
            (valid / "manifest.json").write_text(
                json.dumps(
                    {
                        "name": "valid",
                        "version": "1.0.0",
                        "description": "Valid skill.",
                        "input_schema": {"type": "object", "properties": {}},
                        "outputs": {"type": "text"},
                    }
                ),
                encoding="utf-8",
            )
            (valid / "instructions.md").write_text("Do valid work.", encoding="utf-8")
            (invalid / "manifest.json").write_text('{"name": "invalid"}', encoding="utf-8")

            packages = list_skill_packages(root)

            self.assertEqual([package.name for package in packages], ["valid"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_skill_package -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'orchestrator_core.skill_package'`.

- [ ] **Step 3: Write the minimal implementation**

Create `orchestrator_core/skill_package.py`:

```python
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


REQUIRED_MANIFEST_FIELDS = ("name", "version", "description", "input_schema", "outputs")


@dataclass(frozen=True)
class SkillPackage:
    root: Path
    manifest: Dict[str, Any]
    instructions: str
    tool_paths: Dict[str, Path] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return str(self.manifest["name"])

    @property
    def version(self) -> str:
        return str(self.manifest["version"])

    @property
    def description(self) -> str:
        return str(self.manifest["description"])

    @property
    def input_schema(self) -> Dict[str, Any]:
        return dict(self.manifest["input_schema"])


def _read_manifest(skill_dir: Path) -> Dict[str, Any]:
    manifest_path = skill_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"Missing manifest.json: {skill_dir}")
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    missing = [field for field in REQUIRED_MANIFEST_FIELDS if field not in manifest]
    if missing:
        raise ValueError(f"Manifest {manifest_path} missing required fields: {', '.join(missing)}")
    if not isinstance(manifest["input_schema"], dict):
        raise ValueError(f"Manifest {manifest_path} input_schema must be an object")
    return manifest


def _read_instructions(skill_dir: Path) -> str:
    instructions_path = skill_dir / "instructions.md"
    if not instructions_path.exists():
        raise ValueError(f"Missing instructions.md: {skill_dir}")
    return instructions_path.read_text(encoding="utf-8").strip()


def _discover_tools(skill_dir: Path, manifest: Dict[str, Any]) -> Dict[str, Path]:
    tools_dir = skill_dir / "tools"
    if not tools_dir.exists():
        return {}
    tool_paths: Dict[str, Path] = {}
    for tool in manifest.get("tools", []):
        name = tool.get("name")
        command = tool.get("command")
        if not name or not command:
            raise ValueError("Each tool entry must define name and command")
        path = tools_dir / str(command)
        if not path.exists():
            raise ValueError(f"Tool command not found: {path}")
        tool_paths[str(name)] = path
    return tool_paths


def load_skill_package(skill_dir: Path) -> SkillPackage:
    root = Path(skill_dir)
    manifest = _read_manifest(root)
    instructions = _read_instructions(root)
    tool_paths = _discover_tools(root, manifest)
    return SkillPackage(root=root, manifest=manifest, instructions=instructions, tool_paths=tool_paths)


def list_skill_packages(skills_root: Path) -> List[SkillPackage]:
    root = Path(skills_root)
    if not root.exists():
        return []
    packages: List[SkillPackage] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        try:
            packages.append(load_skill_package(child))
        except ValueError:
            continue
    return packages
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
python3 -m unittest tests.test_skill_package -v
```

Expected: PASS with `Ran 3 tests`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_skill_package.py orchestrator_core/skill_package.py
git commit -m "feat: add universal skill package loader"
```

### Task 2: Dialect Transformation Pipeline

**Files:**

- Create: `tests/test_dialects.py`
- Create: `orchestrator_core/dialects.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dialects.py`:

```python
import unittest

from orchestrator_core.dialects import (
    build_prompt_payload,
    to_anthropic_xml,
    to_generic_cli_prompt,
    to_openai_messages,
)


class DialectTests(unittest.TestCase):
    def test_anthropic_xml_wraps_sections_without_mutating_text(self):
        result = to_anthropic_xml("Follow the manifest.", "Task payload.")

        self.assertEqual(
            result,
            "<instructions>\nFollow the manifest.\n</instructions>\n\n<payload>\nTask payload.\n</payload>",
        )

    def test_openai_messages_use_system_and_user_roles(self):
        result = to_openai_messages("Follow the manifest.", "Task payload.")

        self.assertEqual(
            result,
            [
                {"role": "system", "content": "Follow the manifest."},
                {"role": "user", "content": "Task payload."},
            ],
        )

    def test_generic_cli_prompt_is_plain_markdown(self):
        result = to_generic_cli_prompt("Follow the manifest.", "Task payload.")

        self.assertEqual(
            result,
            "## Instructions\n\nFollow the manifest.\n\n## Payload\n\nTask payload.",
        )

    def test_build_prompt_payload_dispatches_by_dialect(self):
        self.assertIsInstance(build_prompt_payload("openai", "I", "P"), list)
        self.assertIn("<instructions>", build_prompt_payload("anthropic", "I", "P"))
        self.assertIn("## Instructions", build_prompt_payload("cli", "I", "P"))

    def test_unknown_dialect_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            build_prompt_payload("unknown", "I", "P")

        self.assertIn("Unsupported dialect", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_dialects -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'orchestrator_core.dialects'`.

- [ ] **Step 3: Write the minimal implementation**

Create `orchestrator_core/dialects.py`:

```python
from typing import Any, Dict, List, Union


PromptPayload = Union[str, List[Dict[str, str]]]


def _clean(value: str) -> str:
    return value.strip()


def to_anthropic_xml(instructions: str, payload: str) -> str:
    return (
        f"<instructions>\n{_clean(instructions)}\n</instructions>\n\n"
        f"<payload>\n{_clean(payload)}\n</payload>"
    )


def to_openai_messages(instructions: str, payload: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": _clean(instructions)},
        {"role": "user", "content": _clean(payload)},
    ]


def to_generic_cli_prompt(instructions: str, payload: str) -> str:
    return f"## Instructions\n\n{_clean(instructions)}\n\n## Payload\n\n{_clean(payload)}"


def build_prompt_payload(dialect: str, instructions: str, payload: str) -> PromptPayload:
    normalized = dialect.lower().strip()
    if normalized in {"anthropic", "claude"}:
        return to_anthropic_xml(instructions, payload)
    if normalized in {"openai", "responses"}:
        return to_openai_messages(instructions, payload)
    if normalized in {"cli", "generic"}:
        return to_generic_cli_prompt(instructions, payload)
    raise ValueError(f"Unsupported dialect: {dialect}")
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
python3 -m unittest tests.test_dialects -v
```

Expected: PASS with `Ran 5 tests`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_dialects.py orchestrator_core/dialects.py
git commit -m "feat: add prompt dialect transformations"
```

### Task 3: Tool Binding Adapters

**Files:**

- Create: `tests/test_tool_binding.py`
- Create: `orchestrator_core/tool_binding.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tool_binding.py`:

```python
import unittest

from orchestrator_core.tool_binding import bind_tools_for_anthropic, bind_tools_for_openai


MANIFEST = {
    "name": "echo",
    "version": "1.0.0",
    "description": "Echo input text.",
    "input_schema": {"type": "object", "properties": {}},
    "outputs": {"type": "text"},
    "tools": [
        {
            "name": "echo_text",
            "description": "Echo text through CLI.",
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        }
    ],
}


class ToolBindingTests(unittest.TestCase):
    def test_openai_tool_binding_uses_function_shape(self):
        result = bind_tools_for_openai(MANIFEST)

        self.assertEqual(
            result,
            [
                {
                    "type": "function",
                    "function": {
                        "name": "echo_text",
                        "description": "Echo text through CLI.",
                        "parameters": {
                            "type": "object",
                            "properties": {"text": {"type": "string"}},
                            "required": ["text"],
                        },
                    },
                }
            ],
        )

    def test_anthropic_tool_binding_uses_input_schema_shape(self):
        result = bind_tools_for_anthropic(MANIFEST)

        self.assertEqual(
            result,
            [
                {
                    "name": "echo_text",
                    "description": "Echo text through CLI.",
                    "input_schema": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                    },
                }
            ],
        )

    def test_missing_tool_schema_is_rejected(self):
        bad_manifest = dict(MANIFEST)
        bad_manifest["tools"] = [{"name": "bad"}]

        with self.assertRaises(ValueError) as ctx:
            bind_tools_for_openai(bad_manifest)

        self.assertIn("description", str(ctx.exception))
        self.assertIn("input_schema", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_tool_binding -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'orchestrator_core.tool_binding'`.

- [ ] **Step 3: Write the minimal implementation**

Create `orchestrator_core/tool_binding.py`:

```python
from typing import Any, Dict, List


REQUIRED_TOOL_FIELDS = ("name", "description", "input_schema")


def _manifest_tools(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    tools = manifest.get("tools", [])
    if not isinstance(tools, list):
        raise ValueError("manifest tools must be a list")
    for tool in tools:
        missing = [field for field in REQUIRED_TOOL_FIELDS if field not in tool]
        if missing:
            name = tool.get("name", "<unnamed>")
            raise ValueError(f"Tool {name} missing required fields: {', '.join(missing)}")
        if not isinstance(tool["input_schema"], dict):
            raise ValueError(f"Tool {tool['name']} input_schema must be an object")
    return tools


def bind_tools_for_openai(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": str(tool["name"]),
                "description": str(tool["description"]),
                "parameters": dict(tool["input_schema"]),
            },
        }
        for tool in _manifest_tools(manifest)
    ]


def bind_tools_for_anthropic(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "name": str(tool["name"]),
            "description": str(tool["description"]),
            "input_schema": dict(tool["input_schema"]),
        }
        for tool in _manifest_tools(manifest)
    ]
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
python3 -m unittest tests.test_tool_binding -v
```

Expected: PASS with `Ran 3 tests`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_tool_binding.py orchestrator_core/tool_binding.py
git commit -m "feat: add native tool binding adapters"
```

### Task 4: Protocol Normalization To Universal CLI Commands

**Files:**

- Create: `tests/test_protocol.py`
- Create: `orchestrator_core/protocol.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_protocol.py`:

```python
import json
import unittest
from pathlib import Path

from orchestrator_core.protocol import CliCommand, normalize_tool_call


TOOL_PATHS = {"echo_text": Path("/tmp/plugin/tools/echo_text")}


class ProtocolTests(unittest.TestCase):
    def test_normalizes_openai_function_call(self):
        native = {
            "type": "function_call",
            "name": "echo_text",
            "arguments": json.dumps({"text": "hello"}),
        }

        command = normalize_tool_call("openai", native, TOOL_PATHS)

        self.assertEqual(command, CliCommand(executable=Path("/tmp/plugin/tools/echo_text"), arguments={"text": "hello"}))

    def test_normalizes_anthropic_tool_use(self):
        native = {
            "type": "tool_use",
            "name": "echo_text",
            "input": {"text": "hello"},
        }

        command = normalize_tool_call("anthropic", native, TOOL_PATHS)

        self.assertEqual(command, CliCommand(executable=Path("/tmp/plugin/tools/echo_text"), arguments={"text": "hello"}))

    def test_rejects_unknown_tool(self):
        native = {"type": "tool_use", "name": "missing", "input": {}}

        with self.assertRaises(ValueError) as ctx:
            normalize_tool_call("anthropic", native, TOOL_PATHS)

        self.assertIn("Unknown tool", str(ctx.exception))

    def test_rejects_unknown_protocol(self):
        with self.assertRaises(ValueError) as ctx:
            normalize_tool_call("unknown", {}, TOOL_PATHS)

        self.assertIn("Unsupported protocol", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_protocol -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'orchestrator_core.protocol'`.

- [ ] **Step 3: Write the minimal implementation**

Create `orchestrator_core/protocol.py`:

```python
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True)
class CliCommand:
    executable: Path
    arguments: Dict[str, Any]


def _tool_path(name: str, tool_paths: Dict[str, Path]) -> Path:
    if name not in tool_paths:
        raise ValueError(f"Unknown tool: {name}")
    return tool_paths[name]


def _openai_arguments(native_call: Dict[str, Any]) -> Dict[str, Any]:
    raw_arguments = native_call.get("arguments", "{}")
    if isinstance(raw_arguments, str):
        parsed = json.loads(raw_arguments)
    else:
        parsed = raw_arguments
    if not isinstance(parsed, dict):
        raise ValueError("OpenAI function arguments must decode to an object")
    return parsed


def _anthropic_arguments(native_call: Dict[str, Any]) -> Dict[str, Any]:
    parsed = native_call.get("input", {})
    if not isinstance(parsed, dict):
        raise ValueError("Anthropic tool input must be an object")
    return parsed


def normalize_tool_call(protocol: str, native_call: Dict[str, Any], tool_paths: Dict[str, Path]) -> CliCommand:
    normalized = protocol.lower().strip()
    if normalized in {"openai", "responses"}:
        name = str(native_call.get("name", ""))
        return CliCommand(executable=_tool_path(name, tool_paths), arguments=_openai_arguments(native_call))
    if normalized in {"anthropic", "claude"}:
        name = str(native_call.get("name", ""))
        return CliCommand(executable=_tool_path(name, tool_paths), arguments=_anthropic_arguments(native_call))
    raise ValueError(f"Unsupported protocol: {protocol}")
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
python3 -m unittest tests.test_protocol -v
```

Expected: PASS with `Ran 4 tests`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_protocol.py orchestrator_core/protocol.py
git commit -m "feat: normalize model tool calls"
```

### Task 5: Local Project Persistence

**Files:**

- Create: `tests/test_persistence.py`
- Create: `orchestrator_core/persistence.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_persistence.py`:

```python
import tempfile
import unittest
from pathlib import Path

from orchestrator_core.persistence import (
    project_state_dir,
    read_project_json,
    stable_workspace_id,
    write_project_json,
)


class PersistenceTests(unittest.TestCase):
    def test_workspace_id_is_stable_and_path_safe(self):
        first = stable_workspace_id("/tmp/My Project")
        second = stable_workspace_id("/tmp/My Project/")

        self.assertEqual(first, second)
        self.assertRegex(first, r"^[a-f0-9]{16}$")

    def test_project_state_dir_lives_under_plugin_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin_root = Path(tmp) / "plugin"
            result = project_state_dir(plugin_root, "/workspace/app")

            self.assertEqual(result.parent, plugin_root / "projects")
            self.assertTrue(result.name)

    def test_write_and_read_project_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin_root = Path(tmp) / "plugin"
            payload = {"queue": {"status": "Ready"}}

            path = write_project_json(plugin_root, "/workspace/app", "queue.json", payload)
            loaded = read_project_json(plugin_root, "/workspace/app", "queue.json")

            self.assertTrue(path.exists())
            self.assertEqual(loaded, payload)

    def test_missing_project_json_returns_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin_root = Path(tmp) / "plugin"

            loaded = read_project_json(plugin_root, "/workspace/app", "missing.json", default={"ok": True})

            self.assertEqual(loaded, {"ok": True})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_persistence -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'orchestrator_core.persistence'`.

- [ ] **Step 3: Write the minimal implementation**

Create `orchestrator_core/persistence.py`:

```python
import hashlib
import json
from pathlib import Path
from typing import Any


def stable_workspace_id(workspace_root: str) -> str:
    normalized = str(Path(workspace_root).expanduser().resolve(strict=False))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def project_state_dir(plugin_root: Path, workspace_root: str) -> Path:
    return Path(plugin_root) / "projects" / stable_workspace_id(workspace_root)


def write_project_json(plugin_root: Path, workspace_root: str, filename: str, payload: Any) -> Path:
    state_dir = project_state_dir(plugin_root, workspace_root)
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_project_json(plugin_root: Path, workspace_root: str, filename: str, default: Any = None) -> Any:
    path = project_state_dir(plugin_root, workspace_root) / filename
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
python3 -m unittest tests.test_persistence -v
```

Expected: PASS with `Ran 4 tests`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_persistence.py orchestrator_core/persistence.py
git commit -m "feat: add plugin-owned project persistence"
```

### Task 6: Event Factories, Retry Injection, And Meta-Agent Proposals

**Files:**

- Create: `tests/test_events_and_reducers.py`
- Create: `orchestrator_core/events.py`
- Create: `orchestrator_core/meta_agent.py`
- Modify: `orchestrator_core/reducers.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_events_and_reducers.py`:

```python
import unittest

from orchestrator_core.events import (
    artifact_generated,
    circuit_breaker_tripped,
    worker_spawned,
)
from orchestrator_core.main import init_workflow
from orchestrator_core.meta_agent import propose_instruction_update
from orchestrator_core.reducers import reduce_queue_state
from orchestrator_core.state import Event, TaskState


class EventsAndReducersTests(unittest.TestCase):
    def test_event_factories_create_immutable_event_records(self):
        self.assertEqual(worker_spawned("stage_1").type, "WorkerSpawnedEvent")
        self.assertEqual(artifact_generated("stage_1", "content").payload["artifact"], "content")
        self.assertEqual(circuit_breaker_tripped("stage_1", ["bad"]).payload["critiques"], ["bad"])

    def test_task_failure_appends_structured_failure_context(self):
        state = init_workflow("attendance", "create")

        updated = reduce_queue_state(
            state,
            Event(
                "TaskFailedEvent",
                {
                    "task_id": "stage_1",
                    "critique": "Missing scenario",
                    "failure_context": {"attempt": 1, "artifact_path": "test-plan.md"},
                },
            ),
        )

        task = updated.tasks["stage_1"]
        self.assertEqual(task.state, TaskState.READY)
        self.assertEqual(task.retry_count, 1)
        self.assertEqual(task.critiques, ["Missing scenario"])
        self.assertEqual(updated.events_history[-1].payload["failure_context"]["artifact_path"], "test-plan.md")

    def test_circuit_breaker_uses_task_max_retries(self):
        state = init_workflow("attendance", "create")
        state = reduce_queue_state(state, Event("TaskFailedEvent", {"task_id": "stage_1", "critique": "first"}))
        state = reduce_queue_state(state, Event("TaskFailedEvent", {"task_id": "stage_1", "critique": "second"}))
        state = reduce_queue_state(state, Event("TaskFailedEvent", {"task_id": "stage_1", "critique": "third"}))

        task = state.tasks["stage_1"]

        self.assertEqual(task.state, TaskState.BLOCKED_REQUIRES_REVIEW)
        self.assertEqual(task.retry_count, 3)
        self.assertEqual(task.critiques, ["first", "second", "third"])

    def test_meta_agent_proposes_authorization_gated_update(self):
        proposal = propose_instruction_update(
            "stage_2",
            ["Missing widget table", "Missing semantics section"],
        )

        self.assertEqual(proposal["operation"], "Update")
        self.assertEqual(proposal["requires_authorization"], "IMPLEMENTATION APPROVED")
        self.assertIn("stage_2", proposal["summary"])
        self.assertIn("Missing widget table", proposal["candidate_instruction"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_events_and_reducers -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'orchestrator_core.events'`.

- [ ] **Step 3: Add event factory helpers**

Create `orchestrator_core/events.py`:

```python
from typing import Any, Dict, List

from .state import Event


def worker_spawned(task_id: str, model: str = "default") -> Event:
    return Event("WorkerSpawnedEvent", {"task_id": task_id, "model": model})


def artifact_generated(task_id: str, artifact: str) -> Event:
    return Event("ArtifactGeneratedEvent", {"task_id": task_id, "artifact": artifact})


def task_failed(task_id: str, critique: str, failure_context: Dict[str, Any] | None = None) -> Event:
    payload: Dict[str, Any] = {"task_id": task_id, "critique": critique}
    if failure_context is not None:
        payload["failure_context"] = failure_context
    return Event("TaskFailedEvent", payload)


def circuit_breaker_tripped(task_id: str, critiques: List[str]) -> Event:
    return Event("CircuitBreakerTrippedEvent", {"task_id": task_id, "critiques": list(critiques)})
```

- [ ] **Step 4: Add deterministic meta-agent proposal helper**

Create `orchestrator_core/meta_agent.py`:

```python
from typing import Dict, List


def propose_instruction_update(task_id: str, critiques: List[str]) -> Dict[str, str]:
    critique_lines = "\n".join(f"- {critique}" for critique in critiques)
    return {
        "operation": "Update",
        "requires_authorization": "IMPLEMENTATION APPROVED",
        "summary": f"Instruction update proposal for {task_id} after repeated evaluator failures.",
        "candidate_instruction": (
            f"For {task_id}, address these evaluator failures before returning an artifact:\n"
            f"{critique_lines}"
        ),
    }
```

- [ ] **Step 5: Modify reducer retry logic to use each task's max retries**

In `orchestrator_core/reducers.py`, replace only this function body:

```python
def handle_task_failed(state: QueueState, event: Event, max_retries: int = 3) -> QueueState:
    task_id = event.payload.get("task_id")
    critique = event.payload.get("critique")
    
    if not task_id or task_id not in state.tasks:
        return state
        
    task = state.tasks[task_id]
    new_retry_count = task.retry_count + 1
    new_critiques = task.critiques + [critique] if critique else task.critiques
    
    retry_limit = task.max_retries if task.max_retries is not None else max_retries
    if new_retry_count >= retry_limit:
        new_task_state = TaskState.BLOCKED_REQUIRES_REVIEW
    else:
        new_task_state = TaskState.READY 
        
    failed_task = replace(task, 
        state=new_task_state,
        retry_count=new_retry_count,
        critiques=new_critiques
    )
    
    new_tasks = state.tasks.copy()
    new_tasks[task_id] = failed_task
    
    return replace(state, 
        tasks=new_tasks,
        events_history=state.events_history + [event]
    )
```

- [ ] **Step 6: Run the test to verify it passes**

Run:

```bash
python3 -m unittest tests.test_events_and_reducers -v
```

Expected: PASS with `Ran 4 tests`.

- [ ] **Step 7: Commit**

```bash
git add tests/test_events_and_reducers.py orchestrator_core/events.py orchestrator_core/meta_agent.py orchestrator_core/reducers.py
git commit -m "feat: add event factories and retry proposals"
```

### Task 7: MCP Server Integration With Universal Skills

**Files:**

- Create: `tests/test_mcp_server.py`
- Modify: `orchestrator_core/mcp_server.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mcp_server.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from orchestrator_core.mcp_server import process_message


def make_skill(root: Path):
    skill = root / "echo"
    skill.mkdir(parents=True)
    (skill / "manifest.json").write_text(
        json.dumps(
            {
                "name": "echo",
                "version": "1.0.0",
                "description": "Echo input text.",
                "input_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
                "outputs": {"type": "text"},
                "tools": [],
            }
        ),
        encoding="utf-8",
    )
    (skill / "instructions.md").write_text("Echo the input text.", encoding="utf-8")


class McpServerTests(unittest.TestCase):
    def test_tools_list_reads_universal_skill_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = Path(tmp) / "skills"
            make_skill(skills_root)
            message = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

            response = json.loads(process_message(message, str(skills_root)))

            self.assertEqual(response["result"]["tools"][0]["name"], "echo")
            self.assertEqual(response["result"]["tools"][0]["inputSchema"]["required"], ["text"])

    def test_tools_call_returns_queued_task_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = Path(tmp) / "skills"
            make_skill(skills_root)
            message = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "echo", "arguments": {"text": "hello"}},
                }
            )

            response = json.loads(process_message(message, str(skills_root)))

            self.assertEqual(response["id"], 2)
            self.assertIn("Queued task echo", response["result"]["content"][0]["text"])

    def test_tools_call_rejects_unknown_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            message = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "missing", "arguments": {}},
                }
            )

            response = json.loads(process_message(message, tmp))

            self.assertEqual(response["error"]["code"], -32602)
            self.assertIn("Unknown tool", response["error"]["message"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify current behavior fails**

Run:

```bash
python3 -m unittest tests.test_mcp_server -v
```

Expected: FAIL because unknown `tools/call` currently returns a queued response instead of `-32602`.

- [ ] **Step 3: Modify MCP server to use `SkillPackage` discovery**

In `orchestrator_core/mcp_server.py`, replace the `read_manifests`, `handle_list_tools`, and `tools/call` handling with this code while preserving `initialize`, unknown method handling, `process_message`, and `main`:

```python
from .skill_package import list_skill_packages


def read_manifests(skills_dir: str) -> List[Dict[str, Any]]:
    return [package.manifest for package in list_skill_packages(Path(skills_dir))]


def handle_list_tools(manifests: List[Dict[str, Any]]) -> Dict[str, Any]:
    tools = []
    for manifest in manifests:
        tools.append({
            "name": manifest.get("name"),
            "description": manifest.get("description"),
            "inputSchema": manifest.get("input_schema", {"type": "object", "properties": {}})
        })
    return {"tools": tools}


def _handle_tools_call(params: Dict[str, Any], skills_dir: str) -> Dict[str, Any]:
    name = params.get("name")
    args = params.get("arguments", {})
    packages = {package.name: package for package in list_skill_packages(Path(skills_dir))}
    if name not in packages:
        raise ValueError(f"Unknown tool: {name}")
    return {
        "content": [{"type": "text", "text": f"Queued task {name} for execution with args: {args}"}]
    }
```

Then update the `tools/call` branch inside `process_message` to:

```python
elif method == "tools/call":
    response["result"] = _handle_tools_call(msg.get("params", {}), skills_dir)
```

And update exception handling inside `process_message` to distinguish invalid params:

```python
    except ValueError as e:
        response["error"] = {"code": -32602, "message": str(e)}
    except Exception as e:
        response["error"] = {"code": -32603, "message": str(e)}
```

- [ ] **Step 4: Run the MCP server tests**

Run:

```bash
python3 -m unittest tests.test_mcp_server -v
```

Expected: PASS with `Ran 3 tests`.

- [ ] **Step 5: Run the full root test suite**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: PASS for all tests created in Tasks 1-7.

- [ ] **Step 6: Commit**

```bash
git add tests/test_mcp_server.py orchestrator_core/mcp_server.py
git commit -m "feat: wire MCP server to universal skills"
```

### Task 8: Mirror Runtime Modules Into Plugin Package

**Files:**

- Modify: `maestro-e2e-plugin/orchestrator_core/reducers.py`
- Modify: `maestro-e2e-plugin/orchestrator_core/mcp_server.py`
- Create: `maestro-e2e-plugin/orchestrator_core/skill_package.py`
- Create: `maestro-e2e-plugin/orchestrator_core/dialects.py`
- Create: `maestro-e2e-plugin/orchestrator_core/tool_binding.py`
- Create: `maestro-e2e-plugin/orchestrator_core/protocol.py`
- Create: `maestro-e2e-plugin/orchestrator_core/persistence.py`
- Create: `maestro-e2e-plugin/orchestrator_core/events.py`
- Create: `maestro-e2e-plugin/orchestrator_core/meta_agent.py`

- [ ] **Step 1: Copy the tested root runtime modules into the plugin package**

Run:

```bash
cp orchestrator_core/skill_package.py maestro-e2e-plugin/orchestrator_core/skill_package.py
cp orchestrator_core/dialects.py maestro-e2e-plugin/orchestrator_core/dialects.py
cp orchestrator_core/tool_binding.py maestro-e2e-plugin/orchestrator_core/tool_binding.py
cp orchestrator_core/protocol.py maestro-e2e-plugin/orchestrator_core/protocol.py
cp orchestrator_core/persistence.py maestro-e2e-plugin/orchestrator_core/persistence.py
cp orchestrator_core/events.py maestro-e2e-plugin/orchestrator_core/events.py
cp orchestrator_core/meta_agent.py maestro-e2e-plugin/orchestrator_core/meta_agent.py
cp orchestrator_core/reducers.py maestro-e2e-plugin/orchestrator_core/reducers.py
cp orchestrator_core/mcp_server.py maestro-e2e-plugin/orchestrator_core/mcp_server.py
```

Expected: commands complete without output.

- [ ] **Step 2: Compile both runtime copies**

Run:

```bash
python3 -m py_compile orchestrator_core/*.py maestro-e2e-plugin/orchestrator_core/*.py
```

Expected: command exits `0`.

- [ ] **Step 3: Run the full test suite again**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: PASS for all tests.

- [ ] **Step 4: Commit**

```bash
git add maestro-e2e-plugin/orchestrator_core/skill_package.py maestro-e2e-plugin/orchestrator_core/dialects.py maestro-e2e-plugin/orchestrator_core/tool_binding.py maestro-e2e-plugin/orchestrator_core/protocol.py maestro-e2e-plugin/orchestrator_core/persistence.py maestro-e2e-plugin/orchestrator_core/events.py maestro-e2e-plugin/orchestrator_core/meta_agent.py maestro-e2e-plugin/orchestrator_core/reducers.py maestro-e2e-plugin/orchestrator_core/mcp_server.py
git commit -m "feat: package adapter runtime modules"
```

### Task 9: Scaffold A Sample Universal Skill Fixture

**Files:**

- Create: `maestro-e2e-plugin/skills/example_echo/manifest.json`
- Create: `maestro-e2e-plugin/skills/example_echo/instructions.md`
- Create: `maestro-e2e-plugin/skills/example_echo/tools/echo_text`

- [ ] **Step 1: Add the sample manifest**

Create `maestro-e2e-plugin/skills/example_echo/manifest.json`:

```json
{
  "name": "example_echo",
  "version": "1.0.0",
  "description": "Example universal skill that echoes input text.",
  "input_schema": {
    "type": "object",
    "properties": {
      "text": {
        "type": "string"
      }
    },
    "required": ["text"]
  },
  "outputs": {
    "type": "text"
  },
  "tools": [
    {
      "name": "echo_text",
      "description": "Echo input text through a portable CLI executable.",
      "command": "echo_text",
      "input_schema": {
        "type": "object",
        "properties": {
          "text": {
            "type": "string"
          }
        },
        "required": ["text"]
      }
    }
  ]
}
```

- [ ] **Step 2: Add model-agnostic instructions**

Create `maestro-e2e-plugin/skills/example_echo/instructions.md`:

```markdown
# Example Echo Skill

Return the provided `text` value exactly once.

Do not add commentary, formatting, or surrounding quotes.
```

- [ ] **Step 3: Add the portable CLI tool**

Create `maestro-e2e-plugin/skills/example_echo/tools/echo_text`:

```bash
#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' "$1"
```

Then run:

```bash
chmod +x maestro-e2e-plugin/skills/example_echo/tools/echo_text
```

Expected: command exits `0`.

- [ ] **Step 4: Verify MCP tool discovery sees the sample skill**

Run:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 -m orchestrator_core.mcp_server
```

Expected output contains:

```json
"name": "example_echo"
```

- [ ] **Step 5: Commit**

```bash
git add maestro-e2e-plugin/skills/example_echo/manifest.json maestro-e2e-plugin/skills/example_echo/instructions.md maestro-e2e-plugin/skills/example_echo/tools/echo_text
git commit -m "feat: add sample universal skill fixture"
```

### Task 10: Final Verification And Spec Coverage

**Files:**

- No source files unless a previous task failed verification.

- [ ] **Step 1: Run unit tests**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: PASS for all tests.

- [ ] **Step 2: Compile root and plugin runtime modules**

Run:

```bash
python3 -m py_compile orchestrator_core/*.py maestro-e2e-plugin/orchestrator_core/*.py
```

Expected: command exits `0`.

- [ ] **Step 3: Check MCP initialize response**

Run:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize"}' | python3 -m orchestrator_core.mcp_server
```

Expected output:

```json
{"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "agentic-orchestrator", "version": "1.0.0"}}}
```

- [ ] **Step 4: Check git status for accidental files**

Run:

```bash
git status --short
```

Expected: only intentional source, test, fixture, and plan files are modified or untracked. Do not include `__pycache__/` or `.pyc` files in commits.

## Self-Review

1. **Spec coverage:** The plan covers universal skill packages in Tasks 1 and 9; adapter middleware in Tasks 2-4; immutable state and dependency queue integration in Task 6; actor-critic, retry injection, circuit breaker, and meta-agent proposals in Task 6; hooks/events in Task 6; MCP and local persistence in Tasks 5 and 7; plugin distribution mirroring in Task 8.
2. **Placeholder scan:** The plan avoids deferred-work tokens, vague edge-case instructions, and unspecified test-writing steps. Every code-changing step includes concrete code or an exact command.
3. **Type consistency:** `SkillPackage`, `CliCommand`, `Event`, `QueueState`, and existing `TaskState` names are used consistently across tests and implementations. The reducer function names match the current `orchestrator_core/reducers.py`.
