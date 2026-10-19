"""Chat E: contrato visual da tela de arquivos, sem substituir a lógica do Chat B."""

import unittest
from html.parser import HTMLParser
from pathlib import Path


BASE = Path(__file__).resolve().parents[1] / "src/tools/file_analysis/templates"
HTML = (BASE / "files.html").read_text(encoding="utf-8")
CSS = (BASE / "assets.css").read_text(encoding="utf-8")
JS = (BASE / "assets.js").read_text(encoding="utf-8")
EXPECTED_IDS = {
    "file", "upload", "message", "question", "context", "vision",
    "vision-state", "ocr-page", "ocr", "ocr-state", "file-info",
    "result", "delete",
}
DISABLED_ACTIONS = {"context", "vision", "ocr", "delete"}


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []
        self.ids = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        self.elements.append((tag, values))
        if "id" in values:
            self.ids.append(values["id"])


class FileWorkspaceUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = Tags()
        cls.page.feed(HTML)

    def test_preserves_every_existing_control_for_file_worker(self):
        self.assertTrue(EXPECTED_IDS.issubset(self.page.ids))
        self.assertEqual(len(self.page.ids), len(set(self.page.ids)))
        for name in DISABLED_ACTIONS:
            node = next(attrs for _, attrs in self.page.elements if attrs.get("id") == name)
            self.assertIn("disabled", node)
        self.assertIn('src="/files/assets.js"', HTML)
        self.assertIn('href="/files/assets.css"', HTML)

    def test_navigation_is_real_and_accessible(self):
        self.assertIn('href="/"', HTML)
        self.assertIn('href="#workspace"', HTML)
        self.assertIn('id="workspace"', HTML)
        self.assertIn('aria-current="page"', HTML)
        self.assertIn('class="mobile-nav"', HTML)
        self.assertIn('class="sidebar"', HTML)
        self.assertIn("env(safe-area-inset-bottom)", CSS)
        self.assertIn("prefers-reduced-motion", CSS)
        self.assertIn("prefers-reduced-transparency", CSS)
        self.assertIn(":focus-visible", CSS)

    def test_privacy_and_current_csp_are_preserved(self):
        self.assertNotIn("<script>", HTML)
        self.assertNotIn("onclick=", HTML)
        self.assertNotIn("style=", HTML)
        self.assertNotIn("http://", HTML)
        self.assertNotIn("https://", HTML)
        self.assertNotIn("@import", CSS)
        self.assertIn("Os arquivos ficam no armazenamento privado", HTML)
        self.assertIn("não garantem verificação semântica", HTML)
        self.assertIn("credentials: \"same-origin\"", JS)

    def test_status_and_error_results_remain_visible(self):
        self.assertIn('role="status" aria-live="polite"', HTML)
        self.assertIn('id="result" tabindex="0"', HTML)
        self.assertIn('id="delete"', HTML)
        self.assertIn("result.textContent", JS)
        self.assertIn("message.textContent", JS)


if __name__ == "__main__":
    unittest.main()
