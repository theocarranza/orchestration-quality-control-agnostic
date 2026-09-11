"""Tests that the published schemas match what the code actually passes and produces.

Each case here pins one gap found during the 2026-09-09 trial, where a schema and
its own code disagreed and nothing caught it.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import gate_defaults
from qc_lib import Blocked

SCRIPTS = Path(__file__).resolve().parents[1]
SCHEMAS = SCRIPTS.parent / "references" / "schemas"
PACKAGE_SCHEMAS = SCRIPTS.parent / "schemas"

BRIEF = {
    "schema_version": 1,
    "languages": ["dart"],
    "package_managers": ["pub"],
    "layout": ["lib", "e2e_test"],
    "test_trees": ["e2e_test", "test"],
    "ci": [],
    "existing_orchestration": [],
    "existing_mechanism": [],
    "doc_language_hints": [],
    "profile_hints": [],
    "readme_present": True,
    "manifests": ["pubspec.yaml"],
}


def _schema(name, *, package=False):
    root = PACKAGE_SCHEMAS if package else SCHEMAS
    return json.loads((root / name).read_text(encoding="utf-8"))


class AuthorInputSchemaTest(unittest.TestCase):
    def test_every_field_gate_defaults_emits_is_declared(self):
        """The gap: outcome_involves_test_tree was emitted but not declared,
        and author_prepare sets additionalProperties false."""
        prepare = _schema("author-input.schema.json")["oneOf"][0]
        self.assertFalse(prepare["additionalProperties"])
        declared = set(prepare["properties"]) | {"operation", "outcome"}
        emitted = set(gate_defaults.author_fields(BRIEF, {}))
        self.assertEqual(
            emitted - declared,
            set(),
            "gate_defaults emits fields author-input.schema.json does not declare",
        )

    def test_outcome_involves_test_tree_is_declared(self):
        prepare = _schema("author-input.schema.json")["oneOf"][0]
        self.assertIn("outcome_involves_test_tree", prepare["properties"])


class AuthorCheckpointSchemaTest(unittest.TestCase):
    def test_findings_and_validation_are_required(self):
        """The gap: a checkpoint could report no findings in its structured record
        while its own report described three."""
        schema = _schema("author-checkpoint.schema.json")
        self.assertIn("findings", schema["required"])
        self.assertIn("validation", schema["required"])

    def test_validation_block_binds_a_verdict_to_content(self):
        schema = _schema("author-checkpoint.schema.json")
        validation = schema["properties"]["validation"]
        self.assertIn("inspected_digest", validation["required"])
        self.assertIn("all_passed", validation["required"])


class VerificationSchemaTest(unittest.TestCase):
    def test_findings_array_contents_are_defined(self):
        """The gap: an unrestricted array cannot tell a finding from an empty object."""
        schema = _schema("upgrade-verification.schema.json")
        items = schema["properties"]["findings"]["items"]
        self.assertEqual(items["type"], "object")
        self.assertTrue(items["required"])

    def test_extra_nested_fields_are_permitted_not_rejected(self):
        """Provenance flags added by an orchestrator are allowed; their presence is
        not on its own evidence of a schema violation."""
        schema = _schema("upgrade-verification.schema.json")
        self.assertTrue(schema["properties"]["findings"]["items"]["additionalProperties"])
        self.assertTrue(schema["properties"]["template_gaps"]["items"]["additionalProperties"])


class ClientDeliverySchemaTest(unittest.TestCase):
    def test_delivery_schema_is_stricter_than_the_proposal_schema(self):
        proposal = _schema("author-proposal.schema.json")
        delivery = _schema("client-delivery.schema.json", package=True)
        self.assertEqual(proposal["required"], ["files"])
        self.assertGreater(len(delivery["required"]), 10)
        for field in ("entrypoint", "workers", "operations", "files"):
            self.assertIn(field, delivery["required"])


class OverridesFailClosedTest(unittest.TestCase):
    def _run(self, overrides):
        with tempfile.TemporaryDirectory() as tmp:
            brief_path = Path(tmp) / "brief.json"
            brief_path.write_text(json.dumps(BRIEF), encoding="utf-8")
            return subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "gate_defaults.py"),
                    "author-fields",
                    "--brief-json",
                    str(brief_path),
                    "--overrides-json",
                    overrides,
                ],
                capture_output=True,
                text=True,
                env={"PYTHONPATH": str(SCRIPTS), "PATH": "/usr/bin:/bin"},
            )

    def test_valid_inline_overrides_exit_zero(self):
        result = self._run('{"shape": "multi-worker"}')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["fields"]["shape"], "multi-worker")

    def test_a_path_where_inline_json_belongs_blocks_with_exit_two(self):
        """The mistake this guards: --brief-json takes a path, --overrides-json does not."""
        result = self._run("/tmp/overrides.json")
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["reason_code"], "invalid_decision")
        self.assertIn("looks like a path", payload["detail"])
        self.assertTrue(payload["recovery_action"])

    def test_malformed_json_blocks_rather_than_raising(self):
        result = self._run("{not json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "blocked")
        self.assertNotIn("Traceback", result.stderr)

    def test_non_object_json_blocks(self):
        result = self._run("[1, 2, 3]")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["reason_code"], "invalid_decision")

    def test_helper_returns_empty_mapping_for_no_overrides(self):
        self.assertEqual(gate_defaults._overrides(""), {})
        self.assertEqual(gate_defaults._overrides(None), {})

    def test_helper_raises_blocked_not_a_decode_error(self):
        with self.assertRaises(Blocked):
            gate_defaults._overrides("{nope")


if __name__ == "__main__":
    unittest.main()
