"""End-to-end ASGI for private file upload, inspection, auth and deletion."""
import asyncio
import json
import os
import tempfile
import unittest
from urllib.parse import quote
from unittest.mock import patch

from src.api import main
from src.security import auth
from src.tools.file_analysis.contracts import MAX_BYTES
from test_auth_memory import call


def request(method, path, raw=b"", cookie=None, origin="http://localhost:8000",
            content_type="application/octet-stream", headers_extra=None):
    async def invoke():
        sent = []
        received = False
        headers = [(b"host", b"localhost:8000")]
        if content_type is not None:
            headers.append((b"content-type", content_type.encode()))
        if cookie:
            headers.append((b"cookie", cookie.encode()))
        if origin is not None:
            headers.append((b"origin", origin.encode()))
        if headers_extra:
            headers.extend((name.encode(), value.encode()) for name, value in headers_extra.items())

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": raw, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        clean_path, _, query = path.partition("?")
        await main.app({
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1", "method": method,
            "path": clean_path, "raw_path": clean_path.encode(),
            "root_path": "", "query_string": query.encode("utf-8"), "scheme": "http",
            "headers": headers, "client": ("192.168.1.8", 5678),
            "server": ("localhost", 8000),
        }, receive, send)
        status = sent[0]["status"]
        payload = b"".join(m.get("body", b"") for m in sent[1:])
        return status, json.loads(payload) if payload else None

    return asyncio.run(invoke())


class FileRoutesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = temp.name
        settings = patch.dict(os.environ, {"MENOR_DATA_DIR": self.root})
        settings.start()
        self.addCleanup(settings.stop)
        auth._attempts.clear()
        status, _, headers = call("/auth/setup", {"password": "teste-seguro-muitos-caracteres"})
        self.assertEqual(status, 200)
        self.cookie = headers[b"set-cookie"].decode().split(";", 1)[0]

    def test_unauthenticated_and_origin_check_precedes_file_reading(self):
        path = "/files/upload?filename=nota.txt"
        self.assertEqual(request("POST", path, b"secret")[0], 401)
        self.assertEqual(request("GET", "/files/capabilities")[0], 401)
        self.assertEqual(request("POST", path, b"secret", cookie=self.cookie,
                                 origin="https://outside.example")[0], 403)
        self.assertEqual(request("DELETE", "/files/" + "a" * 32)[0], 401)

    def test_upload_inspect_delete_and_no_external_paths(self):
        name = quote("notas do usuário.md")
        status, saved = request("POST", f"/files/upload?filename={name}",
                                "Minha nota privada".encode(), cookie=self.cookie)
        self.assertEqual(status, 201, saved)
        token = saved["file"]["file_id"]
        self.assertRegex(token, r"^[0-9a-f]{32}$")
        status, result = request("GET", "/files/" + token, cookie=self.cookie)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["content"][0]["text"], "Minha nota privada")
        self.assertFalse(result["validation"]["semantic_verified"])
        self.assertEqual(request("GET", "/files/" + token)[0], 401)
        status, gone = request("DELETE", "/files/" + token, cookie=self.cookie)
        self.assertEqual(status, 200, gone)
        self.assertEqual(gone["state"], "deleted")
        self.assertEqual(request("GET", "/files/" + token, cookie=self.cookie)[0], 404)
        self.assertEqual(request("GET", "/files/../../etc/passwd", cookie=self.cookie)[0], 404)

    def test_reject_bad_file_and_mime_without_storing(self):
        path = "/files/upload?filename=imagem.png"
        code, _ = request("POST", path, b"fake image", cookie=self.cookie)
        self.assertEqual(code, 422)
        self.assertEqual(request("POST", "/files/upload?filename=doc.exe",
                                 b"example", cookie=self.cookie)[0], 422)
        self.assertEqual(request("POST", path, b"image", cookie=self.cookie,
                                 content_type="text/plain")[0], 415)

    def test_streamed_body_limit_and_declared_size_limit(self):
        path = "/files/upload?filename=nota.txt"
        huge = b"a" * (MAX_BYTES + 1)
        self.assertEqual(request("POST", path, b"tiny", cookie=self.cookie,
                                 headers_extra={"content-length": str(MAX_BYTES + 1)})[0], 413)
        self.assertEqual(request("POST", path, huge, cookie=self.cookie)[0], 413)

    def test_capabilities_are_grounded_and_require_auth(self):
        status, data = request("GET", "/files/capabilities", cookie=self.cookie)
        self.assertEqual(status, 200, data)
        self.assertEqual(data["name"], "files.inspect")
        self.assertEqual(data["visual_understanding"], "not_integrated")
        self.assertIn("xlsx", data["formats"])

    def test_unknown_or_corrupted_id_is_not_returned_as_document(self):
        self.assertEqual(request("GET", "/files/" + "b" * 32, cookie=self.cookie)[0], 404)
        status, saved = request("POST", "/files/upload?filename=nota.txt", b"hello",
                                cookie=self.cookie)
        self.assertEqual(status, 201, saved)
        token = saved["file"]["file_id"]
        path = os.path.join(self.root, "media", "file_analysis", token + ".blob")
        with open(path, "wb") as output:
            output.write(b"altered")
        self.assertEqual(request("GET", "/files/" + token, cookie=self.cookie)[0], 404)
        self.assertEqual(request("DELETE", "/files/" + token, cookie=self.cookie)[0], 404)


if __name__ == "__main__":
    unittest.main()
