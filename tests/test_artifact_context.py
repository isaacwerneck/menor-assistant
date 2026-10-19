import io
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from src.agent import artifacts, image_prompt, intelligence, runner
from src.agent.model_catalog import comparison, discover
from src.agent.reviewer import review_image
from src.agent.tasks import TaskStore
from src.tools import images


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {"MENOR_DATA_DIR": folder.name})
        env.start()
        self.addCleanup(env.stop)

    def _saved(self, size=(32, 32)):
        picture = Image.new("RGB", size, "purple")
        buf = io.BytesIO()
        picture.save(buf, "PNG")
        return images._save(buf.getvalue())

    def test_actual_requested_32x32_is_real_png_not_false_label(self):
        picture = Image.new("RGB", (512, 512), "purple")
        final, meta = artifacts.format_image(picture, "Um mago 32x32 chapéu marrom, capa roxa")
        self.assertEqual(final.size, (32, 32))
        self.assertTrue(meta["postprocessed"])
        self.assertEqual(meta["requested_size"], [32, 32])
        stored = self._saved(final.size)
        review = review_image({**stored, "status": "completed", "prompt": "mago 32x32"})
        self.assertTrue(review["passed"])
        self.assertFalse(review["content_verified"])
        self.assertEqual(review["width"], 32)

    def test_wrong_dimensions_are_not_accepted_as_valid(self):
        stored = self._saved((512, 512))
        review = review_image({**stored, "status": "completed", "prompt": "mago 32x32"})
        self.assertFalse(review["passed"])
        self.assertIn("resolução", review["reason"])
        with self.assertRaises(ValueError):
            artifacts.requested_size("2x9000")

    def test_receipt_does_not_claim_semantic_success(self):
        img = self._saved()
        proof = {
            **img, "prompt": "mago 32x32 marrom e roxo", "worker": "openvino-sd15-int8",
            "review": {"passed": True, "width": 32, "height": 32, "content_verified": False},
        }
        receipt = artifacts.artifact_receipt(proof)
        self.assertEqual(receipt["actual_size"], [32, 32])
        self.assertFalse(receipt["content_verified"])
        self.assertIn("não", artifacts.describe_artifact(receipt))

    @patch("src.agent.runner.capability_status", return_value={"ready": True})
    @patch("src.agent.runner.generate_image")
    def test_followup_uses_persisted_tool_receipt_even_after_restart(self, generate, capability):
        saved = self._saved()
        generate.return_value = {
            **saved, "prompt": "imagem de um mago 32x32 com capa roxa",
            "worker": "openvino-sd15-int8",
            "review": {"passed": True, "width": 32, "height": 32},
        }
        tasks = TaskStore()
        session = "imgConversationOne"
        with patch.dict(os.environ, {"MENOR_INTELLIGENCE_ENABLED": "0"}):
            first = runner.run(session, "imgTurn00001",
                               "crie uma imagem de um mago 32x32", [], tasks=tasks)
        self.assertTrue(first["handled"])
        self.assertEqual(first["artifact"]["actual_size"], [32, 32])
        self.assertEqual(TaskStore().inspect(session)["last_result"]["id"], saved["id"])
        response = {
            "move": "inspect_result",
            "goal": "Entender a última imagem", "reply": "Vou explicar a imagem produzida.",
            "question": "", "steps": [], "acceptance": [],
        }
        with patch("src.agent.runner.intelligence.decide", return_value=response), patch(
            "src.agent.runner.contextual_knowledge", return_value=""
        ), patch("src.agent.runner.relevant_context", return_value=""):
            next_turn = runner.run(session, "imgTurn00002", "o que é isso que gerou?",
                                   [], tasks=TaskStore())
        self.assertIn("32×32", next_turn["reply"])
        self.assertIn("mago", next_turn["reply"])
        self.assertNotIn("não tenho a capacidade", next_turn["reply"])

    @patch("src.agent.intelligence.requests.post")
    def test_model_receives_tool_receipt_and_can_select_inspect(self, post):
        stub = MagicMock()
        stub.__enter__.return_value = stub
        stub.json.return_value = {"message": {"content": (
            '{"move":"inspect_result","goal":"Revisar imagem","reply":"Vou consultar recibo",'
            '"question":"","steps":[],"acceptance":[]}'
        )}}
        post.return_value = stub
        receipt = {"kind": "image", "id": "a" * 32, "actual_size": [32, 32]}
        self.assertEqual(
            intelligence.decide("o que é isso?", last_result=receipt)["move"], "inspect_result"
        )
        import json
        payload = post.call_args.kwargs["json"]
        self.assertEqual(
            json.loads(payload["messages"][-1]["content"])["previous_verified_tool_result_data"],
            receipt,
        )

    def test_catalog_shows_real_alternatives_without_inventing_installers(self):
        options = comparison("images.generate")
        self.assertGreaterEqual(len(options), 3)
        self.assertEqual(sum(x["install_supported"] for x in options), 1)
        self.assertEqual(len(discover("images.generate")), 1)
        self.assertTrue(all(x["url"].startswith("https://huggingface.co/") for x in options))
        self.assertEqual(comparison("music"), [])


class ImagePromptTests(unittest.TestCase):
    @patch("src.agent.image_prompt.requests.post")
    def test_translated_prompt_preserves_resolution_and_subject(self, post):
        stub = MagicMock()
        stub.__enter__.return_value = stub
        stub.json.return_value = {"message": {"content": (
            '{"prompt":"full body fantasy wizard with brown hat and purple cloak, pixel art"}'
        )}}
        post.return_value = stub
        result = image_prompt.adapt("Faz um mago 32x32 de chapéu marrom e capa roxa")
        self.assertIn("wizard", result)
        self.assertIn("32x32", result)

    @patch("src.agent.image_prompt.requests.post", side_effect=ValueError("offline"))
    def test_prompt_failure_is_fallback_not_claimed_success(self, post):
        brief = "Criar um personagem 32x32 com capa roxa"
        self.assertEqual(image_prompt.adapt(brief), brief)


if __name__ == "__main__":
    unittest.main()
