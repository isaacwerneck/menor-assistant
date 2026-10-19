"""Testes estruturais de transições sem tocar em tarefas reais."""
import json
import unittest

from ops.execution_transitions import audit_sequence, audit_transition


def event(status, **extra):
    result = {"status": status, "mission_id": "m1", "action_id": "a1",
              "idempotency_key": "key1"}
    result.update(extra)
    return result


class ExecutionTransitionTests(unittest.TestCase):
    def test_happy_path(self):
        states = ("planned", "awaiting_approval", "queued", "running",
                  "executed", "verified")
        result = audit_sequence([event(state) for state in states])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["checked"], 5)

    def test_no_replay_after_terminal_states(self):
        for old in ("executed", "failed", "interrupted", "verified"):
            with self.subTest(old=old):
                result = audit_transition(event(old), event("running"))
                self.assertEqual(result["reason"], "invalid_transition")

    def test_cannot_skip_required_stages(self):
        self.assertEqual(audit_transition(event("planned"), event("executed"))
                         ["status"], "critical")

    def test_identity_binding(self):
        for field in ("mission_id", "action_id", "idempotency_key"):
            with self.subTest(field=field):
                self.assertEqual(audit_transition(event("queued"),
                                 event("running", **{field: "other"}))
                                 ["reason"], "identity_mismatch")

    def test_duplicates_not_success(self):
        self.assertEqual(audit_transition(event("running"), event("running"))
                         ["status"], "warning")

    def test_secret_not_reflected(self):
        secret = "PRIVATE_TOKEN_HOME_PATH"
        result = audit_transition(event("running", detail=secret),
                                  event("executed", detail=secret))
        self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(result["status"], "ok")

    def test_invalid_records_fail_closed(self):
        for value in (None, [], {}, event("bogus"), event("running", mission_id=None)):
            with self.subTest(value=value):
                self.assertEqual(audit_transition(value, event("running"))
                                 ["status"], "critical")

    def test_bounded_history(self):
        self.assertEqual(audit_sequence([])["status"], "unknown")
        self.assertEqual(audit_sequence([event("queued")] * 65)["status"], "unknown")
        self.assertEqual(audit_sequence([event("queued"), event("running"),
                                         event("executed")])["checked"], 2)


if __name__ == "__main__":
    unittest.main()
