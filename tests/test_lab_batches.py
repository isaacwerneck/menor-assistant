"""Testes sem inferência real para a gaveta de avaliação."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from src.api import lab_batches
from src.api import lab_batches_routes


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patcher = patch.object(lab_batches, "DATA", Path(self.temp.name))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_builtin_suite(self):
        suite = lab_batches.load_suite("diagnostico-inicial")
        self.assertGreaterEqual(len(suite["cases"]), 4)

    def test_duplicate_ids_rejected(self):
        case = {"id": "same", "mode": "direct", "message": "Oi"}
        with self.assertRaises(ValueError):
            lab_batches.validate_suite({"id": "my-suite", "cases": [case, case]})

    def test_import_kept_outside_checkout(self):
        suite = {"id": "minha-suite", "cases": [
            {"id": "c1", "mode": "direct", "message": "Oi"}]}
        raw = json.dumps(suite).encode()
        self.assertEqual(lab_batches.save_suite(raw), "minha-suite")
        self.assertTrue((Path(self.temp.name) / "suites" / "minha-suite.json").exists())

    def test_report_id_path_traversal(self):
        with self.assertRaises(ValueError):
            lab_batches.report_path("../../etc/passwd")

    def test_routes_require_auth(self):
        with patch.object(lab_batches_routes.auth, "require_owner",
                          side_effect=HTTPException(401, "Unauthorized")):
            for endpoint in (lab_batches_routes.list_batches, lab_batches_routes.batch_reports):
                with self.assertRaises(HTTPException) as caught:
                    endpoint(None)
                self.assertEqual(caught.exception.status_code, 401)
            with self.assertRaises(HTTPException) as caught:
                lab_batches_routes.run_batch("diagnostico-inicial", None)
            self.assertEqual(caught.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
