import inspect
import unittest
from dataclasses import replace

from adapter_port import AdapterPort
from fake_adapter import FakeAdapter
from gate import AnswerDecision, RetryDecision, AWAITING_USER_INPUT, approve_answer
from qc_lib import freeze
from kernel_specs import Envelope, GENESIS_HASH
from mailbox import Mailbox
from qc_lib import Blocked
from run_state import reduce


class FakeAdapterIsAnAdapterPortTest(unittest.TestCase):
    def test_fake_adapter_is_an_adapter_port(self):
        adapter = FakeAdapter({})
        self.assertIsInstance(adapter, AdapterPort)


class SpawnPassingResultTest(unittest.TestCase):
    def test_spawn_appends_a_request_then_a_result_envelope(self):
        mailbox = Mailbox()
        adapter = FakeAdapter({("task-1", 1): {"outcome": "passed"}})
        request, result = adapter.spawn(
            mailbox, run_id="run-1", task_id="task-1", attempt=1,
            agent_id="worker-1", brief={"critique": None},
        )
        self.assertEqual(mailbox.read_all(), (request, result))

        self.assertEqual(request.kind, "request")
        self.assertEqual(request.sender, "orchestrator")
        self.assertEqual(request.recipient, "agent:worker-1")
        self.assertEqual(request.payload["task_id"], "task-1")
        self.assertEqual(request.payload["attempt"], 1)
        self.assertEqual(request.payload["brief"]["critique"], None)

        self.assertEqual(result.kind, "result")
        self.assertEqual(result.sender, "agent:worker-1")
        self.assertEqual(result.recipient, "orchestrator")
        self.assertEqual(result.payload["task_id"], "task-1")
        self.assertEqual(result.payload["attempt"], 1)
        self.assertEqual(result.payload["outcome"], "passed")
        self.assertNotIn("critique", result.payload)

    def test_spawn_return_value_matches_mailbox_order(self):
        mailbox = Mailbox()
        adapter = FakeAdapter({("task-1", 1): {"outcome": "passed"}})
        returned = adapter.spawn(
            mailbox, run_id="run-1", task_id="task-1", attempt=1,
            agent_id="worker-1", brief={},
        )
        self.assertEqual(returned, mailbox.read_all())


class SpawnFailingResultTest(unittest.TestCase):
    def test_spawn_appends_a_failed_result_carrying_the_scripted_critique(self):
        mailbox = Mailbox()
        adapter = FakeAdapter({
            ("task-1", 1): {"outcome": "failed", "critique": "wrong shape"},
        })
        _, result = adapter.spawn(
            mailbox, run_id="run-1", task_id="task-1", attempt=1,
            agent_id="worker-1", brief={},
        )
        self.assertEqual(result.payload["outcome"], "failed")
        self.assertEqual(result.payload["critique"], "wrong shape")

    def test_spawn_preserves_artifact_and_freezes_question_payload(self):
        mailbox = Mailbox()
        adapter = FakeAdapter({
            ("task-1", 1): {"outcome": "failed", "critique": "needs choice",
                            "artifact": "draft.txt",
                            "question": {"question_id": "q-1", "prompt": "Retry?"}},
        })
        _, result = adapter.spawn(mailbox, run_id="run-1", task_id="task-1", attempt=1,
                                  agent_id="worker-1", brief={})
        self.assertEqual(result.payload["artifact"], "draft.txt")
        self.assertEqual(dict(result.payload["question"]), {"question_id": "q-1", "prompt": "Retry?"})
        with self.assertRaises(TypeError):
            result.payload["question"]["prompt"] = "mutate"


