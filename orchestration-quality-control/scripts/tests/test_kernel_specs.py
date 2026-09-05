import json
import unittest
from dataclasses import FrozenInstanceError
from types import MappingProxyType

from tests import SCRIPTS_DIR

from qc_lib import Blocked
from kernel_specs import AgentSpec, Envelope, RunSpec, TaskNode, TaskDag


def _agent_dict(**overrides):
    data = {
        "schema_version": 1,
        "agent_id": "researcher-1",
        "role": "researcher",
        "capabilities": ["analyze", "summarize"],
        "tools": ["search"],
        "output_schema": "schemas/worker-result.schema.json",
        "model_tier": "medium",
        "reasoning_effort": "medium",
    }
    data.update(overrides)
    return data


def _run_dict(**overrides):
    data = {
        "schema_version": 1,
        "run_id": "run-0001",
        "goal": "Produce a reviewed report.",
        "created_at": "2026-09-04T12:00:00+00:00",
    }
    data.update(overrides)
    return data


def _envelope_dict(**overrides):
    data = {
        "schema_version": 1,
        "envelope_id": "env-0001",
        "run_id": "run-0001",
        "sender": "root",
        "recipient": "orchestrator",
        "kind": "request",
        "payload": {"note": "begin"},
        "created_at": "2026-09-04T12:00:00+00:00",
    }
    data.update(overrides)
    return data


class AgentSpecTest(unittest.TestCase):
    def test_well_formed_agent_spec_constructs(self):
        spec = AgentSpec.from_dict(_agent_dict())
        self.assertEqual(spec.agent_id, "researcher-1")
        self.assertEqual(spec.capabilities, ("analyze", "summarize"))
        self.assertEqual(spec.tools, ("search",))

    def test_each_required_field_absence_is_named(self):
        for field_name in (
            "schema_version", "agent_id", "role", "capabilities", "tools",
            "output_schema", "model_tier", "reasoning_effort",
        ):
            with self.subTest(field=field_name):
                data = _agent_dict()
                del data[field_name]
                with self.assertRaises(Blocked) as ctx:
                    AgentSpec.from_dict(data)
                self.assertIn(field_name, ctx.exception.detail)

    def test_invalid_model_tier_is_named(self):
        with self.assertRaises(Blocked) as ctx:
            AgentSpec.from_dict(_agent_dict(model_tier="ultra"))
        self.assertIn("model_tier", ctx.exception.detail)

    def test_no_vendor_vocabulary_in_tiers(self):
        # "low"/"medium"/"high" are the only vocabulary a well-formed
        # AgentSpec may use for model/reasoning strength; a host name or
        # model id must be rejected the same way any other bad enum value is.
        with self.assertRaises(Blocked):
            AgentSpec.from_dict(_agent_dict(model_tier="claude-opus-4"))
        for tier in ("low", "medium", "high"):
            spec = AgentSpec.from_dict(_agent_dict(model_tier=tier, reasoning_effort=tier))
            self.assertEqual(spec.model_tier, tier)

    def test_mutation_after_construction_raises(self):
        spec = AgentSpec.from_dict(_agent_dict())
        with self.assertRaises(FrozenInstanceError):
            spec.agent_id = "other"

    def test_capability_tuple_item_assignment_raises(self):
        spec = AgentSpec.from_dict(_agent_dict())
        with self.assertRaises(TypeError):
            spec.capabilities[0] = "x"

    def test_trailing_newline_in_identifier_is_rejected(self):
        # re.match's '$' matches before a trailing newline, so a naive
        # pattern check would let 'agent-1\n' through as if it were 'agent-1'.
        with self.assertRaises(Blocked) as ctx:
            AgentSpec.from_dict(_agent_dict(agent_id="researcher-1\n"))
        self.assertIn("agent_id", ctx.exception.detail)

    def test_trailing_newline_in_token_is_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            AgentSpec.from_dict(_agent_dict(capabilities=["analyze\n"]))
        self.assertIn("capabilities", ctx.exception.detail)

    def test_serialisation_round_trips_byte_stably(self):
        spec = AgentSpec.from_dict(_agent_dict())
        first = spec.to_json()
        restored = AgentSpec.from_json(first)
        second = restored.to_json()
        self.assertEqual(first, second)
        self.assertEqual(spec.to_dict(), restored.to_dict())

        # Key order in the source mapping must not affect the wire form.
        reordered = dict(reversed(list(_agent_dict().items())))
        reordered_json = AgentSpec.from_dict(reordered).to_json()
        self.assertEqual(first, reordered_json)


