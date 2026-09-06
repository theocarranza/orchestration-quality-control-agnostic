"""adapter_port.py — the narrow port between the deterministic kernel and a host.

This is the Outcome 2 Task 4 slice of
AI_Codex/Architecture/ADR/0014-generated-workflow-deterministic-kernel.md.
Decision 0 keeps the engine (deterministic code) authoritative over what
runs and what a step's outcome means; decision 3 makes isolation the
primary asset. `AdapterPort` is the seam a real host adapter implements in
a later outcome (Outcome 3) so the kernel never has to learn a host name, a
model id, or any other vendor vocabulary.

Exactly four operations, matching the master plan's Outcome 2 line and the
ADR's diagram: spawning one execution agent for one task attempt, emitting
a root-facing status/phase change, relaying a worker's question up to
root, and a hooks/policy enforcement boundary. There is no fifth
operation, and none of the four lets one worker address another worker or
lets root address a worker directly -- `sender`/`recipient` are never
caller-supplied for those two identities; they are fixed by the method
itself, and `_append` re-checks every pairing against
`router.validate_pair` before it ever reaches the mailbox. This makes the
isolation guarantee structural (the API has no parameter that could carry
an illegal pair) as well as enforced (the shared append path checks
anyway, for any pairing a future concrete method might build).

Outcome 3 Task 1 extends the same discipline to the hash chain.
`_append` takes an envelope's *content* (ids, pairing, kind, payload,
timestamp) -- never a pre-built, already-schema-valid `Envelope` -- and is
the only place `schema_version` and `previous_hash` are ever written. A
concrete method cannot pass either: there is no parameter for them to
occupy. This is deliberate, not an oversight: if a concrete method could
construct a fully-formed envelope on its own, nothing would stop a future
one (a real host adapter, Task 4) from getting the chain wrong the same
way a fixed enum or a hand-rolled sender/recipient pairing could once have
gotten isolation wrong. Making the correct thing the only expressible
thing is the same principle `router.validate_pair` already applies to
pairing; this module now applies it to chaining too.
"""

from abc import ABC, abstractmethod

from kernel_specs import ENVELOPE_SCHEMA_VERSION, GENESIS_HASH, Envelope
from router import validate_pair


class AdapterPort(ABC):
    """The kernel-facing seam a host adapter implements.

    Every concrete method appends to `mailbox` (a `mailbox.Mailbox`, taken
    as a plain duck-typed parameter with an `append` method so this module
    never has to import a concrete adapter's storage) and returns the
    Envelope(s) it appended, so a caller (an orchestrator loop, or a test)
    can inspect exactly what happened without re-reading the whole
    mailbox. None of the four methods takes a `sender` or `recipient`
    parameter: legality of who may talk to whom is fixed at the API level,
    not left to a caller's discretion.
    """

    def _append(self, mailbox, *, envelope_id, run_id, sender, recipient,
                kind, payload, created_at):
        """Construct one envelope from its content, chain it, then append.

        This is the one path every concrete method below goes through to
        produce an envelope at all -- there is no way to build one that
        skips it. A concrete method supplies only content: identity fields
        (`envelope_id`, `run_id`), pairing (`sender`, `recipient`), and
        what is being said (`kind`, `payload`, `created_at`). It never
        supplies `schema_version` or `previous_hash`; this method's
        signature has no parameter for either, so passing one is a
        `TypeError`, not a value that gets silently accepted and then
        overridden. `_append` alone decides both:

        - `schema_version` is always `kernel_specs.ENVELOPE_SCHEMA_VERSION`,
          the current Envelope contract version.
        - `previous_hash` is `kernel_specs.GENESIS_HASH` if `mailbox` is
          still empty, or `kernel_specs.Envelope.hash()` of `mailbox`'s
          current last envelope otherwise -- read fresh from `mailbox` on
          every call, never cached, so it is always the *actual*
          predecessor's hash, not whatever the caller might have assumed.

        `validate_pair(sender, recipient)` runs first and raises
        `qc_lib.Blocked` (not a second error type) before anything is
        constructed or `mailbox.append` is ever called, so a rejected
        pairing never partially lands in the mailbox. The envelope is then
        built via `kernel_specs.Envelope.from_dict`, which re-validates the
        whole result against schemas/envelope.schema.json exactly like
        every other Envelope construction path in this kernel -- there is
        no hand-patched field here that skips that check.

        This is what makes producers -- `FakeAdapter` today, a real host
        adapter later -- genuinely unaware of hashing (and of the current
        schema version), per this module's own docstring above: not merely
        that their values would be overridden, but that they have no way
        to supply one in the first place.
        """
        validate_pair(sender, recipient)
        history = mailbox.read_all()
        previous_hash = history[-1].hash() if history else GENESIS_HASH
        envelope = Envelope.from_dict({
            "schema_version": ENVELOPE_SCHEMA_VERSION,
            "envelope_id": envelope_id,
            "run_id": run_id,
            "sender": sender,
            "recipient": recipient,
            "kind": kind,
            "payload": payload,
            "created_at": created_at,
            "previous_hash": previous_hash,
        })
        mailbox.append(envelope)
        return envelope

    @abstractmethod
    def spawn(self, mailbox, *, run_id, task_id, attempt, agent_id, brief):
        """Ask the host to run one execution agent for one task attempt.

        Appends a 'request' envelope from 'orchestrator' to
        'agent:<agent_id>' whose payload carries at least `task_id`,
        `attempt`, and `brief` -- the compiled instructions for this
        attempt, including any critique carried forward from a prior
        failed attempt on the same task. Returns whatever envelope(s) this
        call appended.
        """
        raise NotImplementedError

    @abstractmethod
    def emit_status(self, mailbox, *, run_id, phase, context=None):
        """Announce a phase/status transition, orchestrator -> root.

        Appends a 'status' envelope whose payload carries `phase` (one of
        `run_state.PHASES`) merged with `context`, and returns it. This is
        the only way a phase transition -- including the terminal
        'blocked' and 'awaiting-user-input' phases -- reaches the mailbox.
        Per ADR 0014 decision 4, only engine code (gate.retry_or_block)
        decides to request those two phases; this method only records
        that decision, it does not make it.
        """
        raise NotImplementedError

    @abstractmethod
    def relay_question(self, mailbox, *, run_id, question):
        """Relay a worker's question up to root, orchestrator -> root.

        Appends a 'question' envelope and returns it. A worker never
        addresses root directly through this port: only the orchestrator
        identity sends a 'question' envelope, and only to 'root'. A real
        host adapter uses this to forward a question it already received
        from a worker over its own, separate worker<->orchestrator
        channel -- this method is the relay, not the origination.
        """
        raise NotImplementedError

    @abstractmethod
    def enforce_policy(self, *, run_id, hook_name, context=None):
        """The hooks/policy boundary.

        Host-specific enforcement (sandboxing, write-boundary checks,
        pre/post-tool-use hooks) happens entirely inside a concrete
        adapter's implementation of this method. The kernel calls it once
        per named lifecycle point (`hook_name`) and never inspects what it
        does internally; a `qc_lib.Blocked` raised here is authoritative
        and stops the run at this step. Returns whatever policy metadata
        the adapter wants to disclose -- a fake adapter may return an
        empty mapping. This method never touches a mailbox: it is a pure
        gate, not a hand-off.
        """
        raise NotImplementedError