class SpawnScriptLookupTest(unittest.TestCase):
    def test_spawn_for_an_unscripted_task_attempt_pair_is_blocked(self):
        mailbox = Mailbox()
        adapter = FakeAdapter({("task-1", 1): {"outcome": "passed"}})
        with self.assertRaises(Blocked) as ctx:
            adapter.spawn(
                mailbox, run_id="run-1", task_id="task-1", attempt=2,
                agent_id="worker-1", brief={},
            )
        self.assertEqual(ctx.exception.reason_code, "missing_target")
        # Nothing partially lands in the mailbox when the script lookup fails.
        self.assertEqual(mailbox.read_all(), ())

    def test_spawn_looks_up_by_both_task_id_and_attempt(self):
        mailbox = Mailbox()
        adapter = FakeAdapter({
            ("task-1", 1): {"outcome": "failed", "critique": "first try"},
            ("task-1", 2): {"outcome": "passed"},
        })
        _, result_1 = adapter.spawn(
            mailbox, run_id="run-1", task_id="task-1", attempt=1,
            agent_id="worker-1", brief={},
        )
        _, result_2 = adapter.spawn(
            mailbox, run_id="run-1", task_id="task-1", attempt=2,
            agent_id="worker-1", brief={},
        )
        self.assertEqual(result_1.payload["outcome"], "failed")
        self.assertEqual(result_2.payload["outcome"], "passed")

    def test_spawn_with_an_invalid_scripted_outcome_is_blocked_before_appending(self):
        mailbox = Mailbox()
        adapter = FakeAdapter({("task-1", 1): {"outcome": "bogus"}})
        with self.assertRaises(Blocked):
            adapter.spawn(
                mailbox, run_id="run-1", task_id="task-1", attempt=1,
                agent_id="worker-1", brief={},
            )
        self.assertEqual(mailbox.read_all(), ())


class ResumeSeedingTest(unittest.TestCase):
    # Outcome 2 Task 4 quality-review FIX 3 (the adapter-side half): a
    # fresh FakeAdapter used to always start its id counter at zero, so
    # resuming a persisted run with a brand-new adapter instance collided
    # with ids the reloaded mailbox already held. Passing `mailbox=` seeds
    # the counter from that mailbox's own high-water mark instead.

    def _persist_and_reload(self):
        mailbox = Mailbox()
        adapter = FakeAdapter({
            ("task-1", 1): {"outcome": "passed"},
            ("task-2", 1): {"outcome": "passed"},
        })
        adapter.spawn(mailbox, run_id="run-1", task_id="task-1", attempt=1,
                      agent_id="worker-1", brief={})
        # Mailbox now holds env-1 (request) and env-2 (result).
        return Mailbox.from_jsonl(mailbox.to_jsonl())

    def test_adapter_seeded_from_a_reloaded_mailbox_continues_the_sequence(self):
        reloaded = self._persist_and_reload()
        self.assertEqual(len(reloaded.read_all()), 2)

        resumed_adapter = FakeAdapter(
            {("task-2", 1): {"outcome": "passed"}}, mailbox=reloaded,
        )
        request, result = resumed_adapter.spawn(
            reloaded, run_id="run-1", task_id="task-2", attempt=1,
            agent_id="worker-2", brief={},
        )
        # No Blocked raised, and the sequence continued rather than
        # restarting: env-3, env-4, not env-1, env-2 again.
        self.assertEqual(request.envelope_id, "env-3")
        self.assertEqual(result.envelope_id, "env-4")
        self.assertEqual(len(reloaded.read_all()), 4)

    def test_a_fresh_adapter_without_seeding_collides_on_a_reloaded_mailbox(self):
        # The exact bug root reproduced: constructing FakeAdapter WITHOUT
        # mailbox= restarts the counter at zero, so the very first spawn
        # on the reloaded (non-empty) mailbox tries to reuse 'env-1' --
        # now caught loudly by Mailbox.append's duplicate check (FIX 3's
        # other half) instead of silently accepted.
        reloaded = self._persist_and_reload()
        unseeded_adapter = FakeAdapter({("task-2", 1): {"outcome": "passed"}})
        with self.assertRaises(Blocked) as ctx:
            unseeded_adapter.spawn(
                reloaded, run_id="run-1", task_id="task-2", attempt=1,
                agent_id="worker-2", brief={},
            )
        self.assertIn("env-1", ctx.exception.detail)

    def test_high_water_mark_ignores_ids_outside_the_env_n_scheme(self):
        mailbox = Mailbox()
        adapter = FakeAdapter({("task-1", 1): {"outcome": "passed"}})
        adapter.spawn(mailbox, run_id="run-1", task_id="task-1", attempt=1,
                      agent_id="worker-1", brief={})
        # mailbox now has env-1, env-2 -- add a differently-schemed id too.
        mailbox.append(Envelope.from_dict({
            "schema_version": 2,
            "envelope_id": "custom-id-abc",
            "run_id": "run-1",
            "sender": "orchestrator",
            "recipient": "root",
            "kind": "status",
            "payload": {"phase": "execution"},
            "created_at": "2026-01-01T00:00:03Z",
            "previous_hash": GENESIS_HASH,
        }))
        seeded = FakeAdapter({("task-2", 1): {"outcome": "passed"}}, mailbox=mailbox)
        request, result = seeded.spawn(
            mailbox, run_id="run-1", task_id="task-2", attempt=1,
            agent_id="worker-2", brief={},
        )
        # High-water mark is 2 (from env-2; 'custom-id-abc' does not match
        # the env-N scheme and is ignored), so the next ids are 3 and 4.
        self.assertEqual(request.envelope_id, "env-3")
        self.assertEqual(result.envelope_id, "env-4")


