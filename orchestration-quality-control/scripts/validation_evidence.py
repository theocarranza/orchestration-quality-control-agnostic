"""validation_evidence.py -- authoritative checking evidence, read from the run log.

The bypass this module closes, concretely. In the 2026-09-09 authoring trial the
checking worker returned three findings and the run was nonetheless checkpointed
as clean. `author_state create` took a `--findings-json` path and refused only if
the file it was handed was non-empty; the coordinator handed it a file containing
`[]`. The guard was real, but the evidence behind it was supplied by the very
agent the guard exists to constrain.

The fix is not a better guard on the same input. It is to stop accepting the
input. Findings now come from the run's own append-only, hash-chained mailbox --
the log `adapter_port.AdapterPort._append` writes at a single choke point, whose
integrity `oqc.verify` checks end to end -- and from nowhere else. A coordinator
that wants a clean checkpoint would have to produce a mailbox in which the
checking worker actually returned no findings.

Two bindings make that evidence load-bearing:

  * **Chain integrity.** `oqc.verify` is run over the whole mailbox before any
    payload is read. A hand-edited earlier envelope breaks the following
    envelope's `previous_hash` and blocks the read outright.
  * **Content binding.** A checking result carries `inspected_digest`, the digest
    of the exact proposal file map it inspected. `authoritative_findings` refuses
    to answer for a proposal whose digest differs, so a passing verdict about one
    draft can never be reused to approve a different one.

Disclosed limit, deliberately not overstated. This is file-based evidence on a
shared filesystem. A process that can write the mailbox file can rewrite the
whole chain from genesis, and `oqc.verify` cannot detect that -- it proves
internal consistency, not provenance. What is enforced here is that findings are
never *passed in*, that tampering confined to the middle of the log is caught,
and that a verdict is pinned to the content it judged. Anchoring `head_hash`
outside the mailbox is the caller's job; `authoritative_findings` returns it for
exactly that purpose. Nothing here claims process isolation the host does not
provide.
"""

import argparse
import hashlib
import json

import oqc
import qc_lib
from qc_lib import Blocked

STAGE = "validation_evidence"

#: Envelope kind a worker's returned result uses. Anything else in the mailbox
#: (requests, status notices, questions, answers) is never checking evidence.
RESULT_KIND = "result"


def proposal_digest(files):
    """sha256 over a canonical rendering of a proposal's file map.

    Canonical means: keys sorted, UTF-8, no insignificant whitespace. The same
    file map always produces the same digest on any host, so a digest recorded by
    a checking worker on one machine still binds on another. Path separators are
    normalised to '/' so a map built on Windows and one built on Linux agree.
    """
    if not isinstance(files, dict) or not files:
        raise Blocked(
            stage=STAGE,
            reason_code="invalid_proposal",
            detail="proposal file map must be a non-empty object of path -> contents",
            recovery_action="pass the preview file map the checkpoint will carry",
        )
    normalized = {}
    for path, contents in files.items():
        if not isinstance(path, str) or not isinstance(contents, str):
            raise Blocked(
                stage=STAGE,
                reason_code="invalid_proposal",
                detail="every proposal entry must map a string path to string contents",
                recovery_action="rebuild the preview file map with text contents",
            )
        normalized[path.replace("\\", "/")] = contents
    canonical = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _result_envelopes(mailbox, *, run_id):
    results = []
    for envelope in mailbox.read_all():
        if envelope.kind != RESULT_KIND:
            continue
        if run_id is not None and envelope.run_id != run_id:
            continue
        results.append(envelope)
    return results


def _checking_results(envelopes, *, digest):
    """Result envelopes that inspected exactly `digest`.

    A result without `inspected_digest` is not checking evidence at all -- it is
    a producing worker's return -- and is skipped rather than treated as a clean
    verdict. Treating it as clean is precisely the confusion this module exists
    to prevent.
    """
    matching = []
    unbound = []
    for envelope in envelopes:
        # Envelope payloads are frozen by kernel_specs (dicts become
        # MappingProxyType, lists become tuples), so an isinstance(..., dict)
        # test would silently skip every real envelope. Thaw first, then read.
        payload = qc_lib.thaw(envelope.payload)
        if not isinstance(payload, dict):
            continue
        if "findings" not in payload:
            continue
        inspected = payload.get("inspected_digest")
        if not isinstance(inspected, str) or not inspected:
            unbound.append(envelope)
            continue
        if inspected == digest:
            matching.append(envelope)
    return matching, unbound


