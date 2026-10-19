"""End-to-end ASGI for private file upload, inspection, auth and deletion."""
import asyncio
import io
import json
import os
import tempfile
import unittest
from urllib.parse import quote
from unittest.mock import patch

from PIL import Image

from src.api import main
from src.security import auth
from src.tools.file_analysis.contracts import FileRejected, MAX_BYTES
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
        try:
            decoded = json.loads(payload) if payload else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            decoded = payload.decode("utf-8", errors="replace")
        return status, decoded

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

    def test_private_inspector_page_and_assets(self):
        self.assertEqual(request("GET", "/files/view")[0], 401)
        self.assertEqual(request("GET", "/files/assets.js")[0], 401)
        self.assertEqual(request("GET", "/files/assets.css")[0], 401)
        self.assertEqual(request("GET", "/files/view", cookie=self.cookie)[0], 200)
        self.assertEqual(request("GET", "/files/assets.js", cookie=self.cookie)[0], 200)
        self.assertEqual(request("GET", "/files/assets.css", cookie=self.cookie)[0], 200)

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

    def test_file_context_finds_real_text_with_source_and_without_model(self):
        status, saved = request("POST", "/files/upload?filename=relatorio.md",
                                b"Projeto Menor\nPrazo de entrega: sexta-feira.", cookie=self.cookie)
        self.assertEqual(status, 201, saved)
        token = saved["file"]["file_id"]
        target = "/files/" + token + "/context"
        payload = json.dumps({"question": "Qual e o prazo de entrega?"}).encode()
        self.assertEqual(request("POST", target, payload, content_type="application/json")[0], 401)
        self.assertEqual(request("POST", target, payload, cookie=self.cookie,
                                 origin="https://evil.example")[0], 403)
        code, result = request("POST", target, payload, cookie=self.cookie,
                               content_type="application/json")
        self.assertEqual(code, 200, result)
        self.assertEqual(result["status"], "executed")
        self.assertTrue(result["grounded"])
        self.assertIn("sexta-feira", result["items"][0]["text"])
        self.assertIn(token, result["items"][0]["citation"])
        self.assertIn("não confiáveis", result["limitations"][1])
        self.assertNotIn("answer", result)

    def test_context_validation_no_text_and_invalid_id(self):
        status, saved = request("POST", "/files/upload?filename=nota.txt",
                                b"conteudo", cookie=self.cookie)
        self.assertEqual(status, 201, saved)
        uri = "/files/" + saved["file"]["file_id"] + "/context"
        self.assertEqual(request("POST", uri, b'{"question":""}', cookie=self.cookie,
                                 content_type="application/json")[0], 422)
        self.assertEqual(request("POST", uri, b'{"question":"   "}', cookie=self.cookie,
                                 content_type="application/json")[0], 422)
        self.assertEqual(request("POST", uri, b'{"question":"um teste"}',
                                 cookie=self.cookie, content_type="application/json")[0], 200)
        self.assertEqual(request("POST", "/files/invalid/context", b'{"question":"x"}',
                                 cookie=self.cookie, content_type="application/json")[0], 404)

    def _png_file(self):
        buf = io.BytesIO()
        Image.new("RGB", (32, 32), "purple").save(buf, "PNG")
        status, saved = request("POST", "/files/upload?filename=sprite.png",
                                buf.getvalue(), cookie=self.cookie)
        self.assertEqual(status, 201, saved)
        return saved["file"]["file_id"]

    def test_vision_status_protected_and_absence_is_not_success(self):
        self.assertEqual(request("GET", "/files/vision/status")[0], 401)
        with patch.dict(os.environ, {"MENOR_VISION_MODEL": ""}):
            code, state = request("GET", "/files/vision/status", cookie=self.cookie)
            self.assertEqual(code, 200)
            self.assertEqual(state["status"], "not_configured")
            token = self._png_file()
            uri = "/files/" + token + "/vision"
            question = b'{"question":"Qual cor?"}'
            code, outcome = request("POST", uri, question, cookie=self.cookie,
                                    content_type="application/json")
            self.assertEqual(code, 503)
            self.assertEqual(outcome["status"], "unavailable")
            self.assertFalse(outcome["content_verified"])

    def test_vision_through_api_uses_only_local_mock_and_marks_unverified(self):
        token = self._png_file()
        target = "/files/" + token + "/vision"
        question = b'{"question":"Qual cor aparece?"}'
        import unittest.mock as mocking
        get_response = mocking.MagicMock()
        get_response.json.return_value = {"models": [{"name": "qwen2.5vl:3b"}]}
        post_response = mocking.MagicMock()
        post_response.__enter__.return_value = post_response
        post_response.json.return_value = {"message": {"content": json.dumps({
            "observations": ["Uma região roxa."], "inferences": [],
            "answer": "Roxa.", "uncertainty": "Não há evidência de um personagem.",
        })}}
        with patch.dict(os.environ, {"MENOR_VISION_MODEL": "qwen2.5vl:3b",
                                     "OLLAMA_URL": "http://127.0.0.1:11434"}):
            with patch("src.tools.vision.requests.get", return_value=get_response):
                with patch("src.tools.vision.requests.post", return_value=post_response) as post:
                    self.assertEqual(request("POST", target, question,
                                             content_type="application/json")[0], 401)
                    self.assertEqual(request("POST", target, question, cookie=self.cookie,
                                             origin="https://evil.example",
                                             content_type="application/json")[0], 403)
                    code, body = request("POST", target, question, cookie=self.cookie,
                                         content_type="application/json")
        self.assertEqual(code, 200, body)
        self.assertEqual(body["status"], "executed")
        self.assertFalse(body["validation"]["semantic_verified"])
        self.assertEqual(body["evidence"][0]["dimensions"], [32, 32])
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:11434/api/chat")

    def test_vision_rejects_documents_even_with_installed_model(self):
        status, stored = request("POST", "/files/upload?filename=a.txt",
                                 b"texto", cookie=self.cookie)
        self.assertEqual(status, 201, stored)
        target = "/files/" + stored["file"]["file_id"] + "/vision"
        with patch("src.tools.file_analysis.api.vision.inspect_image", side_effect=FileRejected("not image")):
            code, _ = request("POST", target, b'{"question":"Explique"}',
                              cookie=self.cookie, content_type="application/json")
        self.assertEqual(code, 422)


if __name__ == "__main__":
    unittest.main()
