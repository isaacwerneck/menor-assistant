"""Regressões de evidência: sequência, identidade, limites e digest."""
import json
import unittest

from ops.execution_evidence import verify_evidence, verify_json_envelope
from ops.execution_integrity import audit_runs
from ops.execution_transitions import audit_transition


def event(status, seq=0, **updates):
    record = {"status": status, "sequence": seq, "mission_id": "m",
              "action_id": "a", "idempotency_key": "k"}
    record.update(updates)
    return record


class EvidenceTests(unittest.TestCase):
    def test_valid_sequence_is_not_trusted(self):
        result = verify_evidence([event("planned"), event("queued", 1),
                                  event("running", 2), event("executed", 3)])
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["trusted"])
        self.assertFalse(result["safe_to_retry"])
        self.assertEqual(result["recovery"], "do_not_replay")

    def test_digest_detects_mutation(self):
        events = [event("planned")]
        digest = verify_evidence(events)["last_digest"]
        self.assertEqual(verify_evidence(events, expected_digest=digest)["status"], "unknown")
        self.assertEqual(verify_evidence([event("queued")], expected_digest=digest)
                         ["reason"], "digest_mismatch")

    def test_sequence_gap_and_duplicate(self):
        for sequence in (0, 2):
            self.assertEqual(verify_evidence([event("planned"),
                                              event("queued", sequence)])
                             ["reason"], "sequence_gap")

    def test_identity_change(self):
        self.assertEqual(verify_evidence([event("planned"),
                                          event("queued", 1, action_id="other")])
                         ["reason"], "identity_mismatch")

    def test_invalid_transitions(self):
        self.assertEqual(verify_evidence([event("planned"), event("verified", 1)])
                         ["reason"], "invalid_transition")

    def test_envelope_bounds_and_shape(self):
        for raw in (b"", b"[]", b'{"events":[]}', b'{"events":[],"secret":1}',
                    b"x" * 65537, "not bytes"):
            with self.subTest(raw_type=type(raw).__name__):
                self.assertEqual(verify_json_envelope(raw)["status"], "critical")

    def test_json_valid(self):
        raw = json.dumps({"events": [event("planned")]}).encode()
        self.assertEqual(verify_json_envelope(raw)["status"], "unknown")

    def test_secret_not_echoed(self):
        secret = "SECRET_/home/private/token"
        record = event("planned", mission_id=secret, prompt=secret)
        result = verify_evidence([record])
        self.assertNotIn(secret, json.dumps(result))

    def test_intermediate_invalid_event_cannot_be_ignored(self):
        records = [event("planned"), event("queued", 1), event("running", 2)]
        records[1]["mission_id"] = None
        self.assertEqual(audit_runs([records])["status"], "critical")

    def test_empty_batch_unknown_not_success(self):
        self.assertEqual(audit_runs([])["status"], "unknown")

    def test_transition_invalid_state_type(self):
        self.assertEqual(audit_transition(event("planned"),
                                          event(["queued"], 1))["status"], "critical")

    def test_missing_sequence(self):
        record = event("planned")
        del record["sequence"]
        self.assertEqual(verify_evidence([record])["reason"], "invalid_evidence")


if __name__ == "__main__":
    unittest.main()
