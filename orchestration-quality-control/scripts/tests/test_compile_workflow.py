"""Tests for compile_workflow.py: the deterministic validation and
compilation boundary from accepted discovery/interview `decisions` to a
`RunSpec`, a generated `TaskDag`, and generated `AgentSpec` records.

`_decisions(...)` below builds fixtures by literally calling
`gate_defaults.author_fields` (the same packaged-defaults function
plan_interview/gate_defaults already own) rather than hand-rolling an
equivalent shape -- this is the "reuse plan_interview.py and
gate_defaults.py rather than reimplementing them" requirement, made
concrete in the fixtures rather than only asserted in prose.
"""

import dataclasses
import unittest

import gate_defaults
import plan_interview
from compile_workflow import CompiledWorkflow, compile_workflow
from fake_adapter import FakeAdapter
from mailbox import Mailbox
from oqc import drive, replay, verify
from qc_lib import Blocked
from run_state import attempts_of, status_of

RUN_ID = "run-compile-workflow"
CREATED_AT = "2026-09-06T12:00:00Z"


def _brief(**overrides):
    base = {
        "languages": [],
        "package_managers": [],
        "layout": [],
        "test_trees": [],
        "ci": [],
        "existing_orchestration": [],
        "existing_mechanism": [],
        "doc_language_hints": ["en"],
        "profile_hints": [],
        "readme_present": False,
    }
    base.update(overrides)
    return base


def _decisions(*, outcome="ship the widget", run_id=RUN_ID, created_at=CREATED_AT,
               overrides=None, brief=None):
    """Build a `decisions` mapping the way root/interviewer actually would.

    `gate_defaults.author_fields` packages every field except `outcome`;
    `plan_interview.plan`'s `always_ask` names `outcome` as the one field a
    human is always asked. `run_id`/`created_at` are the run's own
    identity, assigned once by whatever session starts the run -- not an
    interview decision -- so they are threaded in here exactly as a real
    caller would, never derived from a clock inside compile_workflow.py
    itself.
    """
    fields = gate_defaults.author_fields(brief or _brief(), overrides or {})
    return {**fields, "outcome": outcome, "run_id": run_id, "created_at": created_at}


class _MappingLikeWithoutDunderContains:
    """A read-only mapping-like object with `get` and `__getitem__` but no
    `__contains__`/`__iter__` -- the exact shape that used to slip past
    `compile_workflow`'s old duck-typed check
    (`hasattr(decisions, "get")`/`hasattr(decisions, "__getitem__")`).
    `qc_lib.require_fields`'s own `field not in obj` then fell back to the
    legacy sequence protocol (probing `obj[0]`, `obj[1]`, ...), and this
    object's string-keyed `__getitem__` raises `KeyError` there instead of
    the `IndexError` that fallback expects -- a bare `KeyError` escaping
    `compile_workflow` instead of the `Blocked` its docstring promises.
    """

    def __init__(self, data):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]


def _latest_payload(mailbox, *, kind, task_id, attempt=None):
    matches = [
        envelope.payload
        for envelope in mailbox.read_all()
        if envelope.kind == kind
        and envelope.payload.get("task_id") == task_id
        and (attempt is None or envelope.payload.get("attempt") == attempt)
    ]
    if not matches:
        raise AssertionError(f"no {kind!r} envelope for task_id={task_id!r} attempt={attempt!r}")
    return matches[-1]


# ---------------------------------------------------------------------------
# Fixtures are built from the real interview utilities, not a reinvented
# shape.
# ---------------------------------------------------------------------------


