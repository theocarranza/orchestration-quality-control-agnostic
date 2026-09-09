"""Tests for authoritative checking evidence.

The regression these pin is the 2026-09-09 trial's empty-findings bypass: a
checking worker returned three findings and the coordinator handed the checkpoint
command a file containing `[]`. Findings must come from the run's hash-chained
mailbox and must be bound to the digest of the exact proposal being approved.
"""

import json
import tempfile
import unittest
from pathlib import Path

import validation_evidence
from kernel_specs import GENESIS_HASH, Envelope
from mailbox import Mailbox
from qc_lib import Blocked


def _envelope(previous_hash, *, envelope_id, run_id="run-1", sender, recipient, kind, payload):
    return Envelope.from_dict(
        {
            "schema_version": 2,
            "envelope_id": envelope_id,
            "run_id": run_id,
            "sender": sender,
            "recipient": recipient,
            "kind": kind,
            "payload": payload,
            "created_at": "2026-09-09T18:00:00Z",
            "previous_hash": previous_hash,
        }
    )


def _chain(steps):
    """Build a correctly hash-chained, correctly routed mailbox.

    `steps` is a list of (sender, recipient, kind, payload). The router
    (scripts/router.py, enforced by oqc.verify) rejects self-pairs and any
    result without a preceding request for the same task and attempt, so these
    fixtures must be built the way the real adapter port builds them.
    """
    box = Mailbox()
    previous = GENESIS_HASH
    for index, (sender, recipient, kind, payload) in enumerate(steps, start=1):
        envelope = _envelope(
            previous,
            envelope_id=f"env-{index}",
            sender=sender,
            recipient=recipient,
            kind=kind,
            payload=payload,
        )
        box.append(envelope)
        previous = envelope.hash()
    return box


def _checked(payload, *, worker="validator", task_id="check", attempt=1):
    """A routed request/result pair for one checking attempt."""
    return [
        ("orchestrator", f"agent:{worker}", "request", {"task_id": task_id, "attempt": attempt}),
        (f"agent:{worker}", "orchestrator", "result", dict(payload, task_id=task_id, attempt=attempt)),
    ]


FILES = {"ARCHITECTURE.md": "# Architecture\n", "rules/rules-a.md": "- Rule.\n"}


class ProposalDigestTest(unittest.TestCase):
    def test_digest_is_stable_for_the_same_map(self):
        self.assertEqual(
            validation_evidence.proposal_digest(FILES),
            validation_evidence.proposal_digest(dict(reversed(list(FILES.items())))),
        )

    def test_digest_changes_when_contents_change(self):
        altered = dict(FILES, **{"ARCHITECTURE.md": "# Architecture v2\n"})
        self.assertNotEqual(
            validation_evidence.proposal_digest(FILES),
            validation_evidence.proposal_digest(altered),
        )

    def test_digest_changes_when_a_file_is_added(self):
        added = dict(FILES, **{"extra.md": "# Extra\n"})
        self.assertNotEqual(
            validation_evidence.proposal_digest(FILES),
            validation_evidence.proposal_digest(added),
        )

    def test_backslash_paths_normalize_to_the_same_digest(self):
        windows = {"ARCHITECTURE.md": "# Architecture\n", "rules\\rules-a.md": "- Rule.\n"}
        self.assertEqual(
            validation_evidence.proposal_digest(FILES),
            validation_evidence.proposal_digest(windows),
        )

    def test_empty_map_is_blocked(self):
        with self.assertRaises(Blocked) as caught:
            validation_evidence.proposal_digest({})
        self.assertEqual(caught.exception.reason_code, "invalid_proposal")

    def test_non_text_contents_are_blocked(self):
        with self.assertRaises(Blocked) as caught:
            validation_evidence.proposal_digest({"a.md": 3})
        self.assertEqual(caught.exception.reason_code, "invalid_proposal")


