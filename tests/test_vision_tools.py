"""Ollama visual: opt-in local, imagem comprovada, ausência de falso sucesso."""
import io
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from src.tools import vision
from src.tools.file_analysis import service
from src.tools.file_analysis.contracts import FileRejected


def response(data):
    value = MagicMock()
    value.json.return_value = data
    value.__enter__.return_value = value
    value.raise_for_status.return_value = None
    return value


class LocalVisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = patch.dict(os.environ, {
            "MENOR_DATA_DIR": self.temp.name,
            "OLLAMA_URL": "http://127.0.0.1:11434",
            "MENOR_VISION_MODEL": "qwen2.5vl:3b",
        })
        self.settings.start()
        self.addCleanup(self.settings.stop)
        png = io.BytesIO()
        Image.new("RGB", (32, 32), "purple").save(png, "PNG")
        self.image_id = service.ingest(png.getvalue(), "sprite.png")["file"]["file_id"]
        self.text_id = service.ingest(b"texto", "notes.txt")["file"]["file_id"]

    def test_model_not_configured_cannot_claim_visual_understanding(self):
        with patch.dict(os.environ, {"MENOR_VISION_MODEL": ""}):
            with patch("src.tools.vision.requests.get") as get:
                state = vision.status()
                self.assertEqual(state["status"], "not_configured")
                get.assert_not_called()
                self.assertEqual(vision.inspect_image(self.image_id)["status"], "unavailable")

    @patch("src.tools.vision.requests.get")
    @patch("src.tools.vision.requests.post")
    def test_model_not_installed_does_not_attempt_inference(self, post, get):
        get.return_value = response({"models": [{"name": "other:1b"}]})
        result = vision.inspect_image(self.image_id)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["model_state"]["status"], "missing_model")
        post.assert_not_called()

    def test_invalid_or_remote_ollama_url_rejected(self):
        for endpoint in ("https://127.0.0.1:11434", "http://example.com:11434",
                         "http://127.0.0.1:11434/path", "http://x@evil.com:11434"):
            with self.subTest(endpoint=endpoint):
                with patch.dict(os.environ, {"OLLAMA_URL": endpoint}):
                    with self.assertRaises(ValueError):
                        vision._url()

    @patch("src.tools.vision.requests.get")
    @patch("src.tools.vision.requests.post")
    def test_vision_receipt_separates_observations_inferences_and_quality(self, post, get):
        get.return_value = response({"models": [{"name": "qwen2.5vl:3b"}]})
        post.return_value = response({
            "message": {"content": json.dumps({
                "observations": ["Há uma região roxa visível."],
                "inferences": ["Pode ser um fundo."],
                "answer": "A cor dominante parece roxa.",
                "uncertainty": "Não há elementos suficientes para inferir um personagem.",
            })}
        })
        result = vision.inspect_image(self.image_id, "Qual é a cor mais visível?")
        self.assertEqual(result["status"], "executed", result)
        self.assertTrue(result["validation"]["technical_file_verified"])
        self.assertFalse(result["validation"]["semantic_verified"])
        self.assertEqual(result["quality_status"], "unverified_model_assessment")
        self.assertEqual(result["evidence"][0]["dimensions"], [32, 32])
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "qwen2.5vl:3b")
        self.assertTrue(payload["messages"][1]["images"][0])
        self.assertIn("Qual é a cor", payload["messages"][1]["content"])

    @patch("src.tools.vision.requests.get")
    @patch("src.tools.vision.requests.post")
    def test_bad_model_json_returns_explicit_failure(self, post, get):
        get.return_value = response({"models": [{"name": "qwen2.5vl:3b"}]})
        post.return_value = response({"message": {"content": "Isso não é JSON."}})
        result = vision.inspect_image(self.image_id)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["content_verified"])
        self.assertEqual(result["evidence"], [])

    @patch("src.tools.vision.requests.get")
    @patch("src.tools.vision.requests.post")
    def test_non_image_rejected_before_calling_vision(self, post, get):
        get.return_value = response({"models": [{"name": "qwen2.5vl:3b"}]})
        with self.assertRaises(FileRejected):
            vision.inspect_image(self.text_id)
        post.assert_not_called()

    @patch("src.tools.vision.requests.get")
    def test_question_contract_and_missing_file(self, get):
        get.return_value = response({"models": [{"name": "qwen2.5vl:3b"}]})
        for question in ("", "x" * 501):
            with self.assertRaises(ValueError):
                vision.inspect_image(self.image_id, question)
        with self.assertRaises(FileRejected):
            vision.inspect_image("../outside", "Descreva a imagem")

    def test_schema_validator_refuses_claims_without_structure(self):
        for payload in ([], {"observations": "texto", "inferences": []},
                        {"observations": [], "inferences": ["x"], "answer": "",
                         "uncertainty": "não sei"}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                vision._validate_assessment(payload)


if __name__ == "__main__":
    unittest.main()
