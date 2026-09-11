import unittest
from dataclasses import replace

from compile_workflow import compile_workflow
from orchestrator_contract import compile_orchestrator, OrchestratorContract
from qc_lib import Blocked


def _compiled(outcome="ship", named_inputs=None):
    return compile_workflow({"run_id": "run-contract", "created_at": "2026-09-07T12:00:00Z",
        "outcome": outcome, "shape": "single-agent", "named_inputs": named_inputs or [],
        "outcome_involves_test_tree": True, "profile": "core"})


class ContractTests(unittest.TestCase):
    def test_roundtrip_and_immutability(self):
        contract = compile_orchestrator(_compiled(), 3)
        roundtrip = OrchestratorContract.from_json(contract.to_json())
        self.assertEqual(contract, roundtrip)
        self.assertEqual(contract.to_json(), roundtrip.to_json())
        with self.assertRaises(TypeError):
            contract.agent_specs["author"] = object()
        self.assertIn("engine", contract.control_instructions)

    def test_budget_and_bindings_rejected(self):
        with self.assertRaises(Blocked): compile_orchestrator(_compiled(), True)
        data = compile_orchestrator(_compiled(), 2).to_dict()
        data["agent_specs"]["author"]["role"] = "other"
        with self.assertRaises(Blocked): OrchestratorContract.from_dict(data)

    def test_discovery_decisions_change_contract(self):
        a = compile_orchestrator(_compiled("a"), 2)
        b = compile_orchestrator(_compiled("b"), 2)
        self.assertNotEqual(a.to_json(), b.to_json())

    def test_direct_constructor_and_replace_reject_changed_instructions(self):
        contract = compile_orchestrator(_compiled(), 3)
        with self.assertRaises(Blocked):
            OrchestratorContract(contract.run_spec, contract.task_dag,
                                 contract.agent_specs, 3, {"engine": "changed"})
        with self.assertRaises(Blocked):
            replace(contract, control_instructions={"engine": "changed"})

    def test_direct_constructor_revalidates_records_and_bindings(self):
        contract = compile_orchestrator(_compiled(), 3)
        specs = dict(contract.agent_specs)
        specs["extra"] = specs["author"]
        with self.assertRaises(Blocked):
            OrchestratorContract(contract.run_spec, contract.task_dag, specs, 3,
                                 contract.control_instructions)

    def test_all_budget_types_are_rejected(self):
        for value in (0, -1, True, False, 1.5, "1"):
            with self.subTest(value=value), self.assertRaises(Blocked):
                compile_orchestrator(_compiled(), value)

    def test_nested_values_and_serialized_dict_are_independent(self):
        contract = compile_orchestrator(_compiled(), 3)
        with self.assertRaises(TypeError):
            contract.control_instructions["nested"] = "x"
        data = contract.to_dict()
        data["control_instructions"]["engine"] = "changed"
        self.assertEqual(contract.control_instructions["engine"],
                         "The deterministic engine owns scheduling, brief compilation, validation, gating, retries, phase transitions, and stopping.")

    def test_public_canonical_view_cannot_change_source(self):
        with self.assertRaises(TypeError):
            import orchestrator_contract
            orchestrator_contract.CONTROL_INSTRUCTIONS["engine"] = "changed"
        self.assertIn("scheduling", compile_orchestrator(_compiled(), 1).control_instructions["engine"])

    def test_duplicate_agent_ids_are_rejected(self):
        # Add a second valid role by compiling the isolated topology.
        isolated = compile_workflow({"run_id": "r2", "created_at": "2026-09-07T12:00:00Z",
            "outcome": "x", "shape": "isolated-workers", "named_inputs": ["a", "b"],
            "outcome_involves_test_tree": True, "profile": "core"})
        data = compile_orchestrator(isolated, 2).to_dict()
        roles = list(data["agent_specs"])
        data["agent_specs"][roles[1]]["agent_id"] = data["agent_specs"][roles[0]]["agent_id"]
        with self.assertRaises(Blocked): OrchestratorContract.from_dict(data)

    def test_missing_and_extra_dag_roles_are_rejected(self):
        isolated = compile_workflow({"run_id": "r3", "created_at": "2026-09-07T12:00:00Z",
            "outcome": "x", "shape": "isolated-workers", "named_inputs": ["a", "b"],
            "outcome_involves_test_tree": True, "profile": "core"})
        data = compile_orchestrator(isolated, 2).to_dict()
        role = next(iter(data["agent_specs"]))
        del data["agent_specs"][role]
        with self.assertRaises(Blocked): OrchestratorContract.from_dict(data)
        data = compile_orchestrator(isolated, 2).to_dict()
        data["agent_specs"]["extra"] = data["agent_specs"][role]
        with self.assertRaises(Blocked): OrchestratorContract.from_dict(data)

    def test_changed_discovery_topology_changes_contract(self):
        def workflow(named_inputs):
            return compile_workflow({"run_id": "r4", "created_at": "2026-09-07T12:00:00Z",
                "outcome": "same", "shape": "isolated-workers", "named_inputs": named_inputs,
                "outcome_involves_test_tree": True, "profile": "core"})
        a = compile_orchestrator(workflow(["a"]), 2)
        b = compile_orchestrator(workflow(["a", "b"]), 2)
        self.assertNotEqual(a.task_dag.to_list(), b.task_dag.to_list())
        self.assertNotEqual(a.to_json(), b.to_json())

    def test_exact_role_coverage_and_key_mismatch_are_rejected(self):
        data = compile_orchestrator(_compiled(), 2).to_dict()
        data["agent_specs"]["wrong"] = data["agent_specs"].pop("author")
        with self.assertRaises(Blocked): OrchestratorContract.from_dict(data)

    def test_canonical_instructions_reserve_root_and_orchestrator_authority(self):
        instructions = compile_orchestrator(_compiled(), 2).control_instructions
        text = " ".join(instructions.values()).lower()
        for phrase in ("root remains passive", "single orchestrator delegation",
                       "receiving results", "relaying an engine-declared question",
                       "cannot rewrite the mailbox", "cannot mutate state",
                       "scheduling", "brief compilation", "validation", "gating",
                       "retries", "phase transitions", "stopping"):
            self.assertIn(phrase, text)

    def test_from_json_rejects_malformed_json_with_blocked(self):
        with self.assertRaises(Blocked) as caught:
            OrchestratorContract.from_json("{")
        self.assertEqual(caught.exception.stage, "orchestrator_contract")
        self.assertEqual(caught.exception.reason_code, "malformed_checkpoint")

    def test_from_json_rejects_non_string_with_blocked(self):
        with self.assertRaises(Blocked) as caught:
            OrchestratorContract.from_json(123)
        self.assertEqual(caught.exception.stage, "orchestrator_contract")
        self.assertEqual(caught.exception.reason_code, "malformed_checkpoint")


if __name__ == "__main__":
    unittest.main()
