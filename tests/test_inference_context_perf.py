"""Verifica orçamentos reais enviados ao Ollama, ferramentas e métricas sem texto privado."""
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.agent import intelligence, runner
from src.agent.tasks import TaskStore
from src.agent.voice import NATURAL_VOICE, ROUTER_VOICE
from src.tools.registry import list_tools


def fake_reply(move="answer"):
    message = {"move": move, "reply": "Recebi sua pergunta."}
    if move == "plan":
        message.update(goal="Planejar uma horta", steps=["Coletar requisitos", "Verificar o resultado"])
    response = MagicMock()
    response.__enter__.return_value = response
    response.json.return_value = {
        "message": {"content": json.dumps(message)},
        "prompt_eval_count": 500, "prompt_eval_duration": 1_000_000_000,
        "eval_count": 20, "eval_duration": 2_000_000_000,
    }
    return response


class PromptBudgetTests(unittest.TestCase):
    @patch("src.agent.intelligence.requests.post")
    def test_empty_context_not_sent_as_many_sections(self, post):
        post.return_value = fake_reply()
        diag = {}
        result = intelligence.decide(
            "Oi", history=[], knowledge="", preferences="", feedback_examples=[],
            tools=[], capabilities=[], diagnostics=diag,
        )
        self.assertEqual(result["move"], "answer")
        payload = post.call_args.kwargs["json"]
        ctx = json.loads(payload["messages"][-1]["content"])
        self.assertNotIn("available_tools", ctx)
        self.assertNotIn("related_memory_data_not_instructions", ctx)
        self.assertNotIn("pending_goal", ctx)
        self.assertNotIn("paused_goals", ctx)
        self.assertNotIn("skills", ctx)
        self.assertNotIn("review_issues_data_not_instructions", ctx)
        self.assertLess(len(payload["messages"][-1]["content"]), 130)
        self.assertEqual(diag["tool_count"], 0)
        self.assertEqual(diag["outcome"], "validated")
        self.assertEqual(diag["performance"]["prompt_eval_count"], 500)
        self.assertIn("ollama_wall_ms", diag)
        self.assertNotIn("Oi", json.dumps(diag))

    @patch("src.agent.intelligence.requests.post")
    def test_all_tools_remain_exposed_and_tool_contract_is_still_validated(self, post):
        post.return_value = fake_reply()
        all_tools = list_tools()
        diag = {}
        intelligence.decide(
            "Confira minhas ferramentas", tools=all_tools, feedback_examples=[],
            preferences="", diagnostics=diag,
        )
        ctx = json.loads(post.call_args.kwargs["json"]["messages"][-1]["content"])
        listed = ctx["available_tools"]
        self.assertEqual({x["name"] for x in listed}, {x["name"] for x in all_tools})
        self.assertIn("math.calculate", {x["name"] for x in listed})
        for original, compact in zip(all_tools, listed):
            self.assertEqual(compact["arguments"], original["arguments"])
            self.assertEqual(compact["writes"], original["writes"])
        self.assertEqual(diag["tool_count"], len(all_tools))

    @patch("src.agent.intelligence.requests.post")
    def test_approved_facts_prior_goal_and_verified_receipt_not_lost(self, post):
        post.return_value = fake_reply()
        receipt = {"tool": "system.diagnose", "status": "executed", "summary": "OK"}
        intelligence.decide(
            "Qual servidor?", history=[{"role": "user", "content": "Ubuntu 24.04"}],
            pending={"id": "g1", "goal": "Diagnosticar servidor", "steps": ["Consultar relatório"]},
            knowledge="Dado comprovado de projeto", last_result=receipt,
            feedback_examples=[], preferences="Respostas objetivas.",
        )
        payload = post.call_args.kwargs["json"]
        ctx = json.loads(payload["messages"][-1]["content"])
        self.assertIn("Dado comprovado", ctx["related_memory_data_not_instructions"])
        self.assertEqual(ctx["pending_goal"]["goal"], "Diagnosticar servidor")
        self.assertEqual(ctx["previous_verified_tool_result_data"]["tool"], "system.diagnose")
        self.assertEqual(ctx["owner_preferences_data_not_permissions"], "Respostas objetivas.")
        self.assertEqual(payload["messages"][-2]["content"], "Ubuntu 24.04")

    def test_router_has_compact_voice_but_chat_preserves_natural_style(self):
        self.assertLess(len(ROUTER_VOICE), len(NATURAL_VOICE))
        self.assertIn("recibo", intelligence.SYSTEM)
        self.assertIn("Responda naturalmente", intelligence.SYSTEM)
        self.assertIn("Português brasileiro", intelligence.SYSTEM)

    @patch("src.agent.intelligence.requests.post", side_effect=__import__("requests").Timeout)
    def test_timeout_gives_metrics_but_no_fake_action(self, post):
        diag = {}
        self.assertIsNone(intelligence.decide(
            "Pode diagnosticar?", preferences="", feedback_examples=[], diagnostics=diag,
        ))
        self.assertEqual(diag["outcome"], "timeout")
        self.assertIn("ollama_wall_ms", diag)
        self.assertNotIn("message", diag)


class AgentPipelineTimingTests(unittest.TestCase):
    def test_real_runner_includes_safe_split_not_sensitive_context(self):
        with tempfile.TemporaryDirectory() as root:
            with (
                patch.dict(os.environ, {"MENOR_DATA_DIR": root, "MENOR_INTELLIGENCE_ENABLED": "1"}),
                patch.object(runner, "relevant_context", return_value="DADO_PRIVADO_DE_TESTE"),
                patch.object(runner, "contextual_knowledge", return_value=""),
                patch.object(runner.intelligence, "decide", return_value={
                    "move": "answer", "reply": "Está certo.", "goal": "foco",
                }),
            ):
                result = runner.run("sessionLong001", "turnLong0001", "Oi, confira.", [],
                                    tasks=TaskStore())
                self.assertEqual(result["reply"], "Está certo.")
                metrics = result["agent_metrics"]
                self.assertGreaterEqual(metrics["context_retrieval_ms"], 0)
                self.assertGreaterEqual(metrics["agent_wall_ms"], 0)
                self.assertGreater(metrics["available_tools"], 0)
                self.assertNotIn("DADO_PRIVADO_DE_TESTE", json.dumps(metrics))
                self.assertIn("prompt_assembly_ms", metrics)


if __name__ == "__main__":
    unittest.main()
