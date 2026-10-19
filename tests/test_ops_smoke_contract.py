"""Contratos ASGI reais, executados com armazenamento temporário e sem rede.

Garante que mudanças futuras no roteamento não exponham rotas do proprietário.
"""

import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from ops.smoke import PRIVATE_GET, _health_contract
from src.api import main as api


def asgi_get(path):
    async def run():
        events = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(event):
            events.append(event)

        await api.app({
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1", "method": "GET", "path": path,
            "raw_path": path.encode(), "root_path": "", "query_string": b"",
            "scheme": "http", "headers": [(b"host", b"localhost:8000")],
            "client": ("127.0.0.1", 2345), "server": ("localhost", 8000),
        }, receive, send)
        status = next(event["status"] for event in events if event["type"] == "http.response.start")
        body = b"".join(event.get("body", b"") for event in events if event["type"] == "http.response.body")
        return status, body

    return asyncio.run(run())


class ASGIContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings = patch.dict(os.environ, {"MENOR_DATA_DIR": temporary.name})
        settings.start()
        self.addCleanup(settings.stop)

    @patch("src.api.main.requests.get")
    def test_health_keeps_public_contract_even_when_ollama_is_offline(self, get):
        get.side_effect = api.requests.ConnectionError("offline")
        status, raw = asgi_get("/health")
        self.assertEqual(status, 200)
        payload = json.loads(raw)
        self.assertTrue(_health_contract(payload))

    @patch("src.api.main.requests.get")
    def test_health_online_keeps_contract(self, get):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = 200
        get.return_value = response
        status, raw = asgi_get("/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["ollama_status"], "online")
        self.assertTrue(_health_contract(json.loads(raw)))

    @patch("src.api.main.requests.get", side_effect=AssertionError("Rede não deve ser usada"))
    def test_private_routes_without_cookie_are_denied_by_real_app(self, _get):
        for name, path in PRIVATE_GET:
            with self.subTest(name=name):
                code, body = asgi_get(path)
                self.assertEqual(code, 401, path)
                self.assertNotIn(b"traceback", body.lower())


if __name__ == "__main__":
    unittest.main()