class ReusesInterviewUtilitiesTest(unittest.TestCase):
    def test_packaged_defaults_alone_compile_a_single_agent_workflow(self):
        decisions = _decisions()
        self.assertEqual(decisions["shape"], "single-agent")
        compiled = compile_workflow(decisions)
        self.assertEqual([node.task_id for node in compiled.task_dag.tasks], ["task-author"])

    def test_decisions_carry_every_field_plan_interview_reports_as_skipped_plus_outcome(self):
        plan = plan_interview.plan(_brief())
        self.assertEqual(plan["always_ask"], ["outcome"])
        skipped_fields = {item["field"] for item in plan["skip"]}
        decisions = _decisions()
        self.assertTrue(skipped_fields.issubset(decisions.keys()))
        self.assertIn("outcome", decisions)


# ---------------------------------------------------------------------------
# Validation: malformed or contradictory decisions raise Blocked, by field,
# before any spec is built.
# ---------------------------------------------------------------------------


class ValidationTest(unittest.TestCase):
    def test_rejects_a_non_mapping(self):
        with self.assertRaises(Blocked):
            compile_workflow(["not", "a", "mapping"])

    def test_rejects_a_non_dict_mapping_like_object_instead_of_leaking_a_keyerror(self):
        # A mapping-like object with every required field individually
        # valid, but not a `dict` -- see _MappingLikeWithoutDunderContains's
        # own docstring for exactly which duck-typed check this used to
        # slip past, and what it leaked instead of Blocked.
        decisions = _MappingLikeWithoutDunderContains(dict(_decisions()))
        with self.assertRaises(Blocked):
            compile_workflow(decisions)

    def test_rejects_each_missing_required_field(self):
        base = _decisions()
        required = (
            "run_id", "created_at", "outcome", "shape",
            "named_inputs", "outcome_involves_test_tree", "profile",
        )
        for field in required:
            with self.subTest(field=field):
                decisions = dict(base)
                del decisions[field]
                with self.assertRaises(Blocked) as ctx:
                    compile_workflow(decisions)
                self.assertIn(field, ctx.exception.detail)

    def test_rejects_unknown_shape(self):
        decisions = _decisions(overrides={"shape": "multi-agent-swarm"})
        with self.assertRaises(Blocked):
            compile_workflow(decisions)

    def test_rejects_unknown_profile(self):
        decisions = dict(_decisions())
        decisions["profile"] = "unknown-profile"
        with self.assertRaises(Blocked):
            compile_workflow(decisions)

    def test_rejects_non_boolean_outcome_involves_test_tree(self):
        decisions = dict(_decisions())
        decisions["outcome_involves_test_tree"] = "yes"
        with self.assertRaises(Blocked):
            compile_workflow(decisions)

    def test_rejects_named_inputs_that_is_not_an_array(self):
        decisions = _decisions(overrides={"shape": "isolated-workers", "named_inputs": "docs"})
        with self.assertRaises(Blocked):
            compile_workflow(decisions)

    def test_rejects_a_non_string_named_input(self):
        decisions = _decisions(overrides={"shape": "isolated-workers", "named_inputs": ["docs", 123]})
        with self.assertRaises(Blocked):
            compile_workflow(decisions)

    def test_rejects_an_empty_string_named_input(self):
        decisions = _decisions(overrides={"shape": "isolated-workers", "named_inputs": ["docs", ""]})
        with self.assertRaises(Blocked):
            compile_workflow(decisions)

    def test_rejects_single_agent_with_named_inputs_as_contradictory(self):
        decisions = _decisions(overrides={"shape": "single-agent", "named_inputs": ["docs"]})
        with self.assertRaises(Blocked) as ctx:
            compile_workflow(decisions)
        self.assertIn("contradictory", ctx.exception.detail)

    def test_rejects_isolated_workers_with_no_named_inputs_as_contradictory(self):
        decisions = _decisions(overrides={"shape": "isolated-workers", "named_inputs": []})
        with self.assertRaises(Blocked) as ctx:
            compile_workflow(decisions)
        self.assertIn("contradictory", ctx.exception.detail)

    def test_rejects_malformed_run_id_via_reused_kernel_specs_validation(self):
        decisions = dict(_decisions())
        decisions["run_id"] = "Not An Identifier!"
        with self.assertRaises(Blocked):
            compile_workflow(decisions)

    def test_rejects_malformed_created_at_via_reused_kernel_specs_validation(self):
        decisions = dict(_decisions())
        decisions["created_at"] = "not-a-date"
        with self.assertRaises(Blocked):
            compile_workflow(decisions)

    def test_rejects_empty_outcome_via_reused_kernel_specs_validation(self):
        decisions = dict(_decisions())
        decisions["outcome"] = ""
        with self.assertRaises(Blocked):
            compile_workflow(decisions)

    def test_a_rejected_call_never_returns_a_partial_workflow(self):
        decisions = dict(_decisions())
        del decisions["shape"]
        sentinel = object()
        result = sentinel
        try:
            result = compile_workflow(decisions)
        except Blocked:
            pass
        self.assertIs(result, sentinel)


