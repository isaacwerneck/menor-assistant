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

    def test_github_422_does_not_misdiagnose_new_report_as_duplicate(self):
        reply = Mock()
        reply.status_code = 422
        reply.headers = {"X-GitHub-Request-Id": "ABCD:1234:ZX"}
        reply.json.return_value = {"message": "Validation Failed",
                                   "errors": [{"code": "custom", "message": "Bad request"}]}
        detail = lab_publish.describe_github_rejection(reply)
        self.assertIn("rejeitou", detail)
        self.assertIn("ABCD:1234:ZX", detail)
        self.assertNotIn("já publicado", detail)

    def test_github_error_does_not_expose_token_or_untrusted_details(self):
        reply = Mock()
        reply.status_code = 422
        reply.headers = {"X-GitHub-Request-Id": "invalid value with spaces"}
        reply.json.return_value = {"message": "Validation Failed github_pat_DEMOSECRET",
                                   "errors": [{"message": "github_pat_DEMOSECRET"}]}
        detail = lab_publish.describe_github_rejection(reply)
        self.assertNotIn("github_pat_DEMOSECRET", detail)
        self.assertIn("indisponível", detail)

    def test_known_github_sha_validation_error_is_classified(self):
        reply = Mock()
        reply.status_code = 422
        reply.headers = {}
        reply.json.return_value = {"message": 'Invalid request: "sha" was not supplied.'}
        self.assertIn("SHA", lab_publish.describe_github_rejection(reply))

    def test_publish_reports_422_with_safe_error(self):
        response = Mock(status_code=422, headers={}, json=lambda: {"message": "Validation Failed"})
        reference = Mock(status_code=200)
        session = Mock()
        session.get.return_value = reference
        session.put.return_value = response
        env = {"MENOR_LAB_REPORTS_ALLOW_FULL_PUSH": "1",
               "MENOR_LAB_GITHUB_TOKEN": "github_pat_SECRET"}
        with patch.dict("os.environ", env), \
             patch.object(lab_publish.requests, "Session", return_value=session):
            with self.assertRaises(lab_publish.GitHubPublishRejected) as caught:
                lab_publish.publish_report({"run_id": "20261020T022255Z-4f73ee58"})
        self.assertNotIn("github_pat_SECRET", str(caught.exception))
        self.assertNotIn("já publicado", str(caught.exception))
        self.assertTrue(session.put.called)

    def test_route_maps_rejection_to_502_without_leaking_upstream_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            run_id = "20261020T022255Z-4f73ee58"
            Path(directory, run_id + ".json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
            with patch.object(lab_batches, "DATA", Path(directory)), \
                 patch.object(lab_batches_routes.auth, "require_owner"), \
                 patch.object(lab_publish, "publish_report",
                              side_effect=lab_publish.GitHubPublishRejected("GitHub recusou a gravação.")):
                with self.assertRaises(HTTPException) as caught:
                    lab_batches_routes.batch_publish(run_id, Mock())
        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(caught.exception.detail, "GitHub recusou a gravação.")

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
