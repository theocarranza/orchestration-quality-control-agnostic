"""Tests for client-specification compilation and engine emission.

The acceptance case the plan calls "the missing integration proof" is
`GeneratedEngineAcceptanceTest`: generate a package into a temporary workspace,
make the authoring plugin unavailable to it, and drive it through its own entry
point. Planning, checking, approval, application and resumption are all
demonstrated against temporary artifacts, with no model call and no mobile run.
"""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import check_delivery
import client_spec
import compile_delivery
import compile_workflow
from qc_lib import Blocked

SCRIPTS = Path(__file__).resolve().parents[1]
EXAMPLE_SPEC = SCRIPTS / "tests" / "fixtures" / "example-client-spec.json"

DECISIONS = {
    "run_id": "run-1",
    "created_at": "2026-09-09T18:00:00Z",
    "outcome": "Maintain end-to-end coverage through the existing test tree.",
}


def _spec():
    return json.loads(EXAMPLE_SPEC.read_text(encoding="utf-8"))


class SpecValidationTest(unittest.TestCase):
    def test_the_example_client_specification_is_valid(self):
        spec = client_spec.validate(_spec())
        self.assertEqual(spec["engine_id"], "example-e2e")
        self.assertEqual(client_spec.writing_roles(spec), ["applier"])

    def test_a_missing_owner_interview_is_refused(self):
        spec = _spec()
        spec.pop("interview")
        with self.assertRaises(Blocked) as caught:
            client_spec.validate(spec)
        self.assertEqual(caught.exception.reason_code, "malformed_checkpoint")

    def test_an_incomplete_owner_interview_is_refused(self):
        spec = _spec()
        spec["interview"]["requirements"] = []
        with self.assertRaises(Blocked) as caught:
            client_spec.validate(spec)
        self.assertIn("interview.requirements", caught.exception.detail)

    def test_a_coordinator_that_can_write_is_refused(self):
        spec = _spec()
        spec["coordinator"]["tools"] = ["read", "delegate", "edit"]
        spec["coordinator"]["denied_tools"] = []
        with self.assertRaises(Blocked) as caught:
            client_spec.validate(spec)
        self.assertEqual(caught.exception.reason_code, "capability_insufficient")

    def test_a_coordinator_that_cannot_delegate_is_refused(self):
        spec = _spec()
        spec["coordinator"]["tools"] = ["read"]
        with self.assertRaises(Blocked):
            client_spec.validate(spec)

    def test_granting_and_denying_the_same_token_is_refused(self):
        spec = _spec()
        spec["roles"]["planner"]["denied_tools"] = ["read"]
        with self.assertRaises(Blocked) as caught:
            client_spec.validate(spec)
        self.assertIn("both grants and denies", caught.exception.detail)

    def test_a_host_tool_name_instead_of_a_token_is_refused(self):
        spec = _spec()
        spec["roles"]["planner"]["tools"] = ["Read"]
        with self.assertRaises(Blocked) as caught:
            client_spec.validate(spec)
        self.assertEqual(caught.exception.reason_code, "capability_insufficient")

    def test_a_role_no_operation_uses_is_refused(self):
        spec = _spec()
        spec["roles"]["idler"] = copy.deepcopy(spec["roles"]["planner"])
        with self.assertRaises(Blocked) as caught:
            client_spec.validate(spec)
        self.assertIn("no operation uses", caught.exception.detail)

    def test_a_task_naming_an_undeclared_role_is_refused(self):
        spec = _spec()
        spec["operations"]["author_coverage"][0]["role"] = "ghost"
        with self.assertRaises(Blocked):
            client_spec.validate(spec)

    def test_a_dependency_cycle_is_refused(self):
        spec = _spec()
        spec["operations"]["author_coverage"][0]["depends_on"] = ["apply"]
        with self.assertRaises(Blocked) as caught:
            client_spec.validate(spec)
        self.assertIn("cycle", caught.exception.detail)


