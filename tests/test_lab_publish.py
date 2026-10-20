"""Testes de autorização e publicação manual de relatórios."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException

from src.api import lab_batches, lab_batches_routes, lab_publish


class PublishTests(unittest.TestCase):
    def test_feature_off(self):
        with patch.dict("os.environ", {"MENOR_LAB_REPORTS_ALLOW_FULL_PUSH": "0"}):
            with self.assertRaises(RuntimeError):
                lab_publish.publish_report({"run_id": "test"})

    def test_requires_owner(self):
        with patch.object(lab_batches_routes.auth, "require_owner",
                          side_effect=HTTPException(401, "Unauthorized")):
            with self.assertRaises(HTTPException) as caught:
                lab_batches_routes.batch_publish("20261019T010101Z-1234abcd", Mock())
            self.assertEqual(caught.exception.status_code, 401)

    def test_publish_saved_report(self):
        with tempfile.TemporaryDirectory() as directory:
            run_id = "20261019T010101Z-1234abcd"
            report = {"run_id": run_id, "cases": [{"question": "Oi", "result": {"reply": "Olá"}}]}
            Path(directory, run_id + ".json").write_text(json.dumps(report), encoding="utf-8")
            with patch.object(lab_batches, "DATA", Path(directory)), \
                 patch.object(lab_batches_routes.auth, "require_owner"), \
                 patch.object(lab_publish, "publish_report", return_value="https://example.test/report") as push:
                result = lab_batches_routes.batch_publish(run_id, Mock())
            self.assertEqual(result["url"], "https://example.test/report")
            push.assert_called_once_with(report)


if __name__ == "__main__":
    unittest.main()
