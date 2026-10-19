"""Chat E: painel de objetivos só pode consultar estados e deve ser privado."""
import unittest
from html.parser import HTMLParser
from pathlib import Path

from src.api import main
from test_file_api import request
from test_auth_memory import call
from unittest.mock import patch
import os
import tempfile

ASSETS = Path(__file__).resolve().parents[1] / "src/api/workspace_assets"
HTML = (ASSETS / "objectives.html").read_text(encoding="utf-8")
JS = (ASSETS / "assets.js").read_text(encoding="utf-8")
CSS = (ASSETS / "assets.css").read_text(encoding="utf-8")


class Parse(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])


class ObjectivesDashboardTests(unittest.TestCase):
    def test_safe_markup_and_controls(self):
        p = Parse()
        p.feed(HTML)
        self.assertEqual(len(set(p.ids)), len(p.ids))
        for name in ("goals", "missions", "refresh", "mission-filter", "status"):
            self.assertIn(name, p.ids)
        self.assertIn('href="/files/view"', HTML)
        self.assertIn('href="/"', HTML)
        self.assertIn('src="/workspace/assets.js"', HTML)
        self.assertIn("aria-live=", HTML)
        self.assertNotIn("<script>", HTML)
        self.assertNotIn("onclick=", HTML)
        self.assertNotIn("innerHTML", JS)
        self.assertIn("textContent", JS)
        self.assertIn('method: "POST"', JS) if False else self.assertNotIn('method: "POST"', JS)

    def test_server_sources_and_nonfiction(self):
        self.assertIn('"/agent/missions"', JS)
        self.assertIn('"/agent/runs/"', JS)
        self.assertIn("Nenhum estado foi presumido", JS)
        self.assertNotIn("Math.random()", JS)
        self.assertIn("env(safe-area-inset-bottom)", CSS)
        self.assertIn("prefers-reduced-motion", CSS)

    def test_workspace_requires_owner_for_page_and_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"MENOR_DATA_DIR": directory}):
                from src.security import auth
                auth._attempts.clear()
                status, _, headers = call("/auth/setup", {"password": "super-seguro-teste-12345"})
                self.assertEqual(status, 200)
                cookie = headers[b"set-cookie"].decode().split(";", 1)[0]
                for path in ("/workspace/objectives", "/workspace/assets.js", "/workspace/assets.css"):
                    self.assertEqual(request("GET", path)[0], 401)
                    self.assertEqual(request("GET", path, cookie=cookie)[0], 200)
                headers = main.workspace_router  # Check routing is registered and import available.
                self.assertIsNotNone(headers)


if __name__ == "__main__":
    unittest.main()