class RunSpecTest(unittest.TestCase):
    def test_well_formed_run_spec_constructs(self):
        spec = RunSpec.from_dict(_run_dict())
        self.assertEqual(spec.run_id, "run-0001")
        self.assertEqual(spec.goal, "Produce a reviewed report.")

    def test_each_required_field_absence_is_named(self):
        for field_name in ("schema_version", "run_id", "goal", "created_at"):
            with self.subTest(field=field_name):
                data = _run_dict()
                del data[field_name]
                with self.assertRaises(Blocked) as ctx:
                    RunSpec.from_dict(data)
                self.assertIn(field_name, ctx.exception.detail)

    def test_mutation_after_construction_raises(self):
        spec = RunSpec.from_dict(_run_dict())
        with self.assertRaises(FrozenInstanceError):
            spec.goal = "different"

    def test_trailing_newline_in_identifier_is_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            RunSpec.from_dict(_run_dict(run_id="run-0001\n"))
        self.assertIn("run_id", ctx.exception.detail)

    def test_zulu_suffixed_datetime_is_accepted(self):
        # RFC 3339's 'Z' offset must validate identically on every supported
        # interpreter, not only on the ones whose datetime.fromisoformat
        # happens to accept 'Z' natively.
        spec = RunSpec.from_dict(_run_dict(created_at="2026-09-04T12:00:00Z"))
        self.assertEqual(spec.created_at, "2026-09-04T12:00:00Z")

    def test_date_only_string_is_rejected(self):
        # A bare calendar date has no time component and must not be
        # accepted as a date-time, on any interpreter.
        with self.assertRaises(Blocked) as ctx:
            RunSpec.from_dict(_run_dict(created_at="2026-09-04"))
        self.assertIn("created_at", ctx.exception.detail)

    def test_serialisation_round_trips_byte_stably(self):
        spec = RunSpec.from_dict(_run_dict())
        first = spec.to_json()
        second = RunSpec.from_json(first).to_json()
        self.assertEqual(first, second)
        self.assertEqual(spec.to_dict(), RunSpec.from_json(first).to_dict())


class EnvelopeTest(unittest.TestCase):
    def setUp(self):
        schema_path = SCRIPTS_DIR.parent / "schemas" / "envelope.schema.json"
        self.schema = json.loads(schema_path.read_text())

    def test_well_formed_envelope_validates_against_schema(self):
        data = _envelope_dict()
        # The fixture must exercise every field the schema requires, and
        # nothing else, since additionalProperties is false.
        self.assertEqual(sorted(self.schema["required"]), sorted(data.keys()))
        envelope = Envelope.from_dict(data)
        self.assertEqual(envelope.kind, "request")
        self.assertEqual(envelope.sender, "root")

    def test_each_required_field_absence_is_named(self):
        for field_name in self.schema["required"]:
            with self.subTest(field=field_name):
                data = _envelope_dict()
                del data[field_name]
                with self.assertRaises(Blocked) as ctx:
                    Envelope.from_dict(data)
                self.assertIn(field_name, ctx.exception.detail)

    def test_unknown_kind_is_rejected_by_schema(self):
        with self.assertRaises(Blocked) as ctx:
            Envelope.from_dict(_envelope_dict(kind="not-a-kind"))
        self.assertIn("kind", ctx.exception.detail)

    def test_unexpected_field_is_rejected_by_schema(self):
        with self.assertRaises(Blocked) as ctx:
            Envelope.from_dict(_envelope_dict(host="claude"))
        self.assertIn("host", ctx.exception.detail)

    def test_no_vendor_vocabulary_in_kind_enum(self):
        self.assertEqual(
            sorted(self.schema["properties"]["kind"]["enum"]),
            sorted(["request", "result", "status", "question", "answer"]),
        )

    def test_mutation_after_construction_raises(self):
        envelope = Envelope.from_dict(_envelope_dict())
        with self.assertRaises(FrozenInstanceError):
            envelope.sender = "other"

    def test_payload_item_assignment_raises(self):
        envelope = Envelope.from_dict(_envelope_dict())
        with self.assertRaises(TypeError):
            envelope.payload["note"] = "changed"

    def test_nested_payload_mutation_raises(self):
        # _freeze must recurse: a shallow implementation would leave the
        # top-level payload frozen while nested dicts/lists stayed mutable,
        # and every other test in this file would still pass. Prove the
        # nested case explicitly, for a dict, a list item, and append.
        envelope = Envelope.from_dict(_envelope_dict(payload={
            "nested": {"inner": "value"},
            "items": ["a", "b"],
        }))
        with self.assertRaises(TypeError):
            envelope.payload["nested"]["inner"] = "changed"
        with self.assertRaises(TypeError):
            envelope.payload["items"][0] = "changed"
        with self.assertRaises(AttributeError):
            envelope.payload["items"].append("c")

    def test_direct_construction_with_frozen_top_level_freezes_nested_too(self):
        # Envelope is a public frozen dataclass; nothing forces construction
        # through from_dict. If a caller (or a future mailbox/router module)
        # hands the constructor an already-MappingProxyType payload whose
        # nested dicts/lists are still plain, _freeze must not short-circuit
        # on the already-frozen top level and skip recursing into them.
        payload = MappingProxyType({
            "nested": {"inner": "value"},
            "items": ["a", "b"],
        })
        envelope = Envelope(
            schema_version=1,
            envelope_id="env-0002",
            run_id="run-0001",
            sender="root",
            recipient="orchestrator",
            kind="request",
            payload=payload,
            created_at="2026-09-04T12:00:00+00:00",
        )
        with self.assertRaises(TypeError):
            envelope.payload["nested"]["inner"] = "MUTATED"
        with self.assertRaises(TypeError):
            envelope.payload["items"][0] = "MUTATED"
        with self.assertRaises(AttributeError):
            envelope.payload["items"].append("c")

    def test_trailing_newline_in_identifier_is_rejected_by_schema(self):
        with self.assertRaises(Blocked) as ctx:
            Envelope.from_dict(_envelope_dict(envelope_id="env-0001\n"))
        self.assertIn("envelope_id", ctx.exception.detail)

    def test_zulu_suffixed_datetime_is_accepted(self):
        envelope = Envelope.from_dict(_envelope_dict(created_at="2026-09-04T12:00:00Z"))
        self.assertEqual(envelope.created_at, "2026-09-04T12:00:00Z")

    def test_date_only_string_is_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            Envelope.from_dict(_envelope_dict(created_at="2026-09-04"))
        self.assertIn("created_at", ctx.exception.detail)

    def test_serialisation_round_trips_byte_stably(self):
        envelope = Envelope.from_dict(_envelope_dict())
        first = envelope.to_json()
        restored = Envelope.from_json(first)
        second = restored.to_json()
        self.assertEqual(first, second)
        self.assertEqual(envelope.to_dict(), restored.to_dict())


