"""ASGI security contract for owner-only OCR contextual retrieval."""
import json
import unittest
from unittest.mock import patch

from test_file_api import FileRoutesTests, request


class ContextOcrApiTests(unittest.TestCase):
    setUp = FileRoutesTests.setUp

    def test_explicit_ocr_parameters_and_owner_boundary(self):
        saved_status, saved = request("POST", "/files/upload?filename=nota.txt",
                                      b"Nota privada", cookie=self.cookie)
        self.assertEqual(saved_status, 201)
        file_id = saved["file"]["file_id"]
        target = f"/files/{file_id}/context"
        body = json.dumps({"question": "Prazo", "ocr_page": 1, "ocr_language": "por"}).encode()
        with patch("src.tools.file_analysis.api.retrieve_context") as retrieve:
            retrieve.return_value = {"tool": "files.context", "status": "no_text",
                                     "grounded": False, "items": []}
            self.assertEqual(request("POST", target, body, content_type="application/json")[0], 401)
            self.assertEqual(request("POST", target, body, cookie=self.cookie,
                                     origin="https://evil.example",
                                     content_type="application/json")[0], 403)
            self.assertEqual(retrieve.call_count, 0)
            code, result = request("POST", target, body, cookie=self.cookie,
                                   content_type="application/json")
            self.assertEqual(code, 200, result)
            self.assertEqual(retrieve.call_count, 1)
            self.assertEqual(retrieve.call_args.kwargs["ocr_page"], 1)
            self.assertEqual(retrieve.call_args.kwargs["ocr_language"], "por")

    def test_ocr_is_off_by_default_and_rejects_implicit_values(self):
        status, saved = request("POST", "/files/upload?filename=nota.txt",
                                b"Nota privada", cookie=self.cookie)
        self.assertEqual(status, 201)
        target = f"/files/{saved['file']['file_id']}/context"
        with patch("src.tools.file_analysis.api.retrieve_context") as retrieve:
            retrieve.return_value = {"tool": "files.context", "status": "no_text",
                                     "grounded": False, "items": []}
            code, _ = request("POST", target, b'{"question":"Prazo"}',
                              cookie=self.cookie, content_type="application/json")
            self.assertEqual(code, 200)
            self.assertIsNone(retrieve.call_args.kwargs["ocr_page"])
            for page in (True, 0, 41, "1", -1):
                payload = json.dumps({"question": "Prazo", "ocr_page": page}).encode()
                self.assertEqual(request("POST", target, payload, cookie=self.cookie,
                                         content_type="application/json")[0], 422)
            self.assertEqual(retrieve.call_count, 1)

    def test_ocr_unavailable_is_http_503(self):
        status, saved = request("POST", "/files/upload?filename=nota.txt",
                                b"Nota privada", cookie=self.cookie)
        self.assertEqual(status, 201)
        target = f"/files/{saved['file']['file_id']}/context"
        unavailable = {"tool": "files.context", "status": "ocr_unavailable",
                       "grounded": False, "items": []}
        with patch("src.tools.file_analysis.api.retrieve_context", return_value=unavailable):
            code, result = request("POST", target,
                                   b'{"question":"Prazo","ocr_page":1}',
                                   cookie=self.cookie, content_type="application/json")
        self.assertEqual(code, 503, result)
        self.assertFalse(result["grounded"])


if __name__ == "__main__":
    unittest.main()