class PlaceholderRemovalTest(unittest.TestCase):
    """compile_workflow's four fixed constants are driven by the specification now."""

    def test_roles_get_their_own_tools_not_one_empty_list(self):
        compiled = compile_workflow.compile_for_operation(DECISIONS, _spec(), "author_coverage")
        tools = {role: spec.tools for role, spec in compile_workflow.freeze(dict(compiled.agent_specs)).items()}
        self.assertEqual(set(tools["planner"]), {"read", "grep", "glob"})
        self.assertEqual(set(tools["applier"]), {"read", "write", "edit"})
        self.assertNotEqual(tools["planner"], tools["applier"])

    def test_roles_get_their_own_model_tiers(self):
        compiled = compile_workflow.compile_for_operation(DECISIONS, _spec(), "author_coverage")
        specs = dict(compiled.agent_specs)
        self.assertEqual(specs["planner"].model_tier, "high")
        self.assertEqual(specs["applier"].model_tier, "medium")

    def test_the_task_graph_comes_from_the_specification(self):
        compiled = compile_workflow.compile_for_operation(DECISIONS, _spec(), "author_coverage")
        self.assertEqual(
            [node.task_id for node in compiled.task_dag.tasks],
            ["plan", "generate", "check", "apply"],
        )

    def test_a_second_operation_compiles_to_a_different_graph(self):
        compiled = compile_workflow.compile_for_operation(DECISIONS, _spec(), "remediate_existing")
        self.assertEqual([node.task_id for node in compiled.task_dag.tasks], ["check", "apply"])

    def test_an_undeclared_operation_is_refused(self):
        with self.assertRaises(Blocked):
            compile_workflow.compile_for_operation(DECISIONS, _spec(), "invent_something")

    def test_every_operation_compiles(self):
        compiled = compile_workflow.compile_all_operations(DECISIONS, _spec())
        self.assertEqual(sorted(compiled), ["author_coverage", "remediate_existing"])


class SpecDrivesTheEngineTest(unittest.TestCase):
    """A relevant specification change must change the compiled engine."""

    def _build(self, spec):
        return compile_delivery.build_files(
            spec, source_revision="rev", engine_root_rel="e2e_test/orchestration"
        )

    def test_renaming_a_role_changes_the_emitted_package(self):
        baseline = self._build(_spec())
        spec = _spec()
        spec["roles"]["surveyor"] = spec["roles"].pop("planner")
        for task in spec["operations"]["author_coverage"]:
            if task["role"] == "planner":
                task["role"] = "surveyor"
        changed = self._build(spec)
        self.assertIn("agents/planner.md", baseline)
        self.assertNotIn("agents/planner.md", changed)
        self.assertIn("agents/surveyor.md", changed)

    def test_changing_a_tool_grant_changes_the_role_document(self):
        baseline = self._build(_spec())
        spec = _spec()
        spec["roles"]["checker"]["tools"] = ["read"]
        changed = self._build(spec)
        self.assertNotEqual(baseline["agents/checker.md"], changed["agents/checker.md"])
        self.assertIn("tools: read", changed["agents/checker.md"])

    def test_changing_the_artifact_root_changes_the_rules(self):
        spec = _spec()
        spec["artifact_root"] = "integration_test/modules"
        changed = self._build(spec)
        self.assertIn("integration_test/modules", changed["rules/rules-engine.md"])
        self.assertIn("integration_test/modules", json.loads(changed["constants.json"])["artifact_root"])

    def test_adding_an_operation_adds_its_task_graph_file(self):
        spec = _spec()
        spec["operations"]["retire_scenario"] = [
            {"task_id": "check", "role": "checker", "depends_on": []},
            {"task_id": "apply", "role": "applier", "depends_on": ["check"]},
        ]
        changed = self._build(spec)
        self.assertIn("operations/retire_scenario.json", changed)
        manifest = json.loads(changed["manifest.json"])
        self.assertIn("retire_scenario", manifest["operations"])

    def test_two_different_specifications_do_not_produce_the_same_engine(self):
        spec = _spec()
        spec["engine_id"] = "widget-e2e"
        spec["artifact_root"] = "widget_test/cases"
        self.assertNotEqual(
            self._build(_spec())["manifest.json"], self._build(spec)["manifest.json"]
        )

    def test_compilation_is_deterministic(self):
        self.assertEqual(self._build(_spec()), self._build(_spec()))


class EmittedPackageTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self._tmp.name)
        (self.project_root / "e2e_test" / "modules").mkdir(parents=True)
        self.engine_root = self.project_root / "e2e_test" / "orchestration"
        self.result = compile_delivery.emit(
            _spec(),
            engine_root=self.engine_root,
            project_root=self.project_root,
            source_revision="7cfff86",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_emission_passes_the_delivery_contract(self):
        self.assertEqual(self.result["status"], "emitted")
        self.assertEqual(self.result["delivery_check"], "passed")

    def test_the_emitted_package_still_passes_when_checked_again(self):
        verdict = check_delivery.check_delivery(
            engine_root=self.engine_root, project_root=self.project_root
        )
        self.assertEqual(verdict["status"], "passed", verdict["problems"])

    def test_runtime_state_inside_engine_does_not_change_the_delivery_manifest(self):
        state_root = self.engine_root / "state"
        state_root.mkdir()
        (state_root / "run-after-delivery.json").write_text("{}\n", encoding="utf-8")
        verdict = check_delivery.check_delivery(
            engine_root=self.engine_root, project_root=self.project_root
        )
        self.assertEqual(verdict["status"], "passed", verdict["problems"])

    def test_the_package_has_every_required_part(self):
        for expected in (
            "README.md",
            "SKILL.md",
            "ARCHITECTURE.md",
            "IMPLEMENTATION_PLAN.md",
            "client-spec.json",
            "manifest.json",
            "constants.json",
            "scripts/run.py",
            "scripts/engine_lib.py",
            "agents/coordinator.md",
            "agents/planner.md",
            "adapters/claude/README.md",
            "operations/author_coverage.json",
            "schemas/worker-result.schema.json",
            "templates/flow.md",
            "rules/rules-engine.md",
            "workflows/workflows-engine.md",
        ):
            self.assertTrue((self.engine_root / expected).is_file(), expected)

    def test_the_interview_produces_a_client_owned_implementation_plan(self):
        plan = (self.engine_root / "IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")
        self.assertIn("## Client interview", plan)
        self.assertIn(_spec()["interview"]["outcome"], plan)
        self.assertIn("## Implementation steps", plan)

    def test_the_engine_root_may_be_seeded_only_with_the_interview_specification(self):
        self._tmp.cleanup()
        self._tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self._tmp.name)
        (self.project_root / "e2e_test" / "modules").mkdir(parents=True)
        self.engine_root = self.project_root / "e2e_test" / "orchestration"
        self.engine_root.mkdir(parents=True)
        seed = self.engine_root / "client-spec.json"
        seed.write_text(json.dumps(_spec()), encoding="utf-8")
        result = compile_delivery.emit(
            client_spec.load(seed),
            engine_root=self.engine_root,
            project_root=self.project_root,
            source_revision="7cfff86",
            specification_path=seed,
        )
        self.assertEqual(result["delivery_check"], "passed")

    def test_the_engine_imports_nothing_from_the_authoring_plugin(self):
        for path in self.engine_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for module in check_delivery.PLUGIN_MODULE_NAMES:
                self.assertNotIn(f"import {module}", text, f"{path.name} imports {module}")

    def test_emitting_into_a_non_empty_folder_is_refused(self):
        with self.assertRaises(Blocked) as caught:
            compile_delivery.emit(
                _spec(),
                engine_root=self.engine_root,
                project_root=self.project_root,
                source_revision="x",
            )
        self.assertEqual(caught.exception.reason_code, "destination_exists")

    def test_emitting_outside_the_project_is_refused(self):
        with self.assertRaises(Blocked) as caught:
            compile_delivery.emit(
                _spec(),
                engine_root=self.project_root.parent / "elsewhere-engine",
                project_root=self.project_root,
                source_revision="x",
            )
        self.assertEqual(caught.exception.reason_code, "unsafe_path")


