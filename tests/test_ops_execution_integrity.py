"""Regressões de integridade de trilhas: fail-closed, privacidade e limites."""
import json
import unittest

from ops.execution_integrity import audit_runs


def trace(*states, mission="mission", action="action", key="key"):
    return [{"status": state, "mission_id": mission,
             "action_id": action, "idempotency_key": key} for state in states]


class ExecutionIntegrityTests(unittest.TestCase):
    def test_valid_trace_is_structural_only(self):
        result = audit_runs([trace("planned", "queued", "running", "executed")])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["findings"]["terminal_unverified"], "1-9")

    def test_uncertain_outcome_needs_reconciliation(self):
        result = audit_runs([trace("planned", "queued", "running", "interrupted")])
        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["findings"]["needs_reconciliation"], "1-9")

    def test_invalid_transition_is_critical(self):
        result = audit_runs([trace("planned", "executed")])
        self.assertEqual(result["status"], "critical")
        self.assertIn("invalid_transition", result["findings"])

    def test_idempotency_collision_detected(self):
        result = audit_runs([trace("planned", "queued", action="a", key="same"),
                             trace("planned", "queued", action="b", key="same")])
        self.assertEqual(result["status"], "critical")
        self.assertEqual(result["findings"]["idempotency_collision"], "1-9")

    def test_same_action_key_is_not_collision(self):
        result = audit_runs([trace("planned", "queued"),
                             trace("planned", "queued")])
        self.assertNotIn("idempotency_collision", result["findings"])

    def test_identity_change_inside_trace_detected(self):
        events = trace("planned", "queued")
        events[1]["mission_id"] = "different"
        result = audit_runs([events])
        self.assertEqual(result["status"], "critical")
        self.assertIn("identity_mismatch", result["findings"])

    def test_invalid_batch_is_unknown(self):
        for runs in (None, {}, [None], [trace("planned")] * 129):
            with self.subTest(runs_type=type(runs).__name__):
                result = audit_runs(runs)
                self.assertIn(result["status"], ("unknown", "critical"))

    def test_trace_limit_enforced(self):
        self.assertEqual(audit_runs([trace(*(["queued"] * 65))])["status"], "critical")

    def test_no_secret_in_output(self):
        secret = "PRIVATE_SECRET_/home/owner/token"
        events = trace("planned", "queued", mission=secret, key=secret)
        events[0]["prompt"] = secret
        result = audit_runs([events])
        self.assertNotIn(secret, json.dumps(result))

    def test_count_bands_not_exact_numbers(self):
        runs = [trace("running", key=str(index)) for index in range(12)]
        result = audit_runs(runs)
        self.assertEqual(result["runs"], "10-49")
        self.assertEqual(result["findings"]["needs_reconciliation"], "10-49")

    def test_awaiting_approval_never_reported_as_success(self):
        result = audit_runs([trace("planned", "awaiting_approval")])
        self.assertEqual(result["status"], "warning")

    def test_single_valid_event_is_not_proof(self):
        result = audit_runs([trace("planned")])
        self.assertEqual(result["status"], "unknown")
        self.assertIn("insufficient_history", result["findings"])


if __name__ == "__main__":
    unittest.main()
