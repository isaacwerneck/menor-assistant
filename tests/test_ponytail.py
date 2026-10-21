"""Regressão da skill Ponytail em fluxos de código, sem Ollama ou rede."""
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.agent.ponytail import coding_guidance
from src.agent.self_edit import _propose_with_model
from src.agent.tool_builder import _generate


class PonytailTests(unittest.TestCase):
    def test_vendored_skill_and_license(self):
        root = Path(__file__).resolve().parents[1] / ".agents" / "skills"
        self.assertIn("# Ponytail", (root / "ponytail" / "SKILL.md").read_text())
        self.assertIn("MIT License", (root / "ponytail" / "LICENSE").read_text())
        self.assertIn("Audit the whole repo", (root / "ponytail-audit" / "SKILL.md").read_text())
        guidance = coding_guidance()
        self.assertIn("The smallest complete change", guidance)
        self.assertIn("Never cut", guidance)
        self.assertIn("não é autorização", guidance)
        self.assertNotIn("## Levels", guidance)

    @patch("src.agent.self_edit.requests.post")
    def test_code_proposal_receives_guidelines_without_new_permissions(self, post):
        response = MagicMock()
        response.json.return_value = {"message": {"content": json.dumps({
            "source": "def classify(x):\n    return x + 1\n",
            "reason": "Corrigir retorno", "tests": "testar retorno",
        })}}
        post.return_value = response
        code, review = _propose_with_model(
            "Corrigir retorno", "src/agent/router.py", "def classify(x):\n    return x\n",
        )
        self.assertIn("return x + 1", code)
        self.assertEqual(review["reason"], "Corrigir retorno")
        prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("The smallest complete change", prompt)
        self.assertIn("não é autorização", prompt)

    @patch("src.agent.tool_builder.requests.post")
    def test_tool_generator_keeps_contract_and_receives_guidelines(self, post):
        response = MagicMock()
        response.json.return_value = {"message": {"content": json.dumps({
            "source": "def run(text: str) -> str:\n    return text\n",
            "tests": (
                "import unittest\n"
                "class TestRun(unittest.TestCase):\n"
                "    def test_run(self):\n"
                "        self.assertEqual(1, 1)\n"
            ),
            "description": "Recebe e devolve um texto",
        })}}
        post.return_value.__enter__.return_value = response
        source, tests, description = _generate("eco", "Devolver a entrada sem modificar")
        self.assertIn("def run", source)
        self.assertIn("def test_run", tests)
        self.assertIn("texto", description)
        prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("The smallest complete change", prompt)
        self.assertIn("sem rede, arquivos", prompt)


if __name__ == "__main__":
    unittest.main()
