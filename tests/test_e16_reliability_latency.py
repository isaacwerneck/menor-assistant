"""E16: no duplicate slow inference, complete timings and approval scope safety."""
import os
import unittest
from unittest.mock import MagicMock, patch

from src.agent import conversation, runner


class ReliabilityLatencyTests(unittest.TestCase):
    def test_default_disables_secondary_inference(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(runner._secondary_inference_enabled())
        with patch.dict(os.environ, {"MENOR_SECONDARY_INFERENCE_ENABLED": "1"}):
            self.assertTrue(runner._secondary_inference_enabled())

    def test_failed_reasoner_does_not_trigger_second_model_or_lie(self):
        metrics = {}
        with (patch.object(runner.intelligence, "decide", return_value=None),
              patch.object(runner.conversation, "reply") as fallback,
              patch.object(runner, "relevant_context", return_value=""),
              patch.object(runner, "contextual_knowledge", return_value=""),
              patch("src.agent.skills.catalog", return_value=[]),
              patch.dict(os.environ, {"MENOR_SECONDARY_INFERENCE_ENABLED": "0"})):
            next_state, answer = runner._understand(
                {"phase": "idle"}, "Quero organizar um projeto", [], metrics=metrics)
        fallback.assert_not_called()
        self.assertEqual(next_state["phase"], "idle")
        self.assertTrue(answer["handled"])
        self.assertIn("Não consegui interpretar", answer["reply"])
        self.assertEqual(metrics["fallback_reason"], "reasoner_unavailable")
        for key in ("semantic_retrieval_ms", "lexical_retrieval_ms",
                    "project_context_ms", "context_retrieval_ms", "reasoner_wall_ms"):
            self.assertIn(key, metrics)

    def test_pending_goal_survives_model_failure_without_second_call(self):
        previous = {"phase": "goal", "goal": "Criar guia de estudos",
                    "goal_id": "goalabc", "steps": [], "acceptance": []}
        with (patch.object(runner.intelligence, "decide", return_value=None),
              patch.object(runner.conversation, "reply") as reply,
              patch.object(runner, "relevant_context", return_value=""),
              patch.object(runner, "contextual_knowledge", return_value=""),
              patch("src.agent.skills.catalog", return_value=[]),
              patch.dict(os.environ, {"MENOR_SECONDARY_INFERENCE_ENABLED": "0"})):
            state, answer = runner._understand(previous, "E agora?", [])
        self.assertEqual(state["goal_id"], "goalabc")
        self.assertEqual(state["phase"], "goal")
        self.assertIn("preservado", answer["reply"])
        reply.assert_not_called()

    def test_fallback_for_thin_reply_requires_explicit_opt_in(self):
        decision = {"move": "answer", "reply": "Sim", "relation": None}
        with (patch.object(runner.intelligence, "decide", return_value=decision),
              patch.object(runner.conversation, "reply") as reply,
              patch.object(runner, "relevant_context", return_value=""),
              patch.object(runner, "contextual_knowledge", return_value=""),
              patch("src.agent.skills.catalog", return_value=[]),
              patch.dict(os.environ, {"MENOR_SECONDARY_INFERENCE_ENABLED": "0"})):
            metrics = {}
            state, answer = runner._understand({"phase": "idle"},
                                               "Quero entender meu orçamento", [],
                                               metrics=metrics)
        self.assertEqual(state["phase"], "idle")
        self.assertIn("resposta recebida foi insuficiente", answer["reply"])
        self.assertEqual(metrics["fallback_reason"], "low_information_reply")
        reply.assert_not_called()

    def test_secondary_inference_can_be_enabled_by_operator(self):
        decision = {"move": "answer", "reply": "Sim", "relation": None}
        with (patch.object(runner.intelligence, "decide", return_value=decision),
              patch.object(runner.conversation, "reply",
                           return_value="Podemos comparar as opções primeiro.") as reply,
              patch.object(runner, "relevant_context", return_value=""),
              patch.object(runner, "contextual_knowledge", return_value=""),
              patch("src.agent.skills.catalog", return_value=[]),
              patch.dict(os.environ, {"MENOR_SECONDARY_INFERENCE_ENABLED": "1"})):
            metrics = {}
            _, answer = runner._understand({"phase": "idle"}, "Gostaria de entender opções",
                                           [], metrics=metrics)
        reply.assert_called_once()
        self.assertIn("Podemos comparar", answer["reply"])
        self.assertEqual(metrics["secondary_model_calls"], 1)

    def test_old_maintenance_approval_cannot_execute_after_scope_is_removed(self):
        previous = {"phase": "approval", "tool": "developer.propose",
                    "arguments": {"issue": "Revisar código do assistente"}}
        with (patch.dict(os.environ, {"MENOR_AGENT_SCOPE": "personal"}),
              patch.object(runner, "perform") as perform):
            state, response = runner._advance(previous, "eu aprovo", [])
        self.assertEqual(state["phase"], "blocked")
        self.assertIn("não está mais autorizada", response["reply"])
        perform.assert_not_called()

    def test_malformed_saved_approval_never_executes(self):
        cases = [
            {"phase": "approval", "tool": "projects.create",
             "arguments": {"name": "A", "other": "hidden"}},
            {"phase": "approval", "tool": "projects.create", "arguments": ["wrong"]},
            {"phase": "approval", "tool": "projects.create", "arguments": {"name": ""}},
        ]
        with patch.object(runner, "perform") as perform:
            for state in cases:
                with self.subTest(state=state):
                    after, answer = runner._advance(state, "eu aprovo", [])
                    self.assertEqual(after["phase"], "blocked")
                    self.assertIn("nenhuma ação foi executada", answer["reply"].lower())
        perform.assert_not_called()

    def test_normal_pending_approval_executes_exactly_once(self):
        previous = {"phase": "approval", "tool": "projects.create",
                    "arguments": {"name": "Planejamento"}}
        receipt = {"tool": "projects.create", "status": "executed",
                   "result": {"name": "Planejamento"}}
        with (patch.dict(os.environ, {"MENOR_AGENT_SCOPE": "personal"}),
              patch.object(runner, "perform", return_value=receipt) as perform):
            state, response = runner._advance(previous, "eu aprovo", [])
        self.assertEqual(state["phase"], "idle")
        self.assertIn("Execução confirmada", response["reply"])
        perform.assert_called_once_with("projects.create", {"name": "Planejamento"},
                                        dry_run=False)

    def test_multi_step_tool_loop_counts_model_calls_and_time(self):
        output = iter([
            {"action": "tool", "tool": "projects.list", "arguments": {},
             "reply": "Vou consultar projetos."},
            {"action": "answer", "reply": "Consultei a lista de projetos."},
        ])

        def action(*_args):
            return next(output)
        receipt = {"tool": "projects.list", "status": "executed", "result": []}
        with (patch.object(runner, "_model_step", side_effect=action),
              patch.object(runner, "perform", side_effect=[
                  {"status": "planned"}, receipt]) as perform):
            metrics = {}
            state, answer = runner._tool_loop("Quais são meus projetos?", [], metrics)
        self.assertEqual(state["phase"], "idle")
        self.assertEqual(metrics["tool_model_calls"], 2)
        self.assertGreaterEqual(metrics["tool_model_wall_ms"], 0)
        self.assertIn("Consultei", answer["reply"])
        self.assertEqual(perform.call_count, 2)

    def test_tool_model_keeps_ollama_resident_when_configured(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {"message": {"content": (
            '{"action":"answer","reply":"Informação recebida."}')}}
        with (patch.object(runner.requests, "post", return_value=response) as post,
              patch.dict(os.environ, {"OLLAMA_KEEP_ALIVE": "45m"})):
            result = runner._model_step("Explique a operação", [], [])
        self.assertEqual(result["action"], "answer")
        self.assertEqual(post.call_args.kwargs["json"]["keep_alive"], "45m")


class ChatBudgets(unittest.TestCase):
    @patch("src.agent.conversation.requests.post")
    def test_length_directives_change_output_budget_not_subject_words(self, post):
        post.return_value.__enter__.return_value.json.return_value = {
            "message": {"content": "Este é um resumo com contexto suficiente."}}
        texts = ["Responda só uma palavra", "Responda detalhadamente com um exemplo",
                 "O que acha dessa ideia de jogo?", "Como você organizaria uma lista?"]
        budgets = []
        for text in texts:
            self.assertIsNotNone(conversation.reply(text))
            budgets.append(post.call_args.kwargs["json"]["options"]["num_predict"])
        self.assertLess(budgets[0], budgets[2])
        self.assertGreater(budgets[1], budgets[2])
        self.assertEqual(budgets[2], budgets[3])
        self.assertEqual(post.call_count, len(texts))


if __name__ == "__main__":
    unittest.main()