# ---------------------------------------------------------------------------
# Topology: single-agent and isolated-workers shapes.
# ---------------------------------------------------------------------------


class SingleAgentShapeTest(unittest.TestCase):
    def test_no_test_tree_emits_one_task_one_role(self):
        compiled = compile_workflow(_decisions())
        self.assertEqual(compiled.task_dag.to_list(), [
            {"task_id": "task-author", "role": "author", "depends_on": []},
        ])
        self.assertEqual(set(compiled.agent_specs.keys()), {"author"})
        self.assertEqual(compiled.agent_specs["author"].capabilities, ("author",))

    def test_test_tree_emits_a_dependent_verify_task(self):
        decisions = _decisions(overrides={"outcome_involves_test_tree": True})
        compiled = compile_workflow(decisions)
        self.assertEqual(compiled.task_dag.to_list(), [
            {"task_id": "task-author", "role": "author", "depends_on": []},
            {"task_id": "task-verify", "role": "verify", "depends_on": ["task-author"]},
        ])
        self.assertEqual(set(compiled.agent_specs.keys()), {"author", "verify"})


class IsolatedWorkersShapeTest(unittest.TestCase):
    def test_one_independent_task_per_named_input(self):
        decisions = _decisions(overrides={"shape": "isolated-workers", "named_inputs": ["docs", "api"]})
        compiled = compile_workflow(decisions)
        self.assertEqual(compiled.task_dag.to_list(), [
            {"task_id": "task-docs", "role": "author-docs", "depends_on": []},
            {"task_id": "task-api", "role": "author-api", "depends_on": []},
        ])
        self.assertEqual(set(compiled.agent_specs.keys()), {"author-docs", "author-api"})

    def test_test_tree_adds_a_converging_verify_task(self):
        decisions = _decisions(overrides={
            "shape": "isolated-workers",
            "named_inputs": ["docs", "api"],
            "outcome_involves_test_tree": True,
        })
        compiled = compile_workflow(decisions)
        verify_node = compiled.task_dag.tasks[-1]
        self.assertEqual(verify_node.task_id, "task-verify")
        self.assertEqual(verify_node.role, "verify")
        self.assertEqual(verify_node.depends_on, ("task-docs", "task-api"))
        self.assertEqual(set(compiled.agent_specs.keys()), {"author-docs", "author-api", "verify"})


# ---------------------------------------------------------------------------
# The contract fixture: this task's load-bearing evidence. A relevant
# decision change must change the emitted DAG or agent manifest; an
# irrelevant one must leave every emitted spec byte-identical.
# ---------------------------------------------------------------------------


