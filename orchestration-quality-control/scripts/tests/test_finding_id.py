import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import SCRIPTS_DIR

import derive_finding_id
from qc_lib import Blocked


class FindingIdUnitTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, rel_path, content):
        path = self.workspace / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return rel_path

    def test_id_is_stable_across_line_drift(self):
        # The defining property: identical rule+kind+anchor produces the same
        # id no matter what line the anchor sits on, or what surrounds it.
        rel = self._write(
            "workflow.md",
            "line one\nline two\nTHE ANCHOR TEXT\nline four\n",
        )
        first = derive_finding_id.derive(
            str(self.workspace), rel, "rules-workflow-quality-control.md#W6",
            "core/workflow-authoring", "THE ANCHOR TEXT", [],
        )

        # simulate a partial-apply edit that inserts 20 lines above the anchor
        padded = "\n".join(f"inserted line {i}" for i in range(20))
        self._write("workflow.md", padded + "\nline one\nline two\nTHE ANCHOR TEXT\nline four\n")
        second = derive_finding_id.derive(
            str(self.workspace), rel, "rules-workflow-quality-control.md#W6",
            "core/workflow-authoring", "THE ANCHOR TEXT", [],
        )
        self.assertEqual(first["id"], second["id"])

    def test_id_changes_when_anchor_differs(self):
        rel = self._write("workflow.md", "ANCHOR ONE\nANCHOR TWO\n")
        id_one = derive_finding_id.derive(
            str(self.workspace), rel, "rules-workflow-quality-control.md#W6",
            "core/workflow-authoring", "ANCHOR ONE", [],
        )
        id_two = derive_finding_id.derive(
            str(self.workspace), rel, "rules-workflow-quality-control.md#W6",
            "core/workflow-authoring", "ANCHOR TWO", [],
        )
        self.assertNotEqual(id_one["id"], id_two["id"])

    def test_anchor_not_found_is_blocked(self):
        rel = self._write("workflow.md", "actual content\n")
        with self.assertRaises(Blocked) as ctx:
            derive_finding_id.derive(
                str(self.workspace), rel, "rules-workflow-quality-control.md#W6",
                "core/workflow-authoring", "text that does not exist in the file", [],
            )
        self.assertEqual(ctx.exception.reason_code, "anchor_not_found")

    def test_duplicate_anchor_gets_occurrence_suffix(self):
        rel = self._write("workflow.md", "DUP\nDUP\n")
        first = derive_finding_id.derive(
            str(self.workspace), rel, "rules-workflow-quality-control.md#W6",
            "core/workflow-authoring", "DUP", [],
        )
        second = derive_finding_id.derive(
            str(self.workspace), rel, "rules-workflow-quality-control.md#W6",
            "core/workflow-authoring", "DUP", [first["id"]],
        )
        self.assertNotEqual(first["id"], second["id"])
        self.assertTrue(second["id"].endswith("-2"))

    def test_occurrence_suffix_handles_sparse_existing_ids_without_collision(self):
        rel = self._write("workflow.md", "DUP\nDUP\n")
        first = derive_finding_id.derive(
            str(self.workspace), rel, "rules-workflow-quality-control.md#W6",
            "core/workflow-authoring", "DUP", [],
        )
        base_id = first["id"]
        # Existing contains base_id and base_id-2 and base_id-3
        third = derive_finding_id.derive(
            str(self.workspace), rel, "rules-workflow-quality-control.md#W6",
            "core/workflow-authoring", "DUP", [base_id, f"{base_id}-2", f"{base_id}-4"],
        )
        self.assertEqual(third["id"], f"{base_id}-3")

    def test_verify_marks_resolved_finding_not_still_open(self):
        rel = self._write("workflow.md", "before text\n")
        finding_id = derive_finding_id.derive(
            str(self.workspace), rel, "rules-workflow-quality-control.md#W6",
            "core/workflow-authoring", "before text", [],
        )["id"]
        checkpoint_path = self.workspace / "checkpoint.json"
        checkpoint_path.write_text(
            json.dumps(
                {
                    "findings": [
                        {
                            "id": finding_id,
                            "location": {"path": rel, "section": "x"},
                            "anchor": "before text",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        # partial apply: the anchor is gone now
        self._write("workflow.md", "after text\n")
        result = derive_finding_id.verify(str(self.workspace), str(checkpoint_path))
        self.assertFalse(result["results"][0]["still_open"])

    def test_verify_marks_untouched_finding_still_open(self):
        rel = self._write("workflow.md", "unrelated fix happened\nbefore text\n")
        finding_id = derive_finding_id.derive(
            str(self.workspace), rel, "rules-workflow-quality-control.md#W6",
            "core/workflow-authoring", "before text", [],
        )["id"]
        checkpoint_path = self.workspace / "checkpoint.json"
        checkpoint_path.write_text(
            json.dumps(
                {
                    "findings": [
                        {
                            "id": finding_id,
                            "location": {"path": rel, "section": "x"},
                            "anchor": "before text",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        # partial apply of a DIFFERENT finding shifts every line, this anchor untouched
        self._write("workflow.md", "inserted\nline\nunrelated fix happened\nbefore text\n")
        result = derive_finding_id.verify(str(self.workspace), str(checkpoint_path))
        self.assertTrue(result["results"][0]["still_open"])


class PartialApplyConformanceTest(unittest.TestCase):
    """Ships as a fixture pair (before.md / after.md) rather than inline
    strings, so the conformance property is inspectable on its own: applying
    one finding's fix (expanding step 2 into 2a/2b) shifts the 'Stop
    conditions' section by two lines. A second, untouched finding anchored
    there must still resolve to the identical id after that shift.
    """

    FIXTURES = Path(__file__).resolve().parent / "fixtures" / "partial-apply"
    UNTOUCHED_RULE = "rules-orchestrator-quality-control.md#O5"
    UNTOUCHED_KIND = "core/orchestration"
    UNTOUCHED_ANCHOR = "The orchestrator halts and reports on any worker failure."

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_untouched_finding_id_survives_partial_apply(self):
        target = self.workspace / "deploy-orchestrator.md"

        target.write_text(self.FIXTURES.joinpath("before.md").read_text(encoding="utf-8"), encoding="utf-8")
        id_before = derive_finding_id.derive(
            str(self.workspace), "deploy-orchestrator.md",
            self.UNTOUCHED_RULE, self.UNTOUCHED_KIND, self.UNTOUCHED_ANCHOR, [],
        )["id"]

        # simulate: the other finding (step 2 coverage) was applied, shifting lines
        target.write_text(self.FIXTURES.joinpath("after.md").read_text(encoding="utf-8"), encoding="utf-8")
        id_after = derive_finding_id.derive(
            str(self.workspace), "deploy-orchestrator.md",
            self.UNTOUCHED_RULE, self.UNTOUCHED_KIND, self.UNTOUCHED_ANCHOR, [],
        )["id"]

        self.assertEqual(id_before, id_after)


class FindingIdCliTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "derive_finding_id.py"), *args],
            capture_output=True,
            text=True,
        )

    def test_derive_cli_end_to_end(self):
        (self.workspace / "workflow.md").write_text("some anchor text\n", encoding="utf-8")
        proc = self._run(
            "derive",
            "--workspace", str(self.workspace),
            "--path", "workflow.md",
            "--rule", "rules-workflow-quality-control.md#W6",
            "--kind", "core/workflow-authoring",
            "--anchor-text", "some anchor text",
        )
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertRegex(payload["id"], r"^W6-workflow-authoring-[0-9a-f]{10}$")


if __name__ == "__main__":
    unittest.main()