def authoritative_findings(mailbox, *, digest, run_id=None):
    """Return the checking verdict recorded in `mailbox` for the proposal `digest`.

    Raises Blocked -- never returns a clean verdict by default -- when the chain
    does not verify, when no checking result inspected this digest, or when two
    results disagree about it.
    """
    verified = oqc.verify(mailbox)

    envelopes = _result_envelopes(mailbox, run_id=run_id)
    matching, unbound = _checking_results(envelopes, digest=digest)

    if not matching:
        if unbound:
            raise Blocked(
                stage=STAGE,
                reason_code="invalid_proposal",
                detail=(
                    f"{len(unbound)} checking result(s) in this run carry findings but no "
                    "inspected_digest, so none can be bound to the proposal being checkpointed"
                ),
                recovery_action=(
                    "have the checking worker return inspected_digest alongside its findings"
                ),
            )
        raise Blocked(
            stage=STAGE,
            reason_code="missing_target",
            detail=(
                f"no checking result in this run inspected proposal digest {digest}; "
                "a checkpoint cannot be created without a recorded verdict about this exact content"
            ),
            recovery_action="run the checking worker against this proposal before checkpointing",
        )

    verdicts = {json.dumps(_verdict_of(envelope), sort_keys=True) for envelope in matching}
    if len(verdicts) > 1:
        raise Blocked(
            stage=STAGE,
            reason_code="invalid_proposal",
            detail=(
                f"{len(matching)} checking results inspected digest {digest} and disagree; "
                "the run log cannot say which verdict is authoritative"
            ),
            recovery_action=(
                "re-run checking against a fresh proposal so exactly one verdict binds to its digest"
            ),
        )

    chosen = matching[-1]
    verdict = _verdict_of(chosen)
    return {
        "run_id": chosen.run_id,
        "worker": chosen.sender,
        "envelope_id": chosen.envelope_id,
        "inspected_digest": digest,
        "findings": verdict["findings"],
        "template_gaps": verdict["template_gaps"],
        "all_passed": verdict["all_passed"],
        "outcome": verdict["outcome"],
        "head_hash": verified.head_hash,
    }


def _verdict_of(envelope):
    payload = qc_lib.thaw(envelope.payload)
    findings = payload.get("findings")
    gaps = payload.get("template_gaps", [])
    if not isinstance(findings, list):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"envelope {envelope.envelope_id} has a non-array 'findings' payload field",
            recovery_action="have the checking worker return findings as an array",
        )
    if not isinstance(gaps, list):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"envelope {envelope.envelope_id} has a non-array 'template_gaps' payload field",
            recovery_action="have the checking worker return template_gaps as an array",
        )
    outcome = payload.get("outcome")
    all_passed = not findings and outcome != "failed"
    return {
        "findings": findings,
        "template_gaps": gaps,
        "outcome": outcome,
        "all_passed": all_passed,
    }


def load_mailbox(path):
    """Read a mailbox JSONL file, reusing oqc's own loader so failures block identically."""
    return oqc._load_mailbox_file(path)


def main():
    parser = argparse.ArgumentParser(
        description="Read the authoritative checking verdict for a proposal from a run's mailbox."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    digest_parser = sub.add_parser("digest", help="print the canonical digest of a preview folder")
    digest_parser.add_argument("--preview-dir", required=True)

    show_parser = sub.add_parser("show", help="print the recorded verdict for a preview folder")
    show_parser.add_argument("--mailbox", required=True)
    show_parser.add_argument("--preview-dir", required=True)
    show_parser.add_argument("--run-id", default=None)

    args = parser.parse_args()

    def body():
        from pathlib import Path

        preview = Path(args.preview_dir)
        if not preview.is_dir():
            raise Blocked(
                stage=STAGE,
                reason_code="missing_target",
                detail=f"preview directory does not exist: {preview}",
                recovery_action="pass the preview directory the checkpoint will carry",
            )
        files = {
            path.relative_to(preview).as_posix(): path.read_text(encoding="utf-8")
            for path in sorted(preview.rglob("*"))
            if path.is_file()
        }
        digest = proposal_digest(files)
        if args.command == "digest":
            return {"proposal_digest": digest, "file_count": len(files)}
        return authoritative_findings(
            load_mailbox(args.mailbox), digest=digest, run_id=args.run_id
        )

    qc_lib.run_main(STAGE, body)


if __name__ == "__main__":
    main()