class ContractFixtureTest(unittest.TestCase):
    def _workflow_decisions(self, **overrides):
        merged = {
            "shape": "isolated-workers",
            "named_inputs": ["docs", "api"],
            "outcome_involves_test_tree": False,
        }
        merged.update(overrides)
        return _decisions(overrides=merged)

    def test_relevant_change_adding_a_named_input_changes_the_dag_and_manifest(self):
        baseline = compile_workflow(self._workflow_decisions())
        changed = compile_workflow(self._workflow_decisions(named_inputs=["docs", "api", "cli"]))

        self.assertNotEqual(baseline.task_dag.to_json(), changed.task_dag.to_json())
        self.assertNotEqual(set(baseline.agent_specs.keys()), set(changed.agent_specs.keys()))
        self.assertIn("author-cli", changed.agent_specs)

    def test_relevant_change_toggling_test_tree_adds_a_dependent_task(self):
        baseline = compile_workflow(self._workflow_decisions())
        changed = compile_workflow(self._workflow_decisions(outcome_involves_test_tree=True))

        self.assertNotEqual(baseline.task_dag.to_json(), changed.task_dag.to_json())
        self.assertIn("verify", changed.agent_specs)
        self.assertNotIn("verify", baseline.agent_specs)

    def test_relevant_change_via_profile_changes_the_manifest_without_changing_the_dag(self):
        baseline = compile_workflow(self._workflow_decisions())
        changed = compile_workflow(self._workflow_decisions(profile="example-pipeline"))

        self.assertEqual(baseline.task_dag.to_json(), changed.task_dag.to_json())
        self.assertNotEqual(
            baseline.agent_specs["author-docs"].to_json(),
            changed.agent_specs["author-docs"].to_json(),
        )
        self.assertIn("pipeline", changed.agent_specs["author-docs"].capabilities)

    def test_irrelevant_change_leaves_every_emitted_spec_byte_identical(self):
        baseline = compile_workflow(self._workflow_decisions())
        changed = compile_workflow(self._workflow_decisions(
            language="pt-br",
            output_root="a-totally-different-folder",
            approval="not-required",
        ))

        self.assertEqual(baseline.run_spec.to_json(), changed.run_spec.to_json())
        self.assertEqual(baseline.task_dag.to_json(), changed.task_dag.to_json())
        self.assertEqual(set(baseline.agent_specs.keys()), set(changed.agent_specs.keys()))
        for role in baseline.agent_specs:
            self.assertEqual(
                baseline.agent_specs[role].to_json(),
                changed.agent_specs[role].to_json(),
            )


# ---------------------------------------------------------------------------
# Determinism: identical decisions in, byte-identical specs out.
# ---------------------------------------------------------------------------


class DeterminismTest(unittest.TestCase):
    def test_identical_decisions_produce_byte_identical_specs(self):
        decisions = _decisions(overrides={
            "shape": "isolated-workers",
            "named_inputs": ["docs", "api"],
            "outcome_involves_test_tree": True,
        })

        first = compile_workflow(dict(decisions))
        second = compile_workflow(dict(decisions))

        self.assertEqual(first.run_spec.to_json(), second.run_spec.to_json())
        self.assertEqual(first.task_dag.to_json(), second.task_dag.to_json())
        self.assertEqual(set(first.agent_specs.keys()), set(second.agent_specs.keys()))
        for role in first.agent_specs:
            self.assertEqual(first.agent_specs[role].to_json(), second.agent_specs[role].to_json())


class CompiledWorkflowImmutabilityTest(unittest.TestCase):
    def test_agent_specs_mapping_is_frozen(self):
        compiled = compile_workflow(_decisions())
        with self.assertRaises(TypeError):
            compiled.agent_specs["author"] = None

    def test_compiled_workflow_dataclass_is_frozen(self):
        compiled = compile_workflow(_decisions())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            compiled.run_spec = None


# ---------------------------------------------------------------------------
# The model-free run must consume the emitted spec, not a hand-written one.
# ---------------------------------------------------------------------------


