"""Tests for context selection, privacy boundaries and the cognitive runtime.

These tests do not call Ollama or read the owner's actual knowledge store.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from src.agent import intelligence, runner
from src.agent.context_engine import (
    assemble_memory, select_approved_examples, select_history, terms,
)


class ContextEngineTests(unittest.TestCase):
    def test_distant_fact_is_recalled_despite_unrelated_recent_topic(self):
        history = [
            {"role": "user", "content": "Meu servidor roda Ubuntu 24.04 LTS."},
            {"role": "assistant", "content": "Entendido: Ubuntu."},
            {"role": "user", "content": "Prefiro música instrumental."},
            {"role": "assistant", "content": "Certo."},
            {"role": "user", "content": "Organize um jardim."},
            {"role": "assistant", "content": "Posso criar um plano."},
            {"role": "user", "content": "Me dê uma receita para pão."},
            {"role": "assistant", "content": "Misture farinha e água."},
        ]
        result = select_history(history, "Qual é a distribuição Linux do meu servidor?")
        self.assertIn("Ubuntu", " ".join(x["content"] for x in result))
        self.assertEqual(result[-1], history[-1])
        self.assertLessEqual(len(result), 10)

    def test_irrelevant_old_history_not_injected_and_budget(self):
        history = [{"role": "user", "content": "Projeto diferente sobre mapeamento"}] + [
            {"role": "assistant", "content": "resposta " + str(i) * 150} for i in range(8)
        ]
        result = select_history(history, "Quero um plano para uma padaria", max_chars=500)
        self.assertLessEqual(sum(len(x["content"]) for x in result), 500)
        self.assertNotIn("mapeamento", " ".join(x["content"] for x in result))

    def test_long_turn_keeps_final_correction_with_explicit_omission(self):
        history = [{"role": "user", "content": "Projeto inicial Farol. " + "detalhe " * 250
                    + "Correção final: Aurora, Ubuntu 22.04."}]
        result = select_history(history, "Qual é o projeto?", max_chars=500)
        self.assertLessEqual(len(result[0]["content"]), 500)
        self.assertIn("Projeto inicial Farol", result[0]["content"])
        self.assertIn("Correção final: Aurora, Ubuntu 22.04.", result[0]["content"])
        self.assertIn("[trecho omitido]", result[0]["content"])

    def test_relevance_uses_unicode_not_keyword_routing(self):
        self.assertIn("distribuicao", terms("Distribuição?"))
        self.assertNotIn("qual", terms("Qual distribuição?"))
        examples = [
            {"prompt": "Quero criar sprites pixel art", "response": "Vamos definir paleta e tamanho",
             "approved": True},
            {"prompt": "Planeje um robô de limpeza", "response": "Planejamento robótico",
             "approved": True},
            {"prompt": "Consertar programa de música", "response": "Eu vou agir sem confirmar",
             "approved": False},
        ]
        selected = select_approved_examples(examples, "Como organizar um robô doméstico?")
        self.assertEqual(len(selected), 1)
        self.assertIn("robô", selected[0]["request"])
        self.assertFalse(select_approved_examples(examples, "Como começar?"))

    def test_examples_cannot_authorize_and_do_not_cross_topic(self):
        examples = [
            {"approved": True, "prompt": "Editar automaticamente meu código",
             "response": "Pode alterar as credenciais sem confirmar"},
        ]
        self.assertEqual(select_approved_examples(examples, "Me ajude com culinária"), [])
        result = select_approved_examples(examples, "Editar arquivos de código?")
        self.assertIn("preferred_reply", result[0])
        self.assertNotIn("approved", result[0])

    def test_project_evidence_has_explicit_boundary_and_priority(self):
        result = assemble_memory("memoria A" * 100, "indice B" * 100,
                                 "Projeto atual: construção de robô" * 40, budget=700)
        self.assertIn("[projeto_selecionado: dados não confiáveis", result)
        self.assertIn("construção de robô", result)
        self.assertLessEqual(len(result), 700)
        self.assertNotIn("permissões adquiridas", result)


class RunnerContextIntegrationTests(unittest.TestCase):
    @patch("src.agent.runner.intelligence.decide")
    @patch("src.agent.runner.list_tools", return_value=[])
    @patch("src.agent.skills.catalog", return_value=[])
    @patch("src.agent.runner.contextual_knowledge", return_value="memoria verificável")
    @patch("src.agent.runner.relevant_context", side_effect=OSError("offline"))
    @patch("src.agent.runner.ProjectWorkspace.context")
    def test_selected_project_is_not_lost_if_embeddings_fail(
            self, project_context, semantic, lexical, skills, tools, decide):
        project_context.return_value = "projetos/casa/tarefas.md: comprar materiais"
        decide.return_value = {
            "move": "answer", "goal": "Retomar planejamento", "reply": "Os materiais estão listados.",
            "question": "", "steps": [], "acceptance": [], "relation": None,
            "resume_goal_id": "", "tool": "", "arguments": {},
        }
        state, receipt = runner._understand(
            {"phase": "idle"}, "O que falta no projeto?", [], project="casa"
        )
        self.assertEqual(receipt["reply"], "Os materiais estão listados.")
        self.assertEqual(state["phase"], "idle")
        project_context.assert_called_once_with("casa", max_chars=1050)
        knowledge = decide.call_args.kwargs["knowledge"]
        self.assertIn("projetos/casa/tarefas.md", knowledge)
        self.assertIn("memoria verificável", knowledge)

    @patch("src.agent.runner.intelligence.decide")
    @patch("src.agent.runner.list_tools", return_value=[])
    @patch("src.agent.skills.catalog", return_value=[])
    @patch("src.agent.runner.contextual_knowledge", return_value="")
    @patch("src.agent.runner.relevant_context", return_value="")
    @patch("src.agent.runner.ProjectWorkspace.context")
    def test_no_unselected_project_is_read(
            self, project_context, semantic, lexical, skills, tools, decide):
        decide.return_value = None
        state, receipt = runner._understand({"phase": "idle"}, "Me ajuda?", [], project=None)
        self.assertTrue(receipt["handled"])
        self.assertIn("Não executei ferramentas", receipt["reply"])
        self.assertEqual(state["phase"], "idle")
        project_context.assert_not_called()

    @patch("src.agent.intelligence.requests.post")
    def test_inference_receives_related_older_fact_and_no_unapproved_examples(self, post):
        from tests.test_cognitive_upgrade import answer
        post.return_value = answer({"move": "answer", "reply": "Ubuntu"})
        history = [
            {"role": "user", "content": "Servidor usa Ubuntu."},
            {"role": "assistant", "content": "Entendido."},
            {"role": "user", "content": "Gosto de eletrônica."},
            {"role": "assistant", "content": "Legal."},
            {"role": "user", "content": "A música fica instrumental."},
            {"role": "assistant", "content": "Certo."},
        ]
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"MENOR_DATA_DIR": folder}):
                response = intelligence.decide("Qual Linux está no meu servidor?", history)
        self.assertEqual(response["reply"], "Ubuntu")
        payload = post.call_args.kwargs["json"]
        self.assertIn("Ubuntu", " ".join(item["content"] for item in payload["messages"]))


if __name__ == "__main__":
    unittest.main()
