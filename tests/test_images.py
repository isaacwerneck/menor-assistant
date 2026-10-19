import base64
import io
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from src.agent.image_intent import image_intent
from src.tools import images
from test_auth_memory import call


class ImageIntentTests(unittest.TestCase):
    def test_screenshot_prompts_for_missing_details_not_generic_refusal(self):
        value = image_intent("quero q vc crie uma imagem pra mim")
        self.assertEqual(value["decision"], "image_ask")
        self.assertEqual(value["kind"], "generate")
        self.assertIn("imagem", value["question"])

    def test_pixel_art_and_sprites_are_image_requests(self):
        for message in ("queria criar uma pixel art, vc consegue me ajudar?", "quero gerar um sprite"):
            with self.subTest(message=message):
                self.assertEqual(image_intent(message)["decision"], "image_ask")
        for style in ("pixel art", "pixel-art", "sprite"):
            self.assertEqual(image_intent("Crie uma " + style + " de um gato astronauta")["decision"],
                             "image_generate")
        self.assertEqual(image_intent("Anota a ideia de criar pixel art")["decision"], "chat")
        self.assertEqual(image_intent("Salva a ideia de criar pixel art")["decision"], "chat")
        self.assertEqual(image_intent("Crie pixel art de um gato astronauta e salve como PNG")["decision"],
                         "image_generate")

    def test_detailed_image_request_generates(self):
        value = image_intent("Cria uma imagem de uma moto numa rua chuvosa, estilo realista")
        self.assertEqual(value["decision"], "image_generate")
        self.assertIn("moto", value["prompt"])

    def test_edit_needs_file_and_tool_creation_is_not_image_request(self):
        self.assertEqual(image_intent("edita essa foto")["decision"], "image_ask")
        self.assertEqual(image_intent("edita essa foto e deixa o céu azul", True)["decision"], "image_edit")
        self.assertEqual(image_intent("vamos criar uma ferramenta de gerar imagens")["decision"], "chat")
        self.assertEqual(image_intent("como criar imagens em Python?")["decision"], "chat")
        self.assertEqual(image_intent("como fazer um plugin de imagem")["decision"], "chat")


class ImageProviderTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {
            "MENOR_DATA_DIR": tmp.name, "MENOR_IMAGE_API_KEY": "fake-key",
            "MENOR_IMAGE_PROVIDER": "openai",
        })
        env.start()
        self.addCleanup(env.stop)
        buffer = io.BytesIO()
        Image.new("RGB", (12, 12)).save(buffer, "PNG")
        self.png = buffer.getvalue()

    @patch("src.tools.images.requests.post")
    def test_image_generate_saves_private_png_and_returns_confirmed_url(self, post):
        response = MagicMock()
        response.json.return_value = {
            "data": [{"b64_json": base64.b64encode(self.png).decode()}],
        }
        post.return_value = response
        result = images.generate("Um gato cinza numa rua chuvosa")
        self.assertEqual(result["status"], "completed")
        self.assertRegex(result["url"], r"^/images/files/[a-f0-9]{32}$")
        self.assertTrue(images.file_path(result["id"]).exists())
        self.assertEqual(images.file_path(result["id"]).stat().st_mode & 0o777, 0o600)
        self.assertEqual(post.call_args.kwargs["json"]["model"], "gpt-image-1")

    @patch("src.tools.images.requests.post")
    def test_edit_uses_upload_and_does_not_forge_success(self, post):
        response = MagicMock()
        response.json.return_value = {
            "data": [{"b64_json": base64.b64encode(self.png).decode()}],
        }
        post.return_value = response
        result = images.edit("Troque o fundo para azul", self.png)
        self.assertEqual(result["kind"], "edit")
        self.assertIn("image", post.call_args.kwargs["files"])
        self.assertTrue(images.file_path(result["id"]).exists())

    def test_unconfigured_engine_refuses_without_creating_files(self):
        with patch.dict(os.environ, {"MENOR_IMAGE_API_KEY": ""}):
            with self.assertRaises(images.ImageUnavailable):
                images.generate("Uma montanha vista do espaço")

    def test_reject_fake_images_and_path_traversal(self):
        with self.assertRaises(ValueError):
            images._verify_image(b"a" * 200)
        for name in ("../../etc/passwd", "abc.png", "A" * 32):
            with self.subTest(name=name), self.assertRaises(ValueError):
                images.file_path(name)

    @patch("src.tools.images.requests.post")
    def test_invalid_provider_response_never_confirms_generated_file(self, post):
        response = MagicMock()
        response.json.return_value = {"data": [{"b64_json": "not-an-image"}]}
        post.return_value = response
        with self.assertRaises((images.ImageUnavailable, ValueError)):
            images.generate("Um céu azul sobre o mar")


class ImageEndpointTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {
            "MENOR_DATA_DIR": tmp.name, "MENOR_IMAGE_API_KEY": "",
            "MENOR_IMAGE_PROVIDER": "local",
        })
        env.start()
        self.addCleanup(env.stop)
        from src.security import auth
        auth._attempts.clear()
        code, _, headers = call("/auth/setup", {"password": "senha-muito-grande-de-teste"})
        self.assertEqual(code, 200)
        self.cookie = headers[b"set-cookie"].decode().split(";", 1)[0]

    def test_generation_requires_auth_and_returns_honest_engine_state(self):
        self.assertEqual(call("/images/generate", {"prompt": "Um gato no jardim"})[0], 401)
        code, result, _ = call("/images/status", cookie=self.cookie)
        self.assertEqual(code, 200)
        self.assertFalse(result["configured"])
        code, result, _ = call("/images/generate", {"prompt": "Um gato no jardim"}, cookie=self.cookie)
        self.assertEqual(code, 503)
        self.assertIn("não instalado", result["detail"])

    def test_intent_requires_login_and_recognizes_exact_report(self):
        self.assertEqual(call("/images/intent", {"message": "cria uma foto"})[0], 401)
        code, result, _ = call("/images/intent", {
            "message": "quero q vc crie uma imagem pra mim",
        }, cookie=self.cookie)
        self.assertEqual(code, 200)
        self.assertEqual(result["decision"], "image_ask")
        self.assertEqual(call("/images/generate", {"prompt": "Um gato no jardim"},
                              cookie=self.cookie, origin="http://evil.invalid")[0], 403)


if __name__ == "__main__":
    unittest.main()
