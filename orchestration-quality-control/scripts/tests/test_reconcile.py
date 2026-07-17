import unittest

from tests import SCRIPTS_DIR

import reconcile_decision
from qc_lib import Blocked


def _checkpoint(targets=("workflow.md",)):
    return {
        "targets": list(targets),
        "findings": [
            {"id": "id-a"},
            {"id": "id-b"},
            {"id": "id-c"},
        ],
    }


class ApprovedSetTest(unittest.TestCase):
    def test_all_selects_every_finding(self):
        result = reconcile_decision.resolve_approved_set(_checkpoint(), "all")
        self.assertEqual(result, ["id-a", "id-b", "id-c"])

    def test_none_selects_nothing(self):
        result = reconcile_decision.resolve_approved_set(_checkpoint(), "none")
        self.assertEqual(result, [])

    def test_named_subset(self):
        result = reconcile_decision.resolve_approved_set(_checkpoint(), ["id-b"])
        self.assertEqual(result, ["id-b"])

    def test_unknown_id_is_blocked(self):
        with self.assertRaises(Blocked) as ctx:
            reconcile_decision.resolve_approved_set(_checkpoint(), ["id-z"])
        self.assertEqual(ctx.exception.reason_code, "unknown_finding_id")

    def test_malformed_decision_is_blocked(self):
        with self.assertRaises(Blocked) as ctx:
            reconcile_decision.resolve_approved_set(_checkpoint(), 42)
        self.assertEqual(ctx.exception.reason_code, "invalid_decision")


class FinalizeTest(unittest.TestCase):
    def test_every_approved_finding_ends_applied_or_skipped(self):
        checkpoint = _checkpoint()
        outcomes = [
            {"finding_id": "id-a", "outcome": "applied", "applied_path": "workflow.md"},
            {"finding_id": "id-b", "outcome": "skipped", "reason": "capability_insufficient: cannot create file"},
        ]
        result = reconcile_decision.finalize(checkpoint, ["id-a", "id-b"], outcomes)
        by_id = {r["finding_id"]: r for r in result["resolution"]}
        self.assertEqual(by_id["id-a"]["outcome"], "applied")
        self.assertEqual(by_id["id-b"]["outcome"], "skipped")
        # id-c was never approved: auto-filled declined, never silently dropped
        self.assertEqual(by_id["id-c"]["outcome"], "declined")

    def test_missing_outcome_for_approved_finding_is_blocked(self):
        checkpoint = _checkpoint()
        outcomes = [{"finding_id": "id-a", "outcome": "applied"}]
        with self.assertRaises(Blocked) as ctx:
            reconcile_decision.finalize(checkpoint, ["id-a", "id-b"], outcomes)
        self.assertEqual(ctx.exception.reason_code, "malformed_checkpoint")

    def test_skipped_without_reason_is_blocked(self):
        checkpoint = _checkpoint()
        outcomes = [{"finding_id": "id-a", "outcome": "skipped"}]
        with self.assertRaises(Blocked) as ctx:
            reconcile_decision.finalize(checkpoint, ["id-a"], outcomes)
        self.assertEqual(ctx.exception.reason_code, "capability_insufficient")

    def test_applied_path_outside_targets_is_blocked(self):
        checkpoint = _checkpoint(targets=("workflow.md",))
        outcomes = [{"finding_id": "id-a", "outcome": "applied", "applied_path": "other-file.md"}]
        with self.assertRaises(Blocked) as ctx:
            reconcile_decision.finalize(checkpoint, ["id-a"], outcomes)
        self.assertEqual(ctx.exception.reason_code, "target_outside_approved_set")

    def test_outcome_for_unknown_finding_id_is_blocked(self):
        checkpoint = _checkpoint()
        outcomes = [{"finding_id": "id-z", "outcome": "applied"}]
        with self.assertRaises(Blocked) as ctx:
            reconcile_decision.finalize(checkpoint, ["id-a"], outcomes)
        self.assertEqual(ctx.exception.reason_code, "unknown_finding_id")

    def test_none_decision_declines_everything(self):
        checkpoint = _checkpoint()
        result = reconcile_decision.finalize(checkpoint, [], [])
        outcomes = {r["outcome"] for r in result["resolution"]}
        self.assertEqual(outcomes, {"declined"})


if __name__ == "__main__":
    unittest.main()