class TaskNodeTest(unittest.TestCase):
    def test_well_formed_task_node_constructs(self):
        node = TaskNode.from_dict({
            "task_id": "analyze-target",
            "role": "researcher",
            "depends_on": ["discover-files"],
        })
        self.assertEqual(node.task_id, "analyze-target")
        self.assertEqual(node.role, "researcher")
        self.assertEqual(node.depends_on, ("discover-files",))

    def test_task_node_with_empty_depends_on(self):
        node = TaskNode.from_dict({
            "task_id": "root-task",
            "role": "root",
            "depends_on": [],
        })
        self.assertEqual(node.depends_on, ())

    def test_each_required_field_absence_is_named(self):
        for field_name in ("task_id", "role", "depends_on"):
            with self.subTest(field=field_name):
                data = {
                    "task_id": "task-1",
                    "role": "worker",
                    "depends_on": [],
                }
                del data[field_name]
                with self.assertRaises(Blocked) as ctx:
                    TaskNode.from_dict(data)
                self.assertIn(field_name, ctx.exception.detail)

    def test_task_node_mutation_after_construction_raises(self):
        node = TaskNode.from_dict({
            "task_id": "task-1",
            "role": "worker",
            "depends_on": [],
        })
        with self.assertRaises(FrozenInstanceError):
            node.task_id = "task-2"

    def test_task_node_serialisation_round_trips(self):
        node = TaskNode.from_dict({
            "task_id": "task-1",
            "role": "worker",
            "depends_on": ["task-0"],
        })
        first = node.to_json()
        restored = TaskNode.from_json(first)
        second = restored.to_json()
        self.assertEqual(first, second)

    def test_invalid_identifier_in_depends_on_labels_correct_index(self):
        # Verify error labels index correctly when invalid item is not first
        with self.assertRaises(Blocked) as ctx:
            TaskNode.from_dict({
                "task_id": "task-1",
                "role": "worker",
                "depends_on": ["good-id", "Bad-With-Caps", "another-good-id"],
            })
        # Should report error at index 1 (the invalid "Bad-With-Caps")
        self.assertIn("depends_on[1]", ctx.exception.detail)
        self.assertIn("Bad-With-Caps", ctx.exception.detail)


