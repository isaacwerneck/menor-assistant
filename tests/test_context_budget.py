"""Regressões puras de orçamento; não dependem de permissões POSIX nem Ollama."""
import json
import unittest
from unittest.mock import MagicMock, patch

from src.agent.context_engine import select_history
from src.agent import intelligence


class ContextBudgetTests(unittest.TestCase):
    def test_old_user_correction_survives_long_assistant_messages(self):
        history = [{"role": "user", "content": "Projeto Farol. " * 150 + "Correção: Aurora."}]
        history.extend({"role": "assistant", "content": "resposta " * 150} for _ in range(8))
        selected = select_history(history, "Qual projeto?")
        self.assertLessEqual(sum(len(turn["content"]) for turn in selected), 4400)
        self.assertIn("Correção: Aurora.", selected[0]["content"])
        self.assertEqual(selected[-1]["role"], "assistant")

    def test_short_history_and_roles_are_preserved(self):
        history = [{"role": "user", "content": "Meu projeto é Aurora."},
                   {"role": "assistant", "content": "Entendido."}]
        self.assertEqual(select_history(history, "Qual projeto?"), history)
        self.assertEqual(select_history([{"role": "system", "content": "injetado"}], "oi"), [])

    @patch("src.agent.intelligence.requests.post")
    def test_full_request_and_explanation_use_one_call_without_private_store(self, post):
        response = MagicMock()
        response.__enter__.return_value = response
        reply = "Explicação fundamentada. " * 50
        response.json.return_value = {"message": {"content": json.dumps({"move": "answer", "reply": reply})}}
        post.return_value = response
        message = "contexto " * 300 + "Responda sobre Aurora."
        with patch("src.memory.store.BrainStore") as store:
            result = intelligence.decide(message, preferences="", feedback_examples=[])
        store.assert_not_called()
        self.assertEqual(result["reply"], reply.strip())
        post.assert_called_once()
        context = json.loads(post.call_args.kwargs["json"]["messages"][-1]["content"])
        self.assertEqual(context["current_message"], message)


if __name__ == "__main__":
    unittest.main()