class EmitStatusTest(unittest.TestCase):
    def test_emit_status_appends_orchestrator_to_root_with_the_phase(self):
        mailbox = Mailbox()
        adapter = FakeAdapter({})
        envelope = adapter.emit_status(
            mailbox, run_id="run-1", phase="completed", context={"note": "done"},
        )
        self.assertEqual(mailbox.read_all(), (envelope,))
        self.assertEqual(envelope.kind, "status")
        self.assertEqual(envelope.sender, "orchestrator")
        self.assertEqual(envelope.recipient, "root")
        self.assertEqual(envelope.payload["phase"], "completed")
        self.assertEqual(envelope.payload["note"], "done")

    def test_emit_status_with_no_context_still_carries_the_phase(self):
        mailbox = Mailbox()
        adapter = FakeAdapter({})
        envelope = adapter.emit_status(mailbox, run_id="run-1", phase="blocked")
        self.assertEqual(envelope.payload["phase"], "blocked")

    def test_emit_status_with_an_unknown_phase_is_blocked_before_appending(self):
        mailbox = Mailbox()
        adapter = FakeAdapter({})
        with self.assertRaises(Blocked):
            adapter.emit_status(mailbox, run_id="run-1", phase="nonexistent-phase")
        self.assertEqual(mailbox.read_all(), ())


class RelayQuestionTest(unittest.TestCase):
    def test_relay_question_appends_orchestrator_to_root(self):
        mailbox = Mailbox()
        adapter = FakeAdapter({})
        decision = RetryDecision(
            action=AWAITING_USER_INPUT, task_id="task-1", attempt=1,
            critique="bad output", attempts_remaining=2,
            phase=AWAITING_USER_INPUT,
            question=freeze({"question_id": "q-1", "prompt": "which target file?"}),
        )
        # Build the approved waiting state through the real adapter methods.
        adapter = FakeAdapter({("task-1", 1): {"outcome": "failed", "critique": "bad output", "question": {"question_id": "q-1", "prompt": "which target file?"}}})
        adapter.spawn(mailbox, run_id="run-1", task_id="task-1", attempt=1, agent_id="worker-1", brief={})
        adapter.emit_status(mailbox, run_id="run-1", phase=AWAITING_USER_INPUT,
                            context={"task_id": "task-1", "attempt": 1, "critique": "bad output",
                                     "attempts_remaining": 2, "question_id": "q-1", "prompt": "which target file?"})
        envelope = adapter.relay_question(
            mailbox, run_id="run-1", decision=decision,
        )
        self.assertEqual(mailbox.read_all()[-1:], (envelope,))
        self.assertEqual(envelope.kind, "question")
        self.assertEqual(envelope.sender, "orchestrator")
        self.assertEqual(envelope.recipient, "root")
        self.assertEqual(envelope.payload["prompt"], "which target file?")

    def test_relay_question_with_an_empty_question_is_blocked_before_appending(self):
        mailbox = Mailbox()
        adapter = FakeAdapter({})
        decision = RetryDecision(action=AWAITING_USER_INPUT, task_id="task-1", attempt=1,
                                 critique="bad", attempts_remaining=2,
                                 phase=AWAITING_USER_INPUT,
                                 question=freeze({"question_id": "q-1", "prompt": "   "}))
        with self.assertRaises(Blocked):
            adapter.relay_question(mailbox, run_id="run-1", decision=decision)
        self.assertEqual(mailbox.read_all(), ())

    def test_mismatched_question_decision_is_rejected_without_append_or_counter_gap(self):
        mailbox = Mailbox()
        adapter = FakeAdapter({
            ("task-1", 1): {
                "outcome": "failed", "critique": "bad output",
                "question": {"question_id": "q-1", "prompt": "Retry?"},
            },
        })
        adapter.spawn(
            mailbox, run_id="run-1", task_id="task-1", attempt=1,
            agent_id="worker-1", brief={},
        )
        adapter.emit_status(
            mailbox, run_id="run-1", phase=AWAITING_USER_INPUT,
            context={"task_id": "task-1", "attempt": 1, "critique": "bad output",
                     "attempts_remaining": 2, "question_id": "q-1", "prompt": "Retry?"},
        )
        approved = RetryDecision(
            action=AWAITING_USER_INPUT, task_id="task-1", attempt=1,
            critique="bad output", attempts_remaining=2,
            phase=AWAITING_USER_INPUT,
            question=freeze({"question_id": "q-1", "prompt": "Retry?"}),
        )
        stale = replace(approved, question=freeze({
            "question_id": "stale", "prompt": "Retry?",
        }))
        before = mailbox.to_jsonl()
        with self.assertRaises(Blocked):
            adapter.relay_question(mailbox, run_id="run-1", decision=stale)
        with self.assertRaises(Blocked):
            adapter.relay_question(mailbox, run_id="wrong-run", decision=approved)
        self.assertEqual(mailbox.to_jsonl(), before)

        envelope = adapter.relay_question(
            mailbox, run_id="run-1", decision=approved,
        )
        self.assertEqual(envelope.envelope_id, "env-4")


