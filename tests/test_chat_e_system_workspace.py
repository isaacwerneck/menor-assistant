"""Chat E: status e catálogos privados, sem execução operacional."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.api import main
from src.security import auth
from test_auth_memory import call
from test_file_api import request

ASSETS = Path(__file__).resolve().parents[1] / "src/api/system_assets"
PAGE = (ASSETS / "system.html").read_text(encoding="utf-8")
SCRIPT = (ASSETS / "assets.js").read_text(encoding="utf-8")
STYLE = (ASSETS / "assets.css").read_text(encoding="utf-8")


class SystemWorkspaceTests(unittest.TestCase):
    def test_system_sources_only_read_existing_get_endpoints(self):
        for source in ("/health", "/models", "/images/status", "/agent/skills", "/tools"):
            self.assertIn(source, SCRIPT)
        self.assertIn("credentials: \"same-origin\"", SCRIPT)
        self.assertIn("redirect: \"error\"", SCRIPT)
        self.assertNotIn("method: \"POST\"", SCRIPT)
        self.assertNotIn("innerHTML", SCRIPT)
        self.assertIn("textContent", SCRIPT)
        self.assertIn("Sem telemetria de deploy", PAGE)
        self.assertIn("não confirma o código implantado", PAGE)
        self.assertIn("env(safe-area-inset-bottom)", STYLE)

    def test_no_inline_executable_code_or_remote_dependencies(self):
        self.assertIn('src="/workspace/system/assets.js"', PAGE)
        self.assertIn('href="/workspace/system/assets.css"', PAGE)
        self.assertNotIn("<script>", PAGE)
        self.assertNotIn("onclick=", PAGE)
        self.assertNotIn("https://", PAGE)
        self.assertNotIn("http://", PAGE)
        self.assertNotIn("@import", STYLE)
        self.assertNotIn("eval(", SCRIPT)

    def test_routes_require_owner_and_do_not_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"MENOR_DATA_DIR": directory}):
                auth._attempts.clear()
                status, _, headers = call("/auth/setup", {"password": "teste-chave-longa-protegida"})
                self.assertEqual(status, 200)
                cookie = headers[b"set-cookie"].decode().split(";", 1)[0]
                for path in ("/workspace/system", "/workspace/system/assets.js",
                             "/workspace/system/assets.css"):
                    self.assertEqual(request("GET", path)[0], 401)
                    self.assertEqual(request("GET", path, cookie=cookie)[0], 200)
                page_headers = main.system_workspace_router.routes[0].endpoint
                self.assertIsNotNone(page_headers)


if __name__ == "__main__":
    unittest.main()
