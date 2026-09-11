"""check_delivery.py -- the machine-checkable client-engine delivery contract.

schemas/client-delivery.schema.json says what a delivered engine's manifest must
*look like*. This module says what must be *true* about the package the manifest
describes: that every referenced file exists, that its contents are the contents
that were approved, that the task graph is runnable, that no path escapes the
project, and that the engine does not reach back into the authoring plugin at
run time. A schema cannot express any of that, so a structurally valid manifest
alone is never sufficient evidence of a deliverable engine.

Why this module exists at all. references/schemas/author-proposal.schema.json
requires exactly one property -- a `files` map with at least two non-empty string
values. The 2026-09-09 authoring trial produced twelve Markdown files, satisfied
that schema completely, and delivered nothing anyone could run. The acceptance
case in tests/test_check_delivery.py pins that exact tree and requires this
module to reject it.

Two failure modes, deliberately distinguished:

  * A *rejection* is a verdict about the package. The checker read everything it
    needed and the package is not deliverable. Callers get
    ``{"status": "rejected", "problems": [...]}`` with every problem found, not
    just the first -- a caller fixing a package wants the whole list.
  * A *block* is the checker admitting it could not tell. Missing engine root,
    unparseable manifest, an engine root outside the project. These raise
    qc_lib.Blocked and exit 2, exactly like every other script in this package,
    because "I could not check" must never read as "I checked and it passed".

Determinism: problems are sorted by (code, path, detail) before returning, so the
same package always produces byte-identical output.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

import qc_lib

STAGE = "check_delivery"

#: Commands the delivered entry point must support. Section 2 of the delivery
#: plan: "The entry point supports starting a request, resuming an approved
#: request, and inspecting status."
REQUIRED_COMMANDS = ("start", "resume", "status")

#: Substrings that mean the declared dependency set names an interpreter and a
#: host. Checked as substrings rather than exact strings so a version bound
#: ("python>=3.12") satisfies the interpreter requirement.
REQUIRED_DEPENDENCY_HINTS = ("python", "claude")

#: Module names that only exist inside the authoring plugin. An engine importing
#: any of them is not independently runnable, which defeats the whole delivery.
PLUGIN_MODULE_NAMES = frozenset(
    [
        "apply_author",
        "apply_upgrade",
        "author_state",
        "checkpoint_state",
        "classify_targets",
        "compile_workflow",
        "discover_workspace",
        "gate_defaults",
        "plan_interview",
        "qc_lib",
        "render_upgrade",
        "upgrade_state",
    ]
)

#: Text that means a template or role document still carries an unfilled slot.
#: `${...}` is deliberately absent: client test artifacts may legitimately use
#: their own runtime variables.
PLACEHOLDER_PATTERNS = (
    re.compile(r"\{\{[^}]*\}\}"),
    re.compile(r"<TODO[^>]*>"),
    re.compile(r"\bTODO\(fill\)", re.IGNORECASE),
    re.compile(r"\bTBD\b"),
    re.compile(r"\bTK\b"),
    re.compile(r"__[A-Z][A-Z0-9_]{2,}__"),
)

#: A role document must show what the role is responsible for and how it is
#: configured. Section 2: "Coordinator and worker definitions explicitly identify
#: responsibilities and model/tool settings."
ROLE_REQUIRED_MARKERS = (
    ("responsibilities", re.compile(r"responsibilit", re.IGNORECASE)),
    ("model settings", re.compile(r"model[_ ]?tier|model\s*:", re.IGNORECASE)),
    ("tool settings", re.compile(r"\btools?\s*:", re.IGNORECASE)),
)

IMPLEMENTATION_PLAN_REQUIRED_MARKERS = (
    ("client interview", re.compile(r"client interview", re.IGNORECASE)),
    ("requirements", re.compile(r"requirements", re.IGNORECASE)),
    ("implementation steps", re.compile(r"implementation steps", re.IGNORECASE)),
    ("validation", re.compile(r"validation", re.IGNORECASE)),
)

_CHECKSUM_RE = re.compile(r"^[a-f0-9]{64}$")
_MANIFEST_NAME = "manifest.json"

CHECKS = (
    "manifest_schema",
    "path_containment",
    "file_set_and_checksums",
    "task_graph",
    "role_definitions",
    "content_integrity",
    "independence",
)


class _Problems:
    """Accumulates every problem found instead of stopping at the first."""

    def __init__(self):
        self._items = []

    def add(self, code, detail, path=None):
        self._items.append({"code": code, "detail": detail, "path": path or ""})

    def __len__(self):
        return len(self._items)

    def sorted(self):
        return sorted(self._items, key=lambda item: (item["code"], item["path"], item["detail"]))


# -- path helpers -------------------------------------------------------------


def _safe_relative(raw, *, problems, field):
    """Return the normalized relative path, or None when it is unusable.

    Absolute paths and '..' escapes are rejected here rather than in
    qc_lib.normalize_path because a bad path in a manifest is a verdict about the
    package (collect and continue), not a reason to abort the whole check.
    """
    if not isinstance(raw, str) or not raw:
        problems.add("unsafe_path", f"{field} is not a non-empty string", str(raw))
        return None
    candidate = PurePosixPath(raw.replace("\\", "/"))
    if candidate.is_absolute():
        problems.add("unsafe_path", f"{field} '{raw}' is absolute", raw)
        return None
    if ".." in candidate.parts:
        problems.add("unsafe_path", f"{field} '{raw}' escapes through '..'", raw)
        return None
    return candidate


def _is_within(inner, outer):
    """True when `inner` is `outer` or sits underneath it."""
    inner_parts = inner.parts
    outer_parts = outer.parts
    return inner_parts[: len(outer_parts)] == outer_parts


def _resolves_inside(path, root):
    """True when `path` resolves (following symlinks) to somewhere under `root`."""
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
    except OSError:
        return False
    return resolved == root_resolved or root_resolved in resolved.parents


# -- manifest structure -------------------------------------------------------


def _check_manifest_schema(manifest, problems):
    """Hand-rolled validation of schemas/client-delivery.schema.json.

    Hand-rolled because this package is stdlib-only by policy (SKILL.md) and
    jsonschema is not a permitted dependency. The field list below mirrors the
    schema file exactly; the schema stays the published contract and this stays
    its executable twin.
    """
    required = (
        "schema_version",
        "engine_id",
        "source_revision",
        "engine_root",
        "artifact_root",
        "state_root",
        "client_specification",
        "implementation_plan",
        "entrypoint",
        "constants",
        "operations",
        "coordinator",
        "workers",
        "schemas",
        "templates",
        "adapters",
        "dependencies",
        "files",
    )
    for field in required:
        if field not in manifest:
            problems.add("manifest_schema_violation", f"missing required field '{field}'")
    for field in sorted(set(manifest) - set(required)):
        problems.add("manifest_schema_violation", f"unknown field '{field}'")

    if manifest.get("schema_version") != 1:
        problems.add(
            "manifest_schema_violation",
            f"schema_version must be 1, got {manifest.get('schema_version')!r}",
        )
    if manifest.get("constants") != "constants.json":
        problems.add(
            "manifest_schema_violation",
            f"constants must be 'constants.json', got {manifest.get('constants')!r}",
        )
    for field, expected in (
        ("client_specification", "client-spec.json"),
        ("implementation_plan", "IMPLEMENTATION_PLAN.md"),
    ):
        if manifest.get(field) != expected:
            problems.add(
                "manifest_schema_violation",
                f"{field} must be '{expected}', got {manifest.get(field)!r}",
            )

    for field in ("engine_id", "source_revision"):
        value = manifest.get(field)
        if field in manifest and (not isinstance(value, str) or not value):
            problems.add("manifest_schema_violation", f"{field} must be a non-empty string")

    for field in ("operations", "schemas", "templates", "adapters"):
        value = manifest.get(field)
        if field not in manifest:
            continue
        if not isinstance(value, dict) or not value:
            problems.add("manifest_schema_violation", f"{field} must be a non-empty object")
            continue
        for key, entry in sorted(value.items()):
            if not isinstance(entry, str) or not entry:
                problems.add(
                    "manifest_schema_violation", f"{field}['{key}'] must be a non-empty path"
                )

    workers = manifest.get("workers")
    if "workers" in manifest:
        if not isinstance(workers, list) or not workers:
            problems.add("manifest_schema_violation", "workers must be a non-empty array")
        else:
            for index, worker in enumerate(workers):
                _check_worker_schema(worker, index, problems)

    dependencies = manifest.get("dependencies")
    if "dependencies" in manifest:
        if not isinstance(dependencies, list):
            problems.add("manifest_schema_violation", "dependencies must be an array")
        elif len(set(dependencies)) != len(dependencies):
            problems.add("manifest_schema_violation", "dependencies contains duplicates")

    files = manifest.get("files")
    if "files" in manifest:
        if not isinstance(files, dict) or not files:
            problems.add("manifest_schema_violation", "files must be a non-empty object")
        else:
            for name, digest in sorted(files.items()):
                if not isinstance(digest, str) or not _CHECKSUM_RE.match(digest):
                    problems.add(
                        "manifest_schema_violation",
                        f"files['{name}'] is not a lowercase hex SHA-256 digest",
                        name,
                    )


def _check_worker_schema(worker, index, problems):
    required = ("id", "definition", "input_schema", "output_schema", "capabilities")
    if not isinstance(worker, dict):
        problems.add("manifest_schema_violation", f"workers[{index}] must be an object")
        return
    for field in required:
        if field not in worker:
            problems.add(
                "manifest_schema_violation", f"workers[{index}] missing required field '{field}'"
            )
    for field in sorted(set(worker) - set(required)):
        problems.add("manifest_schema_violation", f"workers[{index}] has unknown field '{field}'")
    capabilities = worker.get("capabilities")
    if "capabilities" in worker:
        if not isinstance(capabilities, list) or not all(
            isinstance(item, str) and item for item in capabilities
        ):
            problems.add(
                "manifest_schema_violation",
                f"workers[{index}].capabilities must be an array of non-empty strings",
            )
        elif len(set(capabilities)) != len(capabilities):
            problems.add(
                "manifest_schema_violation", f"workers[{index}].capabilities contains duplicates"
            )


# -- individual checks --------------------------------------------------------


def _check_path_containment(manifest, engine_rel, problems):
    engine_declared = _safe_relative(
        manifest.get("engine_root", ""), problems=problems, field="engine_root"
    )
    artifact = _safe_relative(
        manifest.get("artifact_root", ""), problems=problems, field="artifact_root"
    )
    state = _safe_relative(manifest.get("state_root", ""), problems=problems, field="state_root")

    if engine_declared is not None and engine_declared != engine_rel:
        problems.add(
            "engine_root_mismatch",
            f"manifest declares engine_root '{engine_declared}' but the package was checked at "
            f"'{engine_rel}'",
            str(engine_declared),
        )

    if engine_declared is not None and artifact is not None:
        if engine_declared == artifact:
            problems.add(
                "nested_roots",
                f"engine_root and artifact_root are the same path '{artifact}'",
                str(artifact),
            )
        elif _is_within(artifact, engine_declared):
            problems.add(
                "nested_roots",
                f"artifact_root '{artifact}' sits inside engine_root '{engine_declared}'",
                str(artifact),
            )
        elif _is_within(engine_declared, artifact):
            problems.add(
                "nested_roots",
                f"engine_root '{engine_declared}' sits inside artifact_root '{artifact}'",
                str(engine_declared),
            )

    if state is not None and artifact is not None and _is_within(state, artifact):
        problems.add(
            "nested_roots",
            f"state_root '{state}' sits inside artifact_root '{artifact}'",
            str(state),
        )

    # Every other declared path is engine-relative and must stay inside it.
    for field in ("client_specification", "implementation_plan", "entrypoint", "constants", "coordinator"):
        _safe_relative(manifest.get(field, ""), problems=problems, field=field)
    for group in ("operations", "schemas", "templates", "adapters"):
        entries = manifest.get(group)
        if isinstance(entries, dict):
            for key, value in sorted(entries.items()):
                _safe_relative(value, problems=problems, field=f"{group}['{key}']")
    workers = manifest.get("workers")
    if isinstance(workers, list):
        for index, worker in enumerate(workers):
            if not isinstance(worker, dict):
                continue
            for field in ("definition", "input_schema", "output_schema"):
                _safe_relative(
                    worker.get(field, ""), problems=problems, field=f"workers[{index}].{field}"
                )


def _runtime_state_subtree(manifest, engine_root, project_root):
    """Return an engine-relative runtime state root when the client places it inside the engine."""
    state_root = manifest.get("state_root")
    if not isinstance(state_root, str):
        return None
    try:
        candidate = (project_root / PurePosixPath(state_root)).resolve()
        return candidate.relative_to(engine_root.resolve()).as_posix()
    except ValueError:
        return None


def _shipped_files(engine_root, problems, runtime_state_subtree=None):
    """Every regular file under the engine root, keyed by engine-relative path.

    A symlink pointing outside the engine root is reported and excluded: the
    delivered package must be self-contained, and a link out of it is exactly the
    escape the containment rules exist to stop.
    """
    shipped = {}
    for path in sorted(engine_root.rglob("*")):
        if path.is_symlink() and not _resolves_inside(path, engine_root):
            rel = path.relative_to(engine_root).as_posix()
            problems.add("unsafe_path", f"'{rel}' is a symlink pointing outside the engine", rel)
            continue
        if not path.is_file():
            continue
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(engine_root).as_posix()
        if rel == _MANIFEST_NAME:
            continue
        if runtime_state_subtree and (rel == runtime_state_subtree or rel.startswith(runtime_state_subtree + "/")):
            continue
        shipped[rel] = path
    return shipped


def _check_file_set(manifest, engine_root, shipped, problems):
    declared = manifest.get("files")
    if not isinstance(declared, dict):
        return

    if _MANIFEST_NAME in declared:
        problems.add(
            "manifest_self_reference",
            "files must not contain manifest.json; the approval record protects the manifest",
            _MANIFEST_NAME,
        )

    for rel in sorted(set(declared) - {_MANIFEST_NAME}):
        path = shipped.get(rel)
        if path is None:
            problems.add("missing_file", f"files declares '{rel}' but no such file was shipped", rel)
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != declared[rel]:
            problems.add(
                "checksum_mismatch",
                f"'{rel}' has digest {digest} but the manifest recorded {declared[rel]}",
                rel,
            )

    for rel in sorted(set(shipped) - set(declared)):
        problems.add("undeclared_file", f"'{rel}' was shipped but is absent from files", rel)


def _referenced_paths(manifest):
    """Every engine-relative path the manifest points at, with its field label."""
    references = []
    for field in ("client_specification", "implementation_plan", "entrypoint", "constants", "coordinator"):
        value = manifest.get(field)
        if isinstance(value, str) and value:
            references.append((field, value))
    for group in ("operations", "schemas", "templates", "adapters"):
        entries = manifest.get(group)
        if isinstance(entries, dict):
            for key, value in sorted(entries.items()):
                if isinstance(value, str) and value:
                    references.append((f"{group}['{key}']", value))
    workers = manifest.get("workers")
    if isinstance(workers, list):
        for index, worker in enumerate(workers):
            if not isinstance(worker, dict):
                continue
            for field in ("definition", "input_schema", "output_schema"):
                value = worker.get(field)
                if isinstance(value, str) and value:
                    references.append((f"workers[{index}].{field}", value))
    return references


def _check_references_exist(manifest, shipped, problems):
    for label, rel in _referenced_paths(manifest):
        if rel.startswith("/") or ".." in PurePosixPath(rel).parts:
            continue  # already reported by path containment
        if rel not in shipped:
            problems.add("missing_file", f"{label} points at '{rel}', which was not shipped", rel)


def _check_task_graph(manifest, engine_root, shipped, problems):
    workers = manifest.get("workers")
    if not isinstance(workers, list):
        return
    worker_ids = []
    for worker in workers:
        if isinstance(worker, dict) and isinstance(worker.get("id"), str):
            worker_ids.append(worker["id"])
    for worker_id in sorted({wid for wid in worker_ids if worker_ids.count(wid) > 1}):
        problems.add("duplicate_worker_id", f"worker id '{worker_id}' is declared more than once")
    declared_ids = set(worker_ids)

    used_ids = set()
    operations = manifest.get("operations")
    if not isinstance(operations, dict):
        return
    for operation_id, rel in sorted(operations.items()):
        path = shipped.get(rel)
        if path is None:
            continue  # missing-file already reported
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            problems.add("malformed_operation", f"'{rel}' is not readable JSON: {exc}", rel)
            continue
        tasks = body.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            problems.add("malformed_operation", f"'{rel}' declares no tasks", rel)
            continue
        used_ids |= _check_operation_tasks(operation_id, rel, tasks, declared_ids, problems)

    for worker_id in sorted(declared_ids - used_ids):
        problems.add(
            "unused_worker", f"worker '{worker_id}' is declared but no operation task uses it"
        )


def _check_operation_tasks(operation_id, rel, tasks, declared_ids, problems):
    used_ids = set()
    task_ids = set()
    for task in tasks:
        if isinstance(task, dict) and isinstance(task.get("task_id"), str):
            task_ids.add(task["task_id"])

    edges = {}
    for task in tasks:
        if not isinstance(task, dict):
            problems.add("malformed_operation", f"'{rel}' has a task that is not an object", rel)
            continue
        task_id = task.get("task_id")
        worker = task.get("worker")
        depends_on = task.get("depends_on", [])
        if not isinstance(task_id, str) or not task_id:
            problems.add("malformed_operation", f"'{rel}' has a task with no task_id", rel)
            continue
        if not isinstance(worker, str) or worker not in declared_ids:
            problems.add(
                "undeclared_worker",
                f"{operation_id} task '{task_id}' names worker '{worker}', which is not declared",
                rel,
            )
        else:
            used_ids.add(worker)
        if not isinstance(depends_on, list):
            problems.add(
                "malformed_operation", f"'{rel}' task '{task_id}' has a non-array depends_on", rel
            )
            depends_on = []
        for dependency in depends_on:
            if dependency not in task_ids:
                problems.add(
                    "missing_dependency",
                    f"{operation_id} task '{task_id}' depends on '{dependency}', which does not "
                    "exist in this operation",
                    rel,
                )
        edges[task_id] = [dep for dep in depends_on if dep in task_ids]

    cycle = _find_cycle(edges)
    if cycle is not None:
        problems.add(
            "dependency_cycle",
            f"{operation_id} has a dependency cycle: {' -> '.join(cycle)}",
            rel,
        )
    return used_ids


def _find_cycle(edges):
    """Iterative depth-first search returning one cycle path, or None.

    Iterative rather than recursive so a pathological generated graph cannot
    blow the interpreter's stack and turn a rejection into a crash.
    """
    WHITE, GREY, BLACK = 0, 1, 2
    colors = {node: WHITE for node in edges}
    for start in sorted(edges):
        if colors[start] != WHITE:
            continue
        stack = [(start, iter(edges[start]))]
        path = [start]
        colors[start] = GREY
        while stack:
            node, children = stack[-1]
            advanced = False
            for child in children:
                if child not in colors:
                    continue
                if colors[child] == GREY:
                    return path[path.index(child) :] + [child]
                if colors[child] == WHITE:
                    colors[child] = GREY
                    path.append(child)
                    stack.append((child, iter(edges[child])))
                    advanced = True
                    break
            if not advanced:
                colors[node] = BLACK
                stack.pop()
                path.pop()
    return None


def _check_role_definitions(manifest, shipped, problems):
    roles = []
    coordinator = manifest.get("coordinator")
    if isinstance(coordinator, str):
        roles.append(("coordinator", coordinator))
    workers = manifest.get("workers")
    if isinstance(workers, list):
        for worker in workers:
            if isinstance(worker, dict) and isinstance(worker.get("definition"), str):
                roles.append((worker.get("id", "worker"), worker["definition"]))

    for role_id, rel in roles:
        path = shipped.get(rel)
        if path is None:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            problems.add("role_definition_incomplete", f"'{rel}' is not readable text", rel)
            continue
        missing = [label for label, pattern in ROLE_REQUIRED_MARKERS if not pattern.search(text)]
        if missing:
            problems.add(
                "role_definition_incomplete",
                f"role '{role_id}' definition '{rel}' does not state: {', '.join(missing)}",
                rel,
            )


def _check_content_integrity(manifest, engine_root, shipped, problems):
    checked = set()
    for label, rel in _referenced_paths(manifest):
        if rel in checked or rel not in shipped:
            continue
        checked.add(rel)
        path = shipped[rel]
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in PLACEHOLDER_PATTERNS:
            match = pattern.search(text)
            if match:
                problems.add(
                    "unresolved_placeholder",
                    f"'{rel}' still contains the unfilled slot {match.group(0)!r}",
                    rel,
                )
                break

    plan_path = manifest.get("implementation_plan")
    if isinstance(plan_path, str) and plan_path in shipped:
        plan_text = shipped[plan_path].read_text(encoding="utf-8")
        missing = [
            label for label, pattern in IMPLEMENTATION_PLAN_REQUIRED_MARKERS if not pattern.search(plan_text)
        ]
        if missing:
            problems.add(
                "implementation_plan_incomplete",
                f"'{plan_path}' does not state: {', '.join(missing)}",
                plan_path,
            )

    schemas = manifest.get("schemas")
    if isinstance(schemas, dict):
        for key, rel in sorted(schemas.items()):
            path = shipped.get(rel)
            if path is None:
                continue
            _check_schema_refs(rel, path, engine_root, problems)


def _check_schema_refs(rel, path, engine_root, problems):
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        problems.add("malformed_schema", f"'{rel}' is not readable JSON: {exc}", rel)
        return
    base = (engine_root / rel).parent
    for ref in _collect_refs(body):
        if ref.startswith("#"):
            continue
        if "://" in ref:
            problems.add(
                "unresolved_schema_ref",
                f"'{rel}' references '{ref}', which would require a network request",
                rel,
            )
            continue
        target = ref.split("#", 1)[0]
        if not target:
            continue
        candidate = PurePosixPath(target)
        if candidate.is_absolute() or ".." in candidate.parts:
            problems.add(
                "unresolved_schema_ref", f"'{rel}' references '{ref}' outside the engine", rel
            )
            continue
        if not (base / target).is_file():
            problems.add(
                "unresolved_schema_ref",
                f"'{rel}' references '{ref}', which does not resolve to a shipped file",
                rel,
            )


def _collect_refs(node):
    refs = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                refs.append(value)
            else:
                refs.extend(_collect_refs(value))
    elif isinstance(node, list):
        for item in node:
            refs.extend(_collect_refs(item))
    return refs


def _check_independence(manifest, shipped, problems):
    for rel, path in sorted(shipped.items()):
        if not rel.endswith(".py"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for module in sorted(PLUGIN_MODULE_NAMES):
            pattern = re.compile(rf"^\s*(?:import\s+{module}\b|from\s+{module}\b)", re.MULTILINE)
            if pattern.search(text):
                problems.add(
                    "plugin_dependency",
                    f"'{rel}' imports '{module}', which only exists inside the authoring plugin",
                    rel,
                )

    entrypoint = manifest.get("entrypoint")
    if isinstance(entrypoint, str) and entrypoint in shipped:
        try:
            text = shipped[entrypoint].read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = ""
        missing = [name for name in REQUIRED_COMMANDS if f"'{name}'" not in text and f'"{name}"' not in text]
        if missing:
            problems.add(
                "entrypoint_incomplete",
                f"entry point '{entrypoint}' does not support: {', '.join(missing)}",
                entrypoint,
            )

    dependencies = manifest.get("dependencies")
    if isinstance(dependencies, list):
        joined = " ".join(str(item).lower() for item in dependencies)
        missing = []
        if "python" not in joined:
            missing.append("python")
        adapters = manifest.get("adapters")
        if isinstance(adapters, dict) and adapters:
            for host_name in sorted(adapters.keys()):
                if host_name.lower() not in joined:
                    missing.append(host_name.lower())
        elif "claude" not in joined:
            missing.append("claude")
        if missing:
            problems.add(
                "dependency_incomplete",
                f"dependencies does not name: {', '.join(missing)}",
            )


# -- entry point --------------------------------------------------------------


def check_delivery(*, engine_root, project_root):
    """Check one delivered engine package. Returns a verdict; raises Blocked when undecidable."""
    engine_root = Path(engine_root)
    project_root = Path(project_root)

    if not engine_root.is_dir():
        raise qc_lib.Blocked(
            stage=STAGE,
            reason_code="missing_target",
            detail=f"engine root '{engine_root}' does not exist or is not a directory",
            recovery_action="pass the path of a generated engine package",
        )
    if not _resolves_inside(engine_root, project_root) or engine_root.resolve() == project_root.resolve():
        raise qc_lib.Blocked(
            stage=STAGE,
            reason_code="unsafe_path",
            detail=f"engine root '{engine_root}' is not a directory inside '{project_root}'",
            recovery_action="pass an engine root that sits under the client project root",
        )

    problems = _Problems()
    engine_rel = PurePosixPath(engine_root.resolve().relative_to(project_root.resolve()).as_posix())

    manifest_path = engine_root / _MANIFEST_NAME
    if not manifest_path.is_file():
        problems.add(
            "manifest_missing",
            f"no {_MANIFEST_NAME} at the engine root; a folder of documents is not an engine",
            _MANIFEST_NAME,
        )
        return _verdict(None, engine_rel, problems)

    manifest = qc_lib.load_json_file(str(manifest_path), stage=STAGE)
    if not isinstance(manifest, dict):
        raise qc_lib.Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"{_MANIFEST_NAME} must contain a JSON object",
            recovery_action="regenerate the manifest from the delivery compiler",
        )

    _check_manifest_schema(manifest, problems)
    _check_path_containment(manifest, engine_rel, problems)
    shipped = _shipped_files(
        engine_root,
        problems,
        _runtime_state_subtree(manifest, engine_root, project_root),
    )
    _check_file_set(manifest, engine_root, shipped, problems)
    _check_references_exist(manifest, shipped, problems)
    _check_task_graph(manifest, engine_root, shipped, problems)
    _check_role_definitions(manifest, shipped, problems)
    _check_content_integrity(manifest, engine_root, shipped, problems)
    _check_independence(manifest, shipped, problems)

    return _verdict(manifest, engine_rel, problems)


def _verdict(manifest, engine_rel, problems):
    engine_id = ""
    if isinstance(manifest, dict) and isinstance(manifest.get("engine_id"), str):
        engine_id = manifest["engine_id"]
    return {
        "status": "rejected" if len(problems) else "passed",
        "engine_id": engine_id,
        "engine_root": str(engine_rel),
        "checks_run": list(CHECKS),
        "problems": problems.sorted(),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Check that a delivered client engine package is complete and runnable."
    )
    parser.add_argument("--engine-root", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument(
        "--require-pass",
        action="store_true",
        help="exit 1 when the package is rejected, for use as a delivery gate",
    )
    args = parser.parse_args()

    def body():
        return check_delivery(engine_root=args.engine_root, project_root=args.project_root)

    if not args.require_pass:
        qc_lib.run_main(STAGE, body)
        return

    try:
        verdict = body()
    except qc_lib.Blocked as exc:
        print(json.dumps(exc.payload(), indent=2, sort_keys=True))
        raise SystemExit(2) from exc
    print(json.dumps(verdict, indent=2, sort_keys=True))
    raise SystemExit(0 if verdict["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