class RelayAnswerTest(unittest.TestCase):
    def _waiting(self, remaining=2):
        mailbox = Mailbox()
        adapter = FakeAdapter({("task-1", 1): {"outcome": "failed", "critique": "bad output"}})
        adapter.spawn(mailbox, run_id="run-1", task_id="task-1", attempt=1,
                      agent_id="worker-1", brief={})
        adapter.emit_status(
            mailbox, run_id="run-1", phase="awaiting-user-input",
            context={"task_id": "task-1", "attempt": 1, "question_id": "q-1",
                     "attempts_remaining": remaining, "critique": "bad output",
                     "prompt": "Retry this task?"},
        )
        return mailbox, adapter

    def test_relay_answer_emits_exact_root_to_orchestrator_schema_fields(self):
        mailbox, adapter = self._waiting()
        state = reduce(mailbox.read_all())
        raw = {"run_id": "run-1", "task_id": "task-1", "attempt": 1,
               "question_id": "q-1", "decision": "retry", "text": "retry"}
        answer = adapter.relay_answer(mailbox, answer=approve_answer(state, raw))
        self.assertEqual((answer.sender, answer.recipient, answer.kind),
                         ("root", "orchestrator", "answer"))
        self.assertEqual(set(answer.payload), set(raw))
        self.assertEqual(answer.payload, raw)
        self.assertEqual(answer.previous_hash, mailbox.read_all()[-2].hash())

    def test_valid_stop_answer_has_the_same_exact_envelope_contract(self):
        mailbox, adapter = self._waiting(remaining=0)
        state = reduce(mailbox.read_all())
        raw = {"run_id": "run-1", "task_id": "task-1", "attempt": 1,
               "question_id": "q-1", "decision": "stop", "text": "stop"}
        answer = adapter.relay_answer(mailbox, answer=approve_answer(state, raw))
        self.assertEqual((answer.sender, answer.recipient, answer.kind),
                         ("root", "orchestrator", "answer"))
        self.assertEqual(answer.payload, raw)
        self.assertEqual(answer.previous_hash, mailbox.read_all()[-2].hash())

    def test_raw_and_fabricated_decisions_are_rejected_without_counter_gap(self):
        mailbox, adapter = self._waiting()
        before = mailbox.to_jsonl()
        with self.assertRaises(Blocked):
            adapter.relay_answer(mailbox, answer={})
        self.assertEqual(mailbox.to_jsonl(), before)
        state = reduce(mailbox.read_all())
        raw = {"run_id": "run-1", "task_id": "task-1", "attempt": 1,
               "question_id": "q-1", "decision": "retry", "text": "retry"}
        approved = approve_answer(state, raw)
        fabricated = AnswerDecision(**{**approved.__dict__, "phase": "blocked"})
        with self.assertRaises(Blocked):
            adapter.relay_answer(mailbox, answer=fabricated)
        self.assertEqual(mailbox.to_jsonl(), before)
        answer = adapter.relay_answer(mailbox, answer=approved)
        self.assertEqual(answer.envelope_id, "env-4")

    def test_duplicate_answer_is_rejected_without_append_or_counter_gap(self):
        mailbox, adapter = self._waiting(remaining=0)
        state = reduce(mailbox.read_all())
        raw = {"run_id": "run-1", "task_id": "task-1", "attempt": 1,
               "question_id": "q-1", "decision": "stop", "text": "stop"}
        answer = approve_answer(state, raw)
        adapter.relay_answer(mailbox, answer=answer)
        before = mailbox.to_jsonl()
        with self.assertRaises(Blocked):
            adapter.relay_answer(mailbox, answer=answer)
        self.assertEqual(mailbox.to_jsonl(), before)

    def test_fabricated_decision_fields_are_rejected_byte_identically(self):
        state_fields = {
            "phase": "blocked", "critique": "forged critique",
            "prompt": "forged prompt", "attempts_remaining": 99,
        }
        for field, value in state_fields.items():
            with self.subTest(field=field):
                mailbox, adapter = self._waiting()
                state = reduce(mailbox.read_all())
                raw = {"run_id": "run-1", "task_id": "task-1", "attempt": 1,
                       "question_id": "q-1", "decision": "retry", "text": "retry"}
                approved = approve_answer(state, raw)
                fabricated = replace(approved, **{field: value})
                before = mailbox.to_jsonl()
                with self.assertRaises(Blocked):
                    adapter.relay_answer(mailbox, answer=fabricated)
                self.assertEqual(mailbox.to_jsonl(), before)
                next_answer = adapter.relay_answer(mailbox, answer=approved)
                self.assertEqual(next_answer.envelope_id, "env-4")

        # Text is one of the six raw answer fields, so changing it is a
        # legitimate new answer decision rather than a fabricated derived
        # field; approve_answer re-derives and accepts that value.
        mailbox, adapter = self._waiting()
        state = reduce(mailbox.read_all())
        text_answer = approve_answer(state, {
            "run_id": "run-1", "task_id": "task-1", "attempt": 1,
            "question_id": "q-1", "decision": "retry", "text": "new text",
        })
        self.assertEqual(adapter.relay_answer(mailbox, answer=text_answer).payload["text"], "new text")


