"""Tests for the client-engine delivery checker.

The acceptance case this module exists for is `test_document_only_delivery_is_rejected`:
the twelve-Markdown-file tree the 2026-09-09 trial produced satisfies
references/schemas/author-proposal.schema.json (which requires only a `files` map with
two entries) while being unusable as an engine. check_delivery must reject it.
"""

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

import check_delivery
from qc_lib import Blocked


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class DeliveryCheckerTestCase(unittest.TestCase):
    """Builds a complete, passing engine package that each test then mutates."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self._tmp.name)
        self.engine_root = self.project_root / "e2e_test" / "orchestration"
        self.artifact_root = self.project_root / "e2e_test" / "modules"
        self.artifact_root.mkdir(parents=True)
        self._build_valid_package()

    def tearDown(self):
        self._tmp.cleanup()

    # -- package construction -------------------------------------------------

    def _build_valid_package(self):
        root = self.engine_root
        _write(root / "README.md", "# Engine\n\nHow to run this engine.\n")
        _write(root / "SKILL.md", "# Skill\n\nEntry instructions.\n")
        _write(root / "ARCHITECTURE.md", "# Architecture\n\nRoles and flow.\n")
        _write(
            root / "constants.json",
            json.dumps(
                {
                    "artifact_root": "e2e_test/modules",
                    "state_root": "e2e_test/orchestration/state",
                    "max_attempts": 3,
                    "operations": ["author_coverage", "remediate_existing"],
                }
            ),
        )
        _write(
            root / "client-spec.json",
            json.dumps(
                {"interview": {"owner": "client repository owner", "outcome": "Maintain coverage."}}
            ),
        )
        _write(
            root / "IMPLEMENTATION_PLAN.md",
            "# Implementation plan\n\n## Client interview\n\nRecorded.\n\n"
            "## Requirements\n\nRecorded.\n\n## Implementation steps\n\nRecorded.\n\n"
            "## Validation\n\nRecorded.\n",
        )
        _write(
            root / "scripts" / "run.py",
            "import json\n"
            "COMMANDS = ('start', 'resume', 'status')\n"
            "def main():\n"
            "    return json.dumps({'commands': COMMANDS})\n",
        )
        _write(root / "scripts" / "engine_lib.py", "def helper():\n    return 1\n")
        _write(root / "agents" / "coordinator.md", self._role_doc("Coordinator"))
        for worker in ("planner", "generator", "validator", "remediator"):
            _write(root / "agents" / f"{worker}.md", self._role_doc(worker.capitalize()))
        _write(root / "adapters" / "claude" / "README.md", "# Claude adapter\n\nHost wiring.\n")
        for name in (
            "request",
            "worker-result",
            "finding",
            "proposed-change",
            "approval",
            "run-state",
            "final-report",
        ):
            _write(
                root / "schemas" / f"{name}.schema.json",
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "$id": f"https://example.invalid/example-engine/{name}.schema.json",
                        "type": "object",
                    }
                ),
            )
        for name in ("test-plan", "flow", "report"):
            _write(root / "templates" / f"{name}.md", f"# {name}\n\nBody.\n")
        _write(root / "rules" / "rules-engine.md", "- Keep writes inside the artifact root.\n")
        _write(root / "workflows" / "workflows-engine.md", "1. Plan.\n2. Generate.\n")
        for op in ("author_coverage", "remediate_existing"):
            _write(root / "operations" / f"{op}.json", json.dumps(self._operation(op)))
        self._write_manifest()

    def _role_doc(self, title):
        return (
            f"# {title}\n\n"
            "## Responsibilities\n\nWhat this role does and does not do.\n\n"
            "## Model\n\nmodel_tier: medium\nreasoning_effort: medium\n\n"
            "## Tools\n\ntools: Read, Grep\n"
        )

    def _operation(self, operation_id):
        if operation_id == "author_coverage":
            tasks = [
                {"task_id": "plan", "worker": "planner", "depends_on": []},
                {"task_id": "generate", "worker": "generator", "depends_on": ["plan"]},
                {"task_id": "check", "worker": "validator", "depends_on": ["generate"]},
                {"task_id": "apply", "worker": "remediator", "depends_on": ["check"]},
            ]
        else:
            tasks = [
                {"task_id": "check", "worker": "validator", "depends_on": []},
                {"task_id": "apply", "worker": "remediator", "depends_on": ["check"]},
            ]
        return {"operation_id": operation_id, "tasks": tasks}

    def _worker_entry(self, worker_id, capability):
        return {
            "id": worker_id,
            "definition": f"agents/{worker_id}.md",
            "input_schema": "schemas/request.schema.json",
            "output_schema": "schemas/worker-result.schema.json",
            "capabilities": [capability],
        }

    def _manifest_body(self):
        return {
            "schema_version": 1,
            "engine_id": "example-engine",
            "source_revision": "7cfff86",
            "engine_root": "e2e_test/orchestration",
            "artifact_root": "e2e_test/modules",
            "state_root": "e2e_test/orchestration/state",
            "client_specification": "client-spec.json",
            "implementation_plan": "IMPLEMENTATION_PLAN.md",
            "entrypoint": "scripts/run.py",
            "constants": "constants.json",
            "operations": {
                "author_coverage": "operations/author_coverage.json",
                "remediate_existing": "operations/remediate_existing.json",
            },
            "coordinator": "agents/coordinator.md",
            "workers": [
                self._worker_entry("planner", "plan"),
                self._worker_entry("generator", "generate"),
                self._worker_entry("validator", "verify"),
                self._worker_entry("remediator", "apply"),
            ],
            "schemas": {
                "request": "schemas/request.schema.json",
                "worker_result": "schemas/worker-result.schema.json",
                "finding": "schemas/finding.schema.json",
                "proposed_change": "schemas/proposed-change.schema.json",
                "approval": "schemas/approval.schema.json",
                "run_state": "schemas/run-state.schema.json",
                "final_report": "schemas/final-report.schema.json",
            },
            "templates": {
                "test_plan": "templates/test-plan.md",
                "flow": "templates/flow.md",
                "report": "templates/report.md",
            },
            "adapters": {"claude": "adapters/claude/README.md"},
            "dependencies": ["python>=3.12", "claude-code"],
            "files": {},
        }

    def _write_manifest(self, mutate=None):
        manifest = self._manifest_body()
        if mutate is not None:
            mutate(manifest)
        manifest["files"] = self._compute_files()
        (self.engine_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        return manifest

    def _compute_files(self):
        files = {}
        for path in sorted(self.engine_root.rglob("*")):
            if not path.is_file() or path.name == "manifest.json":
                continue
            rel = path.relative_to(self.engine_root).as_posix()
            files[rel] = _sha256(path)
        return files

    def _rewrite_manifest(self, mutate):
        """Mutate the manifest without recomputing checksums from disk."""
        manifest_path = self.engine_root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        mutate(manifest)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return manifest

    def _check(self):
        return check_delivery.check_delivery(
            engine_root=self.engine_root, project_root=self.project_root
        )

    def _codes(self, verdict):
        return sorted({problem["code"] for problem in verdict["problems"]})


class ValidPackageTest(DeliveryCheckerTestCase):
    def test_complete_package_passes(self):
        verdict = self._check()
        self.assertEqual(verdict["status"], "passed", verdict["problems"])
        self.assertEqual(verdict["problems"], [])
        self.assertEqual(verdict["engine_id"], "example-engine")

    def test_passing_verdict_names_every_check_it_ran(self):
        verdict = self._check()
        self.assertIn("manifest_schema", verdict["checks_run"])
        self.assertIn("file_set_and_checksums", verdict["checks_run"])
        self.assertIn("task_graph", verdict["checks_run"])
        self.assertIn("path_containment", verdict["checks_run"])


class DocumentOnlyDeliveryTest(unittest.TestCase):
    """The acceptance case. A tree of Markdown files is not an engine."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self._tmp.name)
        self.engine_root = self.project_root / "authored-orchestration"
        names = [
            "ARCHITECTURE.md",
            "orchestrator.md",
            "rules/rules-engine.md",
            "rules/rules-engine-planner.md",
            "rules/rules-engine-generator.md",
            "rules/rules-engine-validator.md",
            "rules/rules-engine-remediator.md",
            "workflows/workflows-engine.md",
            "workflows/workflows-engine-planner.md",
            "workflows/workflows-engine-generator.md",
            "workflows/workflows-engine-validator.md",
            "workflows/workflows-engine-remediator.md",
        ]
        for name in names:
            _write(self.engine_root / name, f"# {name}\n\nProse only.\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_document_only_delivery_satisfies_the_old_proposal_schema(self):
        """Guard: proves the two schemas genuinely disagree, so the new one earns its place."""
        proposal = {
            "files": {
                path.relative_to(self.engine_root).as_posix(): path.read_text(encoding="utf-8")
                for path in sorted(self.engine_root.rglob("*"))
                if path.is_file()
            }
        }
        self.assertGreaterEqual(len(proposal["files"]), 2)
        self.assertTrue(all(isinstance(body, str) and body for body in proposal["files"].values()))

    def test_document_only_delivery_is_rejected(self):
        verdict = check_delivery.check_delivery(
            engine_root=self.engine_root, project_root=self.project_root
        )
        self.assertEqual(verdict["status"], "rejected")
        codes = sorted({problem["code"] for problem in verdict["problems"]})
        self.assertIn("manifest_missing", codes)


class ManifestStructureTest(DeliveryCheckerTestCase):
    def test_missing_required_manifest_field_is_rejected(self):
        self._rewrite_manifest(lambda manifest: manifest.pop("entrypoint"))
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("manifest_schema_violation", self._codes(verdict))

    def test_unknown_manifest_field_is_rejected(self):
        self._rewrite_manifest(lambda manifest: manifest.update({"extra": "no"}))
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("manifest_schema_violation", self._codes(verdict))

    def test_wrong_schema_version_is_rejected(self):
        self._rewrite_manifest(lambda manifest: manifest.update({"schema_version": 2}))
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("manifest_schema_violation", self._codes(verdict))

    def test_constants_must_be_the_named_file(self):
        self._rewrite_manifest(lambda manifest: manifest.update({"constants": "settings.json"}))
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("manifest_schema_violation", self._codes(verdict))

    def test_missing_implementation_plan_is_rejected(self):
        self._rewrite_manifest(lambda manifest: manifest.pop("implementation_plan"))
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("manifest_schema_violation", self._codes(verdict))

    def test_incomplete_implementation_plan_is_rejected(self):
        _write(self.engine_root / "IMPLEMENTATION_PLAN.md", "# Implementation plan\n")
        self._write_manifest()
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("implementation_plan_incomplete", self._codes(verdict))

    def test_empty_worker_list_is_rejected(self):
        self._rewrite_manifest(lambda manifest: manifest.update({"workers": []}))
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("manifest_schema_violation", self._codes(verdict))

    def test_malformed_checksum_value_is_rejected(self):
        self._rewrite_manifest(
            lambda manifest: manifest["files"].update({"README.md": "not-a-checksum"})
        )
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("manifest_schema_violation", self._codes(verdict))

    def test_unreadable_manifest_json_blocks_rather_than_rejecting(self):
        (self.engine_root / "manifest.json").write_text("{ not json", encoding="utf-8")
        with self.assertRaises(Blocked) as caught:
            self._check()
        self.assertEqual(caught.exception.reason_code, "malformed_checkpoint")


class PathContainmentTest(DeliveryCheckerTestCase):
    def test_absolute_root_path_is_rejected(self):
        self._rewrite_manifest(lambda manifest: manifest.update({"artifact_root": "/etc"}))
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("unsafe_path", self._codes(verdict))

    def test_parent_escape_in_root_path_is_rejected(self):
        self._rewrite_manifest(lambda manifest: manifest.update({"artifact_root": "../outside"}))
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("unsafe_path", self._codes(verdict))

    def test_parent_escape_in_engine_relative_path_is_rejected(self):
        self._rewrite_manifest(lambda manifest: manifest.update({"entrypoint": "../run.py"}))
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("unsafe_path", self._codes(verdict))

    def test_artifact_root_inside_engine_root_is_rejected(self):
        self._rewrite_manifest(
            lambda manifest: manifest.update({"artifact_root": "e2e_test/orchestration/modules"})
        )
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("nested_roots", self._codes(verdict))

    def test_engine_root_inside_artifact_root_is_rejected(self):
        self._rewrite_manifest(
            lambda manifest: manifest.update({"artifact_root": "e2e_test"})
        )
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("nested_roots", self._codes(verdict))

    def test_engine_root_equal_to_artifact_root_is_rejected(self):
        self._rewrite_manifest(
            lambda manifest: manifest.update({"artifact_root": "e2e_test/orchestration"})
        )
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("nested_roots", self._codes(verdict))

    def test_declared_engine_root_must_match_the_checked_directory(self):
        self._rewrite_manifest(lambda manifest: manifest.update({"engine_root": "somewhere/else"}))
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("engine_root_mismatch", self._codes(verdict))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unsupported on this platform")
    def test_symlink_escape_is_rejected(self):
        outside = self.project_root.parent / "outside-target.md"
        outside.write_text("# outside\n", encoding="utf-8")
        try:
            link = self.engine_root / "templates" / "escape.md"
            link.symlink_to(outside)
            self._write_manifest()
            verdict = self._check()
            self.assertEqual(verdict["status"], "rejected")
            self.assertIn("unsafe_path", self._codes(verdict))
        finally:
            outside.unlink(missing_ok=True)


class FileSetTest(DeliveryCheckerTestCase):
    def test_referenced_file_that_does_not_exist_is_rejected(self):
        (self.engine_root / "templates" / "flow.md").unlink()
        self._rewrite_manifest(lambda manifest: manifest["files"].pop("templates/flow.md"))
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("missing_file", self._codes(verdict))

    def test_changed_file_contents_are_rejected(self):
        (self.engine_root / "README.md").write_text("# Tampered\n", encoding="utf-8")
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("checksum_mismatch", self._codes(verdict))

    def test_shipped_file_absent_from_the_file_map_is_rejected(self):
        _write(self.engine_root / "scripts" / "stowaway.py", "print('hi')\n")
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("undeclared_file", self._codes(verdict))

    def test_file_map_entry_with_no_file_on_disk_is_rejected(self):
        self._rewrite_manifest(
            lambda manifest: manifest["files"].update({"ghost.md": "0" * 64})
        )
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("missing_file", self._codes(verdict))

    def test_manifest_may_not_checksum_itself(self):
        self._rewrite_manifest(
            lambda manifest: manifest["files"].update({"manifest.json": "0" * 64})
        )
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("manifest_self_reference", self._codes(verdict))


class WorkerAndGraphTest(DeliveryCheckerTestCase):
    def test_duplicate_worker_identity_is_rejected(self):
        def mutate(manifest):
            manifest["workers"].append(self._worker_entry("planner", "plan"))

        self._rewrite_manifest(mutate)
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("duplicate_worker_id", self._codes(verdict))

    def test_task_referencing_an_undeclared_worker_is_rejected(self):
        operation = self._operation("author_coverage")
        operation["tasks"][0]["worker"] = "nobody"
        _write(
            self.engine_root / "operations" / "author_coverage.json", json.dumps(operation)
        )
        self._write_manifest()
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("undeclared_worker", self._codes(verdict))

    def test_task_depending_on_a_missing_task_is_rejected(self):
        operation = self._operation("author_coverage")
        operation["tasks"][1]["depends_on"] = ["nonexistent"]
        _write(
            self.engine_root / "operations" / "author_coverage.json", json.dumps(operation)
        )
        self._write_manifest()
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("missing_dependency", self._codes(verdict))

    def test_dependency_cycle_is_rejected(self):
        operation = self._operation("author_coverage")
        operation["tasks"][0]["depends_on"] = ["apply"]
        _write(
            self.engine_root / "operations" / "author_coverage.json", json.dumps(operation)
        )
        self._write_manifest()
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("dependency_cycle", self._codes(verdict))

    def test_declared_worker_never_used_by_any_operation_is_rejected(self):
        def mutate(manifest):
            manifest["workers"].append(self._worker_entry("idler", "idle"))

        self._rewrite_manifest(mutate)
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("unused_worker", self._codes(verdict))

    def test_worker_definition_without_model_and_tool_settings_is_rejected(self):
        _write(
            self.engine_root / "agents" / "planner.md",
            "# Planner\n\nDoes some planning.\n",
        )
        self._write_manifest()
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("role_definition_incomplete", self._codes(verdict))

    def test_coordinator_definition_without_model_and_tool_settings_is_rejected(self):
        _write(self.engine_root / "agents" / "coordinator.md", "# Coordinator\n\nRuns things.\n")
        self._write_manifest()
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("role_definition_incomplete", self._codes(verdict))


class ContentIntegrityTest(DeliveryCheckerTestCase):
    def test_unresolved_template_placeholder_is_rejected(self):
        _write(
            self.engine_root / "templates" / "flow.md",
            "# flow\n\nappId: {{ APP_ID }}\n",
        )
        self._write_manifest()
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("unresolved_placeholder", self._codes(verdict))

    def test_unresolved_placeholder_in_a_role_definition_is_rejected(self):
        _write(
            self.engine_root / "agents" / "planner.md",
            self._role_doc("Planner") + "\nOwner: <TODO>\n",
        )
        self._write_manifest()
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("unresolved_placeholder", self._codes(verdict))

    def test_schema_reference_that_cannot_be_resolved_locally_is_rejected(self):
        _write(
            self.engine_root / "schemas" / "request.schema.json",
            json.dumps(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {"body": {"$ref": "missing-thing.schema.json"}},
                }
            ),
        )
        self._write_manifest()
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("unresolved_schema_ref", self._codes(verdict))

    def test_remote_schema_reference_is_rejected(self):
        _write(
            self.engine_root / "schemas" / "request.schema.json",
            json.dumps(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {"body": {"$ref": "https://example.com/x.schema.json"}},
                }
            ),
        )
        self._write_manifest()
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("unresolved_schema_ref", self._codes(verdict))

    def test_local_schema_reference_that_resolves_is_accepted(self):
        _write(
            self.engine_root / "schemas" / "request.schema.json",
            json.dumps(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {"body": {"$ref": "finding.schema.json"}},
                }
            ),
        )
        self._write_manifest()
        verdict = self._check()
        self.assertEqual(verdict["status"], "passed", verdict["problems"])


