"""Contrato de compatibilidade entre recibos de imagem e evidência limitada."""
import json
import unittest

from src.agent.intelligence import _bounded_evidence


class EvidenceCompatibilityTests(unittest.TestCase):
    def test_image_identity_and_dimensions_survive(self):
        receipt = {"kind": "image", "id": "a" * 32, "actual_size": [32, 32]}
        self.assertEqual(_bounded_evidence(receipt), receipt)

    def test_full_image_receipt_keeps_proof_without_raw_prompt(self):
        receipt = {"kind": "image", "id": "a" * 32, "url": "/images/id",
                   "actual_size": [512, 512], "file_verified": True,
                   "content_verified": False, "prompt": "SECRET" * 1000,
                   "content_description": "PRIVATE" * 1000}
        bounded = _bounded_evidence(receipt)
        self.assertTrue(bounded["file_verified"])
        self.assertFalse(bounded["content_verified"])
        self.assertNotIn("SECRET", json.dumps(bounded))
        self.assertNotIn("PRIVATE", json.dumps(bounded))

    def test_invalid_dimensions_are_excluded(self):
        self.assertEqual(_bounded_evidence({"kind": "image", "actual_size": [1, "bad"]}),
                         {"kind": "image"})

    def test_large_metadata_never_exceeds_budget(self):
        receipt = {name: "x" * 100000 for name in
                   ("tool", "status", "source", "citation", "summary", "excerpt",
                    "kind", "id", "worker", "limitation")}
        self.assertLessEqual(len(json.dumps(_bounded_evidence(receipt), ensure_ascii=False)), 2400)


if __name__ == "__main__":
    unittest.main()