class EnforcePolicyTest(unittest.TestCase):
    def test_enforce_policy_returns_an_empty_disclosure_mapping(self):
        adapter = FakeAdapter({})
        result = adapter.enforce_policy(run_id="run-1", hook_name="pre-write", context={})
        self.assertEqual(result, {})

    def test_enforce_policy_never_touches_any_mailbox(self):
        # enforce_policy takes no mailbox parameter at all -- a purely
        # structural guarantee that this hook can never itself become a
        # hand-off channel.
        params = inspect.signature(FakeAdapter.enforce_policy).parameters
        self.assertNotIn("mailbox", params)


class DeterminismTest(unittest.TestCase):
    # A fake adapter must never read a real clock or any other hidden
    # source of variation: two fresh instances driven through the exact
    # same call sequence must produce byte-identical envelopes.

    def _drive(self):
        mailbox = Mailbox()
        adapter = FakeAdapter({
            ("task-1", 1): {"outcome": "failed", "critique": "off by one"},
            ("task-1", 2): {"outcome": "passed"},
        })
        adapter.spawn(mailbox, run_id="run-1", task_id="task-1", attempt=1,
                      agent_id="worker-1", brief={"critique": None})
        adapter.spawn(mailbox, run_id="run-1", task_id="task-1", attempt=2,
                      agent_id="worker-1", brief={"critique": "off by one"})
        adapter.emit_status(mailbox, run_id="run-1", phase="completed", context={})
        return mailbox

    def test_two_fresh_adapters_produce_byte_identical_mailboxes(self):
        first = self._drive()
        second = self._drive()
        self.assertEqual(first.to_jsonl(), second.to_jsonl())

    def test_ids_and_timestamps_never_come_from_a_real_clock(self):
        import fake_adapter as fake_adapter_module

        source = inspect.getsource(fake_adapter_module)
        self.assertNotIn("time.time(", source)
        self.assertNotIn("datetime.now(", source)
        self.assertNotIn("utcnow(", source)


if __name__ == "__main__":
    unittest.main()