class GeneratedEngineAcceptanceTest(unittest.TestCase):
    """The missing integration proof.

    The package is generated into a temporary workspace, the authoring plugin is
    made unreachable from it, and the engine is driven through its own entry
    point and its own spine. No model call, no mobile run.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self._tmp.name)
        self.artifacts = self.project_root / "e2e_test" / "modules"
        self.artifacts.mkdir(parents=True)
        self.engine_root = self.project_root / "e2e_test" / "orchestration"
        compile_delivery.emit(
            _spec(),
            engine_root=self.engine_root,
            project_root=self.project_root,
            source_revision="7cfff86",
        )
        self.state_root = self.engine_root / "state"
        self.changes = [
            {
                "path": "login/scenarios/happy/happy.flow.yaml",
                "action": "create",
                "after": "appId: ${APP_ID}\n---\n- launchApp\n",
            }
        ]

    def tearDown(self):
        self._tmp.cleanup()

    def _run_entrypoint(self, *args):
        """Invoke the entry point with an environment that cannot reach this plugin."""
        return subprocess.run(
            [sys.executable, str(self.engine_root / "scripts" / "run.py"),
             "--project-root", str(self.project_root), *args],
            capture_output=True,
            text=True,
            cwd=str(self.project_root),
            env={"PATH": "/usr/bin:/bin", "HOME": str(self.project_root)},
        )

    def _engine_lib(self):
        """Import the emitted spine from the temporary workspace only."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "emitted_engine_lib", self.engine_root / "scripts" / "engine_lib.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    # -- entry point ---------------------------------------------------------

    def test_start_opens_a_run_with_the_plugin_unavailable(self):
        result = self._run_entrypoint("start", "--operation", "author_coverage", "--run-id", "r1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["phase"], "planning")

    def test_status_reports_what_the_run_is_waiting_for(self):
        self._run_entrypoint("start", "--operation", "author_coverage", "--run-id", "r1")
        result = self._run_entrypoint("status", "--run-id", "r1")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["operation"], "author_coverage")
        self.assertIn("awaiting", payload)

    def test_an_unknown_operation_is_refused_with_a_recovery_action(self):
        result = self._run_entrypoint("start", "--operation", "nope", "--run-id", "r2")
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(payload["recovery_action"])

    def test_starting_the_same_run_twice_is_refused(self):
        self._run_entrypoint("start", "--operation", "author_coverage", "--run-id", "r1")
        result = self._run_entrypoint("start", "--operation", "author_coverage", "--run-id", "r1")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["reason_code"], "destination_exists")

    # -- the spine -----------------------------------------------------------

    def _prepared(self, engine, run_id, *, findings=()):
        engine.start_run(
            self.state_root,
            run_id=run_id,
            operation="author_coverage",
            operations=["author_coverage", "remediate_existing"],
        )
        engine.record_result(
            self.state_root,
            run_id,
            {
                "task_id": "check",
                "role": "checker",
                "outcome": "failed" if findings else "passed",
                "findings": list(findings),
            },
        )
        engine.propose(self.state_root, run_id, self.changes)
        return engine

    def test_a_checked_and_approved_change_set_is_written(self):
        engine = self._engine_lib()
        self._prepared(engine, "clean")
        engine.approve(self.state_root, "clean", "approve")
        outcome = engine.apply_changes(self.state_root, "clean", self.artifacts)
        self.assertEqual(outcome["phase"], "completed")
        self.assertEqual(outcome["skipped"], [])
        written = self.artifacts / "login" / "scenarios" / "happy" / "happy.flow.yaml"
        self.assertTrue(written.is_file())
        self.assertIn("launchApp", written.read_text(encoding="utf-8"))

    def test_applying_without_approval_is_refused(self):
        engine = self._engine_lib()
        self._prepared(engine, "unapproved")
        with self.assertRaises(engine.EngineError) as caught:
            engine.apply_changes(self.state_root, "unapproved", self.artifacts)
        self.assertEqual(caught.exception.reason_code, "not_approved")

    def test_approval_cannot_stand_in_for_a_check(self):
        engine = self._engine_lib()
        engine.start_run(
            self.state_root,
            run_id="unchecked",
            operation="author_coverage",
            operations=["author_coverage", "remediate_existing"],
        )
        engine.propose(self.state_root, "unchecked", self.changes)
        engine.approve(self.state_root, "unchecked", "approve")
        with self.assertRaises(engine.EngineError) as caught:
            engine.apply_changes(self.state_root, "unchecked", self.artifacts)
        self.assertEqual(caught.exception.reason_code, "not_checked")

    def test_a_failing_check_cannot_be_applied(self):
        engine = self._engine_lib()
        self._prepared(
            engine,
            "dirty",
            findings=[{"id": "f1", "severity": "high", "summary": "selector uses visible text"}],
        )
        engine.approve(self.state_root, "dirty", "approve")
        with self.assertRaises(engine.EngineError) as caught:
            engine.apply_changes(self.state_root, "dirty", self.artifacts)
        self.assertEqual(caught.exception.reason_code, "not_clean")

    def test_a_change_set_moved_after_approval_is_refused(self):
        engine = self._engine_lib()
        self._prepared(engine, "moved")
        engine.approve(self.state_root, "moved", "approve")
        record = engine.load_run(self.state_root, "moved")
        record["proposed_changes"][0]["after"] = "appId: ${APP_ID}\n---\n- clearState\n"
        engine.save_run(self.state_root, record)
        with self.assertRaises(engine.EngineError) as caught:
            engine.apply_changes(self.state_root, "moved", self.artifacts)
        self.assertEqual(caught.exception.reason_code, "stale_approval")

    def test_a_write_outside_the_artifact_folder_is_skipped_with_a_reason(self):
        engine = self._engine_lib()
        engine.start_run(
            self.state_root,
            run_id="escape",
            operation="author_coverage",
            operations=["author_coverage", "remediate_existing"],
        )
        engine.record_result(
            self.state_root,
            "escape",
            {"task_id": "check", "role": "checker", "outcome": "passed", "findings": []},
        )
        engine.propose(
            self.state_root,
            "escape",
            [{"path": "../../lib/main.dart", "action": "update", "after": "void main() {}\n"}],
        )
        engine.approve(self.state_root, "escape", "approve")
        outcome = engine.apply_changes(self.state_root, "escape", self.artifacts)
        self.assertEqual(outcome["applied"], [])
        self.assertEqual(len(outcome["skipped"]), 1)
        self.assertFalse((self.project_root / "lib" / "main.dart").exists())

    def test_every_item_ends_applied_or_skipped_with_a_reason(self):
        engine = self._engine_lib()
        engine.start_run(
            self.state_root,
            run_id="mixed",
            operation="author_coverage",
            operations=["author_coverage", "remediate_existing"],
        )
        engine.record_result(
            self.state_root,
            "mixed",
            {"task_id": "check", "role": "checker", "outcome": "passed", "findings": []},
        )
        proposed = self.changes + [
            {"path": "../outside.yaml", "action": "create", "after": "x\n"}
        ]
        engine.propose(self.state_root, "mixed", proposed)
        engine.approve(self.state_root, "mixed", "approve")
        outcome = engine.apply_changes(self.state_root, "mixed", self.artifacts)
        self.assertEqual(len(outcome["applied"]) + len(outcome["skipped"]), len(proposed))
        for skipped in outcome["skipped"]:
            self.assertTrue(skipped["reason"])

    def test_an_interrupted_run_resumes_from_its_saved_record(self):
        """Each accepted result is persisted immediately, so nothing is replayed."""
        engine = self._engine_lib()
        self._prepared(engine, "interrupted")
        reloaded = self._engine_lib()  # a fresh process would import it again
        record = reloaded.load_run(self.state_root, "interrupted")
        self.assertEqual(record["phase"], "awaiting_approval")
        self.assertEqual(len(record["results"]), 1)
        reloaded.approve(self.state_root, "interrupted", "approve")
        outcome = reloaded.apply_changes(self.state_root, "interrupted", self.artifacts)
        self.assertEqual(outcome["phase"], "completed")

    def test_a_declined_run_stops_and_writes_nothing(self):
        engine = self._engine_lib()
        self._prepared(engine, "declined")
        engine.approve(self.state_root, "declined", "decline")
        with self.assertRaises(engine.EngineError):
            engine.apply_changes(self.state_root, "declined", self.artifacts)
        self.assertFalse(any(self.artifacts.rglob("*.yaml")))


if __name__ == "__main__":
    unittest.main()