class IndependenceTest(DeliveryCheckerTestCase):
    def test_engine_code_importing_the_authoring_plugin_is_rejected(self):
        _write(
            self.engine_root / "scripts" / "run.py",
            "import sys\n"
            "sys.path.insert(0, '/plugins/orchestration-quality-control/scripts')\n"
            "import author_state\n"
            "COMMANDS = ('start', 'resume', 'status')\n",
        )
        self._write_manifest()
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("plugin_dependency", self._codes(verdict))

    def test_entrypoint_missing_a_required_command_is_rejected(self):
        _write(
            self.engine_root / "scripts" / "run.py",
            "COMMANDS = ('start', 'status')\n",
        )
        self._write_manifest()
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("entrypoint_incomplete", self._codes(verdict))

    def test_declared_dependencies_must_name_python_and_the_host(self):
        self._rewrite_manifest(lambda manifest: manifest.update({"dependencies": ["python>=3.12"]}))
        verdict = self._check()
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("dependency_incomplete", self._codes(verdict))


class BlockingConditionsTest(DeliveryCheckerTestCase):
    def test_missing_engine_root_blocks(self):
        with self.assertRaises(Blocked) as caught:
            check_delivery.check_delivery(
                engine_root=self.project_root / "nope", project_root=self.project_root
            )
        self.assertEqual(caught.exception.reason_code, "missing_target")

    def test_engine_root_outside_project_root_blocks(self):
        with self.assertRaises(Blocked) as caught:
            check_delivery.check_delivery(
                engine_root=self.project_root.parent, project_root=self.project_root
            )
        self.assertEqual(caught.exception.reason_code, "unsafe_path")


if __name__ == "__main__":
    unittest.main()
