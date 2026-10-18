import base64
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.agent.self_edit import (
    ImprovementUnavailable, _validate_patch, choose_target, propose,
)
from test_auth_memory import call


class SupervisedDevTests(unittest.TestCase):
    def test_issue_to_safe_file_mapping(self):
        self.assertEqual(choose_target("Erro quando peço uma imagem"), "src/agent/image_intent.py")
        self.assertEqual(choose_target("O simm não confirma memória"), "src/agent/resolve.py")
        self.assertEqual(choose_target("Classificação errada"), "src/agent/router.py")

    def test_dry_run_does_not_need_credentials_or_write_git(self):
        with patch.dict(os.environ, {"MENOR_AUTODEV_ENABLED": "0", "MENOR_GITHUB_TOKEN": ""}):
            with patch("src.agent.self_edit.requests.request") as network:
                result = propose("A detecção de intenção está errando", dry_run=True)
                self.assertEqual(result["status"], "planned")
                network.assert_not_called()
                with self.assertRaises(ImprovementUnavailable):
                    propose("A detecção de intenção está errando", dry_run=False)

    def test_patch_validation_rejects_nonsyntax_and_new_dangerous_apis(self):
        original = "def classify(x):\n    return x\n"
        self.assertEqual(_validate_patch(original, "def classify(x):\n    return x + 1\n"),
                         "def classify(x):\n    return x + 1\n")
        with self.assertRaises((ValueError, SyntaxError)):
            _validate_patch(original, "def wrong(")
        for bad in ("eval('1 + 1')", "__import__('os')", "import subprocess"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                _validate_patch(original, bad)

    @patch("src.agent.self_edit._propose_with_model")
    @patch("src.agent.self_edit.requests.request")
    def test_opted_in_github_creates_draft_pr_not_main_commit(self, request, model):
        original = "def fn():\n    return 1\n"
        updated = "def fn():\n    return 2\n"
        model.return_value = (updated, {"reason": "bug", "tests": "pytest"})
        remote_calls = []

        def execute(method, url, **kwargs):
            remote_calls.append((method, url, kwargs.get("json")))
            response = MagicMock()
            if "/contents/" in url and method == "GET":
                response.json.return_value = {
                    "content": base64.b64encode(original.encode()).decode(), "sha": "file123",
                }
            elif "/git/ref/" in url:
                response.json.return_value = {"object": {"sha": "commit123"}}
            elif url.endswith("/pulls"):
                response.json.return_value = {"number": 42, "html_url": "https://github.com/pull/42"}
            else:
                response.json.return_value = {}
            return response

        request.side_effect = execute
        with patch.dict(os.environ, {
            "MENOR_AUTODEV_ENABLED": "1", "MENOR_GITHUB_TOKEN": "test-fake",
        }):
            with tempfile.TemporaryDirectory() as tmp:
                with patch.dict(os.environ, {"MENOR_DATA_DIR": tmp}):
                    result = propose("Classificador erra as intenções em português", dry_run=False)
        self.assertEqual(result["status"], "pr_created")
        self.assertTrue(result["requires_review"])
        self.assertTrue(any(x[0] == "POST" and x[1].endswith("/pulls") and
                            x[2]["draft"] for x in remote_calls))
        self.assertTrue(all(x[2].get("branch") != "main" for x in remote_calls
                            if x[0] == "PUT"))
        self.assertEqual(model.call_count, 1)


class ImprovementEndpointTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {
            "MENOR_DATA_DIR": tmp.name, "MENOR_AUTODEV_ENABLED": "0",
            "MENOR_GITHUB_TOKEN": "",
        })
        env.start()
        self.addCleanup(env.stop)
        from src.security import auth
        auth._attempts.clear()
        code, _, headers = call("/auth/setup", {"password": "senha-de-teste-suficiente"})
        self.assertEqual(code, 200)
        self.cookie = headers[b"set-cookie"].decode().split(";", 1)[0]

    def test_improvement_endpoint_has_safe_default(self):
        self.assertEqual(call("/agent/improve/status")[0], 401)
        code, data, _ = call("/agent/improve/status", cookie=self.cookie)
        self.assertEqual(code, 200)
        self.assertFalse(data["enabled"])
        code, result, _ = call("/agent/improve", {
            "issue": "O detector de imagens está falhando",
        }, cookie=self.cookie)
        self.assertEqual(code, 200)
        self.assertEqual(result["status"], "planned")
        code, result, _ = call("/agent/improve", {
            "issue": "O detector de imagens está falhando", "dry_run": False,
        }, cookie=self.cookie)
        self.assertEqual(code, 503)
        self.assertIn("não autorizada", result["detail"])


if __name__ == "__main__":
    unittest.main()
