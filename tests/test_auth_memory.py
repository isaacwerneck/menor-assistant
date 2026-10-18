import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src.api import main
from src.memory.store import BrainStore
from src.security import auth


def call(path, body=None, cookie=None, origin="http://localhost:8000", client="192.168.0.8"):
    async def run():
        sent = []
        raw = json.dumps(body).encode() if body is not None else b""
        headers = [(b"host", b"localhost:8000"), (b"content-type", b"application/json")]
        if origin is not None:
            headers.append((b"origin", origin.encode()))
        if cookie:
            headers.append((b"cookie", cookie.encode()))

        async def receive():
            return {"type": "http.request", "body": raw, "more_body": False}

        async def send(value):
            sent.append(value)

        await main.app({
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1", "method": "POST" if body is not None else "GET",
            "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"",
            "scheme": "http", "headers": headers, "client": (client, 3211),
            "server": ("localhost", 8000),
        }, receive, send)
        reply = sent[0]
        return reply["status"], json.loads(b"".join(e.get("body", b"") for e in sent[1:])), dict(reply["headers"])

    return asyncio.run(run())


class MemoryChatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        settings = patch.dict(os.environ, {"MENOR_DATA_DIR": self.temp.name})
        settings.start()
        self.addCleanup(settings.stop)
        auth._attempts.clear()
        self.password = "senha-longa-para-o-menor"

    def _setup(self):
        code, reply, headers = call("/auth/setup", {"password": self.password})
        self.assertEqual(code, 200, reply)
        self.assertIn(b"set-cookie", headers)
        self.assertIn("httponly", headers[b"set-cookie"].decode().lower())
        return headers[b"set-cookie"].decode().split(";", 1)[0]

    def test_first_use_setup_private_only_and_password_strength(self):
        status, reply, _ = call("/auth/status")
        self.assertEqual(status, 200)
        self.assertFalse(reply["configured"])
        self.assertEqual(call("/auth/setup", {"password": self.password}, client="8.8.8.8")[0], 403)
        self.assertEqual(call("/auth/setup", {"password": "curta"})[0], 422)
        self.assertEqual(call("/auth/setup", {"password": self.password}, origin="https://evil.example")[0], 403)
        cookie = self._setup()
        self.assertEqual(call("/auth/setup", {"password": self.password})[0], 409)
        self.assertTrue(call("/auth/status", cookie=cookie)[1]["authenticated"])
        self.assertEqual((BrainStore().data_dir / "owner.json").stat().st_mode & 0o777, 0o600)
        settings = (BrainStore().data_dir / "owner.json").read_text(encoding="utf-8")
        self.assertNotIn(self.password, settings)

    def test_memory_needs_cookie_and_origin_and_does_not_overwrite(self):
        self.assertEqual(call("/memory/remember", {"text": "Use respostas curtas", "kind": "preference"})[0], 401)
        cookie = self._setup()
        payload = {"text": "Use respostas curtas", "kind": "preference"}
        self.assertEqual(call("/memory/remember", payload, cookie=cookie, origin="http://evil.test")[0], 403)
        self.assertEqual(call("/memory/remember", payload, cookie=cookie)[0], 200)
        self.assertEqual(call("/memory/remember", payload, cookie=cookie)[0], 200)
        self.assertEqual(BrainStore().preference_context(), "- Use respostas curtas")
        knowledge = {"text": "O jogo utiliza sprites pixelados", "kind": "knowledge"}
        self.assertEqual(call("/memory/remember", knowledge, cookie=cookie)[0], 200)
        self.assertIn("sprites pixelados", BrainStore().read_note("conhecimentos/aprendizados_gerais.md"))
        self.assertNotIn("sprites pixelados", BrainStore().preference_context())
        self.assertIn("Use respostas curtas", main.prompt_with_preferences())
        self.assertEqual(call("/memory/preferences", cookie=cookie)[0], 200)

    def test_chat_is_protected_after_first_owner_setup(self):
        self._setup()
        self.assertEqual(call("/chat", {"message": "oi"})[0], 401)
        self.assertEqual(call("/chat/stream", {"message": "oi"})[0], 401)
        self.assertEqual(call("/models")[0], 401)

    def test_wrong_password_and_rate_limit(self):
        self._setup()
        for _ in range(5):
            self.assertEqual(call("/auth/login", {"password": "incorreta"})[0], 401)
        self.assertEqual(call("/auth/login", {"password": self.password})[0], 429)
        auth._attempts.clear()
        status, result, headers = call("/auth/login", {"password": self.password})
        self.assertEqual(status, 200, result)
        self.assertIn(b"set-cookie", headers)
        cookie = headers[b"set-cookie"].decode().split(";", 1)[0]
        self.assertTrue(call("/auth/status", cookie=cookie)[1]["authenticated"])

    def test_cookie_signature_is_verified(self):
        cookie = self._setup()
        self.assertTrue(call("/auth/status", cookie=cookie)[1]["authenticated"])
        forged = cookie[:-5] + "XXXXX"
        self.assertFalse(call("/auth/status", cookie=forged)[1]["authenticated"])
        self.assertEqual(call("/memory/preferences", cookie=forged)[0], 401)


if __name__ == "__main__":
    unittest.main()
