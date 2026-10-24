"""Testes do Curador Visual Autônomo e Multimodal (Fase 3)."""
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.agent.visual_curator import VisualCurator, curate_visual_references
from src.memory.store import BrainStore


class TestVisualCuratorV2(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = BrainStore(data_dir=self.temp_dir.name)
        self.store.initialize()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_fetch_candidates_fallback(self):
        curator = VisualCurator(store=self.store)
        candidates = curator.fetch_candidates("dark ui glassmorphism", limit=5)
        self.assertIsInstance(candidates, list)
        self.assertGreaterEqual(len(candidates), 1)
        self.assertIn("url", candidates[0])

    def test_evaluate_image_fallback(self):
        curator = VisualCurator(store=self.store)
        res = curator.evaluate_image(image_url="http://example.com/test.png", criteria="dark minimalista")
        self.assertIn("score", res)
        self.assertGreaterEqual(res["score"], 5.0)
        self.assertIn("style", res)
        self.assertIn("palette", res)

    @patch("requests.post")
    def test_evaluate_image_with_vlm(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        fake_json = (
            '{"score": 9.2, "style": "Cyberpunk UI", "palette": ["#1a0033", "#00f3ff"], '
            '"critique": "Excelente contraste", "approved": true}'
        )
        mock_resp.json.return_value = {"message": {"content": fake_json}}
        mock_post.return_value = mock_resp

        curator = VisualCurator(store=self.store)
        res = curator.evaluate_image(image_data=b"fake-bytes", criteria="cyberpunk")
        self.assertEqual(res["score"], 9.2)
        self.assertEqual(res["style"], "Cyberpunk UI")
        self.assertEqual(res["palette"], ["#1a0033", "#00f3ff"])

    def test_curate_pipeline(self):
        curator = VisualCurator(store=self.store)
        candidates = [
            {"url": "http://img1.png", "title": "Dashboard Dark"},
            {"url": "http://img2.png", "title": "Mobile App Glass"},
            {"url": "http://img3.png", "title": "Minimal Wireframe"},
        ]
        res = curator.curate(query="Dark Mode UI", domain="design", max_selection=2, candidates=candidates)
        self.assertTrue(res["success"])
        self.assertEqual(res["selected_count"], 2)
        self.assertTrue(len(res["top_selection"]) <= 2)
        # Score decrescente
        self.assertGreaterEqual(res["top_selection"][0]["score"], res["top_selection"][1]["score"])

        # Verifica se gerou arquivo de relatório
        rep_path = self.store.brain_dir / "relatorios"
        reports = list(rep_path.glob("curadoria_*.md"))
        self.assertEqual(len(reports), 1)

        # Verifica se salvou regra em conhecimentos/design/
        notes = self.store.list_domain_knowledge("design")
        self.assertTrue(any("referencias" in k for k in notes.keys()))

    def test_tool_curate_visual_references(self):
        res = curate_visual_references(
            query="Game Textures Shaders", domain="game_design", max_selection=3, store=self.store
        )
        self.assertTrue(res["success"])
        self.assertIn("top_selection", res)


if __name__ == "__main__":
    unittest.main()
