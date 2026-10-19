"""Regressões de recuperação: nenhuma repetição implícita de efeitos."""
import json
import unittest

from ops.recovery_decision import recovery_decision


def item(status="planned", **changes):
    value = {"status": status, "mission_id": "m1",
             "action_id": "a1", "idempotency_key": "k1"}
    value.update(changes)
    return value


class RecoveryDecisionTests(unittest.TestCase):
    def test_no_state_automatically_authorizes_replay(self):
        for status in ("planned", "awaiting_approval", "queued", "running",
                       "executed", "failed", "interrupted", "verified"):
            with self.subTest(status=status):
                decision = recovery_decision(item(status))
                self.assertFalse(decision["safe_to_retry"])
                self.assertNotIn("execute", decision["decision"])
                json.dumps(decision)

    def test_uncertain_requires_reconciliation(self):
        for status in ("running", "interrupted"):
            self.assertEqual(recovery_decision(item(status))["decision"], "reconcile")

    def test_terminal_never_replays_even_if_requested_state_is_planned(self):
        for status in ("executed", "verified"):
            result = recovery_decision(item(), persisted=item(status))
            self.assertEqual(result["decision"], "do_not_replay")

    def test_persisted_uncertainty_dominates_proposed_retry(self):
        result = recovery_decision(item("planned"), persisted=item("running"))
        self.assertEqual(result["decision"], "reconcile")

    def test_identity_mismatch_fails_closed(self):
        for field in ("mission_id", "action_id", "idempotency_key"):
            with self.subTest(field=field):
                prior = item()
                prior[field] = "different"
                result = recovery_decision(item(), persisted=prior)
                self.assertEqual(result["reason"], "identity_mismatch")
                self.assertFalse(result["safe_to_retry"])

    def test_invalid_data_never_leaks_raw_fields(self):
        secret = "SECRET_private_path_/home/user/token"
        for record in (None, [], {}, item("invalid"),
                       item(mission_id=secret * 10), item(idempotency_key=None)):
            result = recovery_decision(record)
            self.assertEqual(result["decision"], "manual_review")
            self.assertNotIn(secret, json.dumps(result))

    def test_failed_does_not_automatically_retry(self):
        self.assertEqual(recovery_decision(item("failed"))["decision"], "manual_review")

    def test_queue_and_approval_remain_non_executable(self):
        self.assertEqual(recovery_decision(item("queued"))["decision"], "check_queue")
        self.assertEqual(recovery_decision(item("awaiting_approval"))["decision"],
                         "await_approval")


if __name__ == "__main__":
    unittest.main()
