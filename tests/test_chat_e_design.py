"""Contrato do Chat E: identidade visual sem alterar as APIs nem a conversa."""

import unittest
from pathlib import Path


HTML = (Path(__file__).resolve().parents[1] / "src/api/templates/chat.html").read_text(encoding="utf-8")


class ChatEDesignTests(unittest.TestCase):
    def test_brand_uses_minimalist_identity(self):
        self.assertIn("<title>Menor AI — Assistente pessoal</title>", HTML)
        self.assertIn('class="brand"', HTML)
        self.assertIn('class="brand-mark"', HTML)
        self.assertIn("--accent: #b2a2f5;", HTML)
        self.assertNotIn('<div class="welcome-logo">⚡</div>', HTML)

    def test_navigation_uses_existing_features(self):
        self.assertIn('class="app-nav" aria-label="Navegação principal"', HTML)
        self.assertIn('class="mobile-nav" aria-label="Navegação rápida"', HTML)
        self.assertIn('href="/files/view"', HTML)
        self.assertIn('onclick="openProjects()"', HTML)
        self.assertIn('onclick="openBrain()"', HTML)
        self.assertIn('onclick="toggleSidebar()"', HTML)
        self.assertIn('id="userInput"', HTML)
        self.assertIn('id="sendBtn"', HTML)

    def test_responsive_accessible_treatments(self):
        self.assertIn("@media (max-width: 768px)", HTML)
        self.assertIn("env(safe-area-inset-bottom)", HTML)
        self.assertIn("prefers-reduced-motion", HTML)
        self.assertIn("prefers-reduced-transparency", HTML)
        self.assertIn(":focus-visible", HTML)
        self.assertIn('aria-current="page"', HTML)
        self.assertIn("[hidden] { display: none !important; }", HTML)

    def test_visual_changes_do_not_require_external_dependencies(self):
        self.assertNotIn("@import url(", HTML)
        self.assertNotIn("fonts.googleapis.com", HTML)
        self.assertEqual(HTML.count("<script>"), 1)
        self.assertEqual(HTML.count("</script>"), 1)
        self.assertIn('onclick="sendMsg()"', HTML)


if __name__ == "__main__":
    unittest.main()
