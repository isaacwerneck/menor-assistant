"""Chat A — revisão independente de planos, sem autorização por parecer."""
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.agent import plan_review, runner
from src.agent.tasks import TaskStore


def proposal(move="plan"):
    return {
        "move": move, "goal": "Analisar documentos do usuário",
        "reply": "Vou implementar um analisador de textos, tabelas e imagens.",
        "question": "" if move != "clarify" else "Qual formato é prioritário?",
        "steps": ["Ler dados de PDF e DOCX", "Testar extração com arquivos reais"]
                 if move != "clarify" else [],
        "acceptance": ["Respostas com fontes e páginas"],
        "relation": "start", "resume_goal_id": "",
        "tool": "", "arguments": {},
    }


def simulated_reply(value):
    response = MagicMock()
    response.__enter__.return_value = response
    response.json.return_value = {"message": {"content": json.dumps(value, ensure_ascii=False)}}
    return response


class CriticContractTests(unittest.TestCase):
    @patch("src.agent.plan_review.requests.post")
    def test_critic_considers_actual_task_not_fixed_domain(self, post):
        post.return_value = simulated_reply({
            "verdict": "revise",
            "issues": ["O plano produz imagens mas o pedido exige extração e interpretação."],
            "question": "",
        })
        result = plan_review.review(
            "Quero analisar imagens e planilhas",
            {**proposal(), "steps": ["Gerar imagens artificiais"]},
        )
        self.assertEqual(result["verdict"], "revise")
        args = post.call_args.kwargs["json"]
        data = json.loads(args["messages"][-1]["content"])
        self.assertIn("planilhas", data["message"])
        self.assertIn("Gerar imagens", data["steps"][0])
        self.assertEqual(args["format"], "json")

    @patch("src.agent.plan_review.requests.post")
    def test_short_followup_provides_previous_goal_to_critic(self, post):
        post.return_value = simulated_reply({
            "verdict": "ok", "issues": [], "question": "",
        })
        result = plan_review.review(
            "Também sem internet", proposal(),
            pending={"goal": "Criar analisador privado de documentos"},
        )
        self.assertEqual(result["verdict"], "ok")
        context = json.loads(post.call_args.kwargs["json"]["messages"][-1]["content"])
        self.assertEqual(context["pending_goal"], "Criar analisador privado de documentos")

    @patch("src.agent.plan_review.requests.post")
    def test_malformed_or_unavailable_verdict_has_no_authority(self, post):
        for reply in [
            {"verdict": "shell.exec", "issues": [], "question": ""},
            {"verdict": "revise", "issues": [], "question": ""},
            {"verdict": "clarify", "issues": [], "question": ""},
            {"verdict": "ok", "issues": ["x" * 250], "question": ""},
        ]:
            post.return_value = simulated_reply(reply)
            self.assertEqual(plan_review.review("Crie um app", proposal())["verdict"], "unavailable")
        post.side_effect = __import__("requests").Timeout()
        self.assertEqual(plan_review.review("Crie um app", proposal())["verdict"], "unavailable")

    def test_default_is_off_to_avoid_extra_cpu_cost(self):
        with patch.dict(os.environ, {"MENOR_PLAN_REVIEW_ENABLED": "0"}):
            self.assertFalse(plan_review.should_review(proposal()))
        with patch.dict(os.environ, {"MENOR_PLAN_REVIEW_ENABLED": "1"}):
            self.assertTrue(plan_review.should_review(proposal()))
            self.assertFalse(plan_review.should_review(proposal("act")))
            self.assertFalse(plan_review.should_review(proposal("answer")))


class CriticRunnerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = patch.dict(os.environ, {
            "MENOR_DATA_DIR": tmp.name, "MENOR_INTELLIGENCE_ENABLED": "1",
            "MENOR_PLAN_REVIEW_ENABLED": "1",
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tasks = TaskStore()
        self.session = "criticConversation01"

    @patch("src.agent.runner.plan_review.review", return_value={
        "verdict": "revise",
        "issues": ["Foi proposto gerar imagem em vez de analisar o conteúdo."],
        "question": "",
    })
    @patch("src.agent.runner.intelligence.decide")
    @patch("src.agent.runner.perform")
    def test_reviser_repairs_wrong_domain_without_running_tool(self, tool, decide, review):
        wrong = {**proposal(), "reply": "Vou gerar imagens com modelo difusor.",
                 "steps": ["Gerar uma imagem em vez de analisar o conteúdo"]}
        correct = proposal()
        decide.side_effect = [wrong, correct]
        result = runner.run(
            self.session, "criticTurn001",
            "Crie ferramenta que leia PDFs e planilhas", [], tasks=self.tasks,
        )
        self.assertEqual(result["phase"], "goal")
        self.assertEqual(result["plan_review_status"], "revised_unverified")
        self.assertIn("Ler dados de PDF", result["reply"])
        self.assertNotIn("modelo difusor", result["reply"])
        self.assertIn("review_issues", decide.call_args.kwargs)
        self.assertEqual(self.tasks.inspect(self.session)["plan_review_status"], "revised_unverified")
        review.assert_called_once()
        tool.assert_not_called()

    @patch("src.agent.runner.plan_review.review", return_value={
        "verdict": "clarify", "issues": [],
        "question": "Quais formatos você precisa analisar primeiro?",
    })
    @patch("src.agent.runner.intelligence.decide", return_value=proposal())
    def test_critic_asks_one_question_before_storing_goal(self, decide, review):
        result = runner.run(self.session, "criticTurn001", "Criar leitor universal", [], tasks=self.tasks)
        self.assertEqual(result["phase"], "goal")
        self.assertIn("formatos", result["reply"])
        self.assertEqual(result["plan_review_status"], "needs_clarification")
        self.assertEqual(self.tasks.inspect(self.session)["question"],
                         "Quais formatos você precisa analisar primeiro?")
        review.assert_called_once()

    @patch("src.agent.runner.plan_review.review", return_value={
        "verdict": "unavailable", "issues": [], "question": "",
    })
    @patch("src.agent.runner.intelligence.decide", return_value=proposal())
    def test_when_offline_draft_is_labeled_without_tool_calls(self, decide, review):
        result = runner.run(self.session, "criticTurn001", "Criar um leitor", [], tasks=self.tasks)
        self.assertEqual(result["plan_review_status"], "unavailable")
        self.assertIn("revisão independente indisponível", result["reply"])

    @patch("src.agent.runner.plan_review.review", return_value={
        "verdict": "revise", "issues": ["Este plano não tem testes específicos"], "question": "",
    })
    @patch("src.agent.runner.intelligence.decide")
    def test_only_one_revision_attempt_and_invalid_tool_never_runs(self, decide, review):
        decide.side_effect = [
            proposal(), {
                **proposal("act"), "tool": "projects.create",
                "arguments": {"name": "teste"},
            },
        ]
        with patch("src.agent.runner.perform") as tool:
            result = runner.run(self.session, "criticTurn001", "Criar analisador", [], tasks=self.tasks)
        self.assertEqual(result["phase"], "goal")
        self.assertEqual(result["plan_review_status"], "revise")
        self.assertIn("inconsistências", result["reply"])
        self.assertEqual(decide.call_count, 2)
        tool.assert_not_called()

    @patch("src.agent.runner.plan_review.review")
    @patch("src.agent.runner.intelligence.decide", return_value=proposal("answer"))
    def test_critic_never_runs_on_simple_answers(self, decide, review):
        result = runner.run(self.session, "criticTurn001", "O que é JSON?", [], tasks=self.tasks)
        self.assertTrue(result["handled"])
        review.assert_not_called()


if __name__ == "__main__":
    unittest.main()