class TaskDagTest(unittest.TestCase):
    def test_well_formed_task_dag_constructs(self):
        dag = TaskDag.from_list([
            {"task_id": "discover", "role": "root", "depends_on": []},
            {"task_id": "analyze", "role": "worker", "depends_on": ["discover"]},
        ])
        self.assertEqual(len(dag.tasks), 2)
        self.assertEqual(dag.tasks[0].task_id, "discover")
        self.assertEqual(dag.tasks[1].depends_on, ("discover",))

    def test_duplicate_task_id_is_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            TaskDag.from_list([
                {"task_id": "task-1", "role": "root", "depends_on": []},
                {"task_id": "task-1", "role": "worker", "depends_on": []},
            ])
        self.assertIn("duplicate", ctx.exception.detail.lower())
        self.assertIn("task_id", ctx.exception.detail)

    def test_unknown_dependency_is_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            TaskDag.from_list([
                {"task_id": "task-1", "role": "root", "depends_on": []},
                {"task_id": "task-2", "role": "worker", "depends_on": ["unknown-task"]},
            ])
        self.assertIn("unknown", ctx.exception.detail.lower())
        self.assertIn("unknown-task", ctx.exception.detail)

    def test_cycle_is_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            TaskDag.from_list([
                {"task_id": "task-1", "role": "root", "depends_on": ["task-2"]},
                {"task_id": "task-2", "role": "worker", "depends_on": ["task-1"]},
            ])
        self.assertIn("cycle", ctx.exception.detail.lower())

    def test_self_loop_cycle_is_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            TaskDag.from_list([
                {"task_id": "task-1", "role": "root", "depends_on": ["task-1"]},
            ])
        self.assertIn("cycle", ctx.exception.detail.lower())

    def test_longer_cycle_is_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            TaskDag.from_list([
                {"task_id": "task-1", "role": "root", "depends_on": ["task-2"]},
                {"task_id": "task-2", "role": "worker", "depends_on": ["task-3"]},
                {"task_id": "task-3", "role": "worker", "depends_on": ["task-1"]},
            ])
        self.assertIn("cycle", ctx.exception.detail.lower())

    def test_task_dag_serialisation_round_trips(self):
        data = [
            {"task_id": "discover", "role": "root", "depends_on": []},
            {"task_id": "analyze", "role": "worker", "depends_on": ["discover"]},
        ]
        dag = TaskDag.from_list(data)
        first = dag.to_json()
        restored = TaskDag.from_json(first)
        second = restored.to_json()
        self.assertEqual(first, second)

    def test_task_dag_mutation_after_construction_raises(self):
        dag = TaskDag.from_list([
            {"task_id": "task-1", "role": "root", "depends_on": []},
        ])
        with self.assertRaises(TypeError):
            dag.tasks[0] = None

    def test_task_dag_field_reassignment_raises(self):
        # test_task_dag_mutation_after_construction_raises only proves the
        # `tasks` tuple itself rejects item assignment, which is true of
        # any tuple whether or not TaskDag is frozen -- it would pass
        # identically with `frozen=True` removed. Reassigning the `tasks`
        # field itself is what actually exercises TaskDag's own frozen
        # guarantee.
        dag = TaskDag.from_list([
            {"task_id": "task-1", "role": "root", "depends_on": []},
        ])
        with self.assertRaises(FrozenInstanceError):
            dag.tasks = ()

    def test_cycle_reachable_only_through_a_diamond_is_rejected(self):
        # A cycle that is not on the first edge explored from the entry
        # node, but only becomes visible after fanning out through a
        # diamond (start -> b1, start -> b2 -> both merge back into
        # `merge`, which depends on `start` again). Detection must not
        # depend on which branch of the diamond happens to be visited
        # first.
        with self.assertRaises(Blocked) as ctx:
            TaskDag.from_list([
                {"task_id": "start", "role": "root", "depends_on": ["merge"]},
                {"task_id": "b1", "role": "worker", "depends_on": ["start"]},
                {"task_id": "b2", "role": "worker", "depends_on": ["start"]},
                {"task_id": "merge", "role": "worker", "depends_on": ["b1", "b2"]},
            ])
        self.assertIn("cycle", ctx.exception.detail.lower())

    def test_long_linear_chain_constructs_without_recursion_error(self):
        # Regression for unbounded Python recursion in cycle detection: a
        # mostly-linear pipeline (exactly what a DAG generator emits) must
        # not depend on sys.getrecursionlimit() to construct successfully.
        # 5000 nodes comfortably exceeds the default recursion limit
        # (1000), so this fails loudly with RecursionError under a
        # recursive visit() and must pass under an iterative one.
        node_count = 5000
        data = [{"task_id": "task-0", "role": "root", "depends_on": []}]
        for index in range(1, node_count):
            data.append({
                "task_id": f"task-{index}",
                "role": "worker",
                "depends_on": [f"task-{index - 1}"],
            })
        dag = TaskDag.from_list(data)
        self.assertEqual(len(dag.tasks), node_count)

    def test_long_chain_with_back_edge_raises_blocked_not_recursion_error(self):
        node_count = 5000
        data = [{"task_id": "task-0", "role": "root", "depends_on": [f"task-{node_count - 1}"]}]
        for index in range(1, node_count):
            data.append({
                "task_id": f"task-{index}",
                "role": "worker",
                "depends_on": [f"task-{index - 1}"],
            })
        with self.assertRaises(Blocked) as ctx:
            TaskDag.from_list(data)
        self.assertIn("cycle", ctx.exception.detail.lower())


if __name__ == "__main__":
    unittest.main()