class AuthoritativeFindingsTest(unittest.TestCase):
    def setUp(self):
        self.digest = validation_evidence.proposal_digest(FILES)

    def _clean_mailbox(self):
        return _chain(
            _checked({"outcome": "passed", "inspected_digest": self.digest, "findings": []})
        )

    def _failing_mailbox(self, findings=None):
        findings = (
            findings
            if findings is not None
            else [
                {"id": "O4-x", "severity": "high", "summary": "ungated worker return"},
                {"id": "O3-y", "severity": "medium", "summary": "return shape mismatch"},
                {"id": "O6-z", "severity": "medium", "summary": "state never persisted"},
            ]
        )
        return _chain(
            _checked(
                {"outcome": "failed", "inspected_digest": self.digest, "findings": findings}
            )
        )

    def test_clean_run_reports_all_passed(self):
        verdict = validation_evidence.authoritative_findings(
            self._clean_mailbox(), digest=self.digest
        )
        self.assertTrue(verdict["all_passed"])
        self.assertEqual(verdict["findings"], [])
        self.assertEqual(verdict["worker"], "agent:validator")
        self.assertEqual(verdict["inspected_digest"], self.digest)

    def test_verdict_carries_the_head_hash_for_external_anchoring(self):
        verdict = validation_evidence.authoritative_findings(
            self._clean_mailbox(), digest=self.digest
        )
        self.assertRegex(verdict["head_hash"], r"^[0-9a-f]{64}$")

    def test_failing_run_reports_every_finding(self):
        verdict = validation_evidence.authoritative_findings(
            self._failing_mailbox(), digest=self.digest
        )
        self.assertFalse(verdict["all_passed"])
        self.assertEqual(len(verdict["findings"]), 3)

    def test_findings_cannot_be_supplied_by_the_caller(self):
        """The bypass regression. There is no parameter through which to pass findings."""
        import inspect

        signature = inspect.signature(validation_evidence.authoritative_findings)
        self.assertEqual(sorted(signature.parameters), ["digest", "mailbox", "run_id"])

    def test_worker_reporting_failed_with_no_findings_is_not_all_passed(self):
        verdict = validation_evidence.authoritative_findings(
            self._failing_mailbox(findings=[]), digest=self.digest
        )
        self.assertFalse(verdict["all_passed"])

    def test_verdict_about_a_different_proposal_does_not_bind(self):
        other = validation_evidence.proposal_digest({"other.md": "# Other\n"})
        with self.assertRaises(Blocked) as caught:
            validation_evidence.authoritative_findings(self._clean_mailbox(), digest=other)
        self.assertEqual(caught.exception.reason_code, "missing_target")

    def test_run_with_no_checking_result_is_blocked(self):
        mailbox = _chain(
            _checked({"outcome": "passed"}, worker="author", task_id="draft")
        )
        with self.assertRaises(Blocked) as caught:
            validation_evidence.authoritative_findings(mailbox, digest=self.digest)
        self.assertEqual(caught.exception.reason_code, "missing_target")

    def test_checking_result_without_a_digest_is_blocked_not_treated_as_clean(self):
        mailbox = _chain(_checked({"outcome": "passed", "findings": []}))
        with self.assertRaises(Blocked) as caught:
            validation_evidence.authoritative_findings(mailbox, digest=self.digest)
        self.assertEqual(caught.exception.reason_code, "invalid_proposal")

    def test_two_disagreeing_verdicts_about_one_digest_are_blocked(self):
        mailbox = _chain(
            _checked(
                {
                    "outcome": "failed",
                    "inspected_digest": self.digest,
                    "findings": [{"id": "a", "severity": "high", "summary": "x"}],
                },
                attempt=1,
            )
            + _checked(
                {"outcome": "passed", "inspected_digest": self.digest, "findings": []},
                attempt=2,
            )
        )
        with self.assertRaises(Blocked) as caught:
            validation_evidence.authoritative_findings(mailbox, digest=self.digest)
        self.assertEqual(caught.exception.reason_code, "invalid_proposal")

    def test_template_gaps_are_carried_separately_from_findings(self):
        mailbox = _chain(
            _checked(
                {
                    "outcome": "passed",
                    "inspected_digest": self.digest,
                    "findings": [],
                    "template_gaps": [{"id": "TG-1", "invariant": "hashes in hand-offs"}],
                }
            )
        )
        verdict = validation_evidence.authoritative_findings(mailbox, digest=self.digest)
        self.assertEqual(verdict["findings"], [])
        self.assertEqual(len(verdict["template_gaps"]), 1)

    def test_non_array_findings_payload_is_blocked(self):
        mailbox = _chain(
            _checked(
                {
                    "outcome": "passed",
                    "inspected_digest": self.digest,
                    "findings": {"count": 0},
                }
            )
        )
        with self.assertRaises(Blocked) as caught:
            validation_evidence.authoritative_findings(mailbox, digest=self.digest)
        self.assertEqual(caught.exception.reason_code, "malformed_checkpoint")


class ChainIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.digest = validation_evidence.proposal_digest(FILES)

    def test_a_tampered_earlier_envelope_blocks_the_read(self):
        """Editing a failing verdict to look clean breaks the following previous_hash."""
        mailbox = _chain(
            _checked(
                {
                    "outcome": "failed",
                    "inspected_digest": self.digest,
                    "findings": [{"id": "a", "severity": "high", "summary": "real problem"}],
                }
            )
            + [("orchestrator", "root", "status", {"phase": "awaiting_approval"})]
        )
        lines = mailbox.to_jsonl().strip().split("\n")
        tampered = json.loads(lines[1])
        tampered["payload"]["findings"] = []
        tampered["payload"]["outcome"] = "passed"
        rebuilt = Mailbox.from_jsonl(
            lines[0] + "\n" + json.dumps(tampered) + "\n" + lines[2] + "\n"
        )
        with self.assertRaises(Blocked):
            validation_evidence.authoritative_findings(rebuilt, digest=self.digest)


class DigestCliTest(unittest.TestCase):
    def test_digest_of_a_preview_folder_matches_the_in_memory_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            preview = Path(tmp) / "preview"
            for name, body in FILES.items():
                target = preview / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body, encoding="utf-8")
            from_disk = {
                path.relative_to(preview).as_posix(): path.read_text(encoding="utf-8")
                for path in sorted(preview.rglob("*"))
                if path.is_file()
            }
            self.assertEqual(
                validation_evidence.proposal_digest(from_disk),
                validation_evidence.proposal_digest(FILES),
            )


if __name__ == "__main__":
    unittest.main()