class ModelFreeRunConsumesCompiledSpecTest(unittest.TestCase):
    def _compiled(self):
        decisions = _decisions(overrides={"outcome_involves_test_tree": True})
        return compile_workflow(decisions)

    def test_drive_reaches_completed_on_the_emitted_two_task_dependent_dag(self):
        compiled = self._compiled()
        script = {
            ("task-author", 1): {"outcome": "failed", "critique": "first draft needs revision"},
            ("task-author", 2): {"outcome": "passed"},
            ("task-verify", 1): {"outcome": "passed"},
        }
        mailbox = Mailbox()
        adapter = FakeAdapter(script)

        final_state = drive(
            compiled.task_dag,
            adapter,
            mailbox,
            compiled.agent_specs,
            3,
            run_id=compiled.run_spec.run_id,
        )

        self.assertEqual(final_state.phase, "completed")
        self.assertEqual(final_state.run_id, compiled.run_spec.run_id)
        self.assertEqual(status_of(final_state, "task-author"), "passed")
        self.assertEqual(status_of(final_state, "task-verify"), "passed")
        self.assertEqual(attempts_of(final_state, "task-author"), 2)

    def test_the_second_attempts_brief_carries_the_first_failures_critique(self):
        compiled = self._compiled()
        script = {
            ("task-author", 1): {"outcome": "failed", "critique": "first draft needs revision"},
            ("task-author", 2): {"outcome": "passed"},
            ("task-verify", 1): {"outcome": "passed"},
        }
        mailbox = Mailbox()
        adapter = FakeAdapter(script)

        drive(
            compiled.task_dag,
            adapter,
            mailbox,
            compiled.agent_specs,
            3,
            run_id=compiled.run_spec.run_id,
        )

        request_2 = _latest_payload(mailbox, kind="request", task_id="task-author", attempt=2)
        self.assertEqual(request_2["brief"]["critique"], "first draft needs revision")
        self.assertEqual(request_2["brief"]["role"], "author")
        self.assertEqual(request_2["brief"]["agent_id"], "agent-author")


# ---------------------------------------------------------------------------
# The judgement call this task asks for: compiled independent branches make
# drive()'s halt-on-any-terminal-decision behaviour a real, exercised case
# rather than a theoretical one. drive() is frozen; this proves the
# behaviour rather than avoiding emitting parallel branches to sidestep it.
# ---------------------------------------------------------------------------


class IndependentBranchLimitationTest(unittest.TestCase):
    def test_an_unrelated_independent_branch_never_runs_after_a_sibling_exhausts_its_budget(self):
        decisions = _decisions(overrides={
            "shape": "isolated-workers",
            "named_inputs": ["alpha", "beta"],
            "outcome_involves_test_tree": False,
        })
        compiled = compile_workflow(decisions)

        # Beta has a valid success response, but fail-fast policy must leave
        # it pending and never invoke it after alpha exhausts its budget.
        script = {
            ("task-alpha", 1): {"outcome": "failed", "critique": "attempt 1: wrong shape"},
            ("task-alpha", 2): {"outcome": "failed", "critique": "attempt 2: still wrong"},
            ("task-alpha", 3): {"outcome": "failed", "critique": "attempt 3: still wrong"},
            ("task-beta", 1): {"outcome": "passed"},
        }
        mailbox = Mailbox()
        adapter = FakeAdapter(script)

        final_state = drive(
            compiled.task_dag,
            adapter,
            mailbox,
            compiled.agent_specs,
            3,
            run_id=compiled.run_spec.run_id,
        )

        self.assertEqual(final_state.phase, "blocked")
        self.assertEqual(status_of(final_state, "task-alpha"), "failed")
        self.assertEqual(status_of(final_state, "task-beta"), "pending")
        for envelope in mailbox.read_all():
            self.assertNotEqual(envelope.payload.get("task_id"), "task-beta")

        # The terminal phase and state are derived from the emitted mailbox,
        # so replay and verification must agree with the live drive result.
        self.assertEqual(replay(mailbox), final_state)
        self.assertEqual(verify(mailbox).state, final_state)


if __name__ == "__main__":
    unittest.main()
