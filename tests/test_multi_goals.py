"""Regressões multidomínio do Chat A: alternância, retomada e permissões."""
import os
import tempfile
import unittest
from unittest.mock import patch

from src.agent import goal_context, intelligence, runner
from src.agent.tasks import TaskStore


def decision(goal, move="plan", relation=None, resume_goal_id=""):
    return {
        "move": move, "goal": goal,
        "reply": "Organizei etapas específicas para: " + goal,
        "question": "", "steps": ["Avaliar necessidades reais", "Validar uma implementação"],
        "acceptance": ["Resultado comprovado por teste"],
        "relation": relation, "resume_goal_id": resume_goal_id,
    }


class GoalTransitionsTests(unittest.TestCase):
    def test_independent_goals_pause_and_resume_exact_reference(self):
        first = goal_context.apply_plan({"phase": "idle"}, decision("Analisar documentos", relation="start"))
        second = goal_context.apply_plan(first, decision("Compor música", relation="switch"))
        self.assertNotEqual(first["goal_id"], second["goal_id"])
        self.assertEqual(second["goal"], "Compor música")
        self.assertEqual(second["paused_goals"][0]["goal"], "Analisar documentos")
        resumed = goal_context.apply_plan(
            second, decision("Retomar documentos", "continue", "resume", first["goal_id"]),
        )
        self.assertEqual(resumed["goal_id"], first["goal_id"])
        self.assertEqual(resumed["goal"], "Analisar documentos")
        self.assertEqual(resumed["paused_goals"][0]["goal"], "Compor música")
        self.assertEqual([x["kind"] for x in resumed["goal_decisions"]], ["start", "switch", "resume"])

    def test_forged_resume_id_does_not_change_goal_or_execute(self):
        active = goal_context.apply_plan({"phase": "idle"}, decision("Estudar sensores"))
        with self.assertRaises(goal_context.GoalReferenceError):
            goal_context.apply_plan(
                active, decision("Executar outro plano", "continue", "resume", "a" * 32),
            )
        self.assertEqual(active["goal"], "Estudar sensores")

    def test_refine_retains_identifier_and_pause_cap_is_bounded(self):
        active = goal_context.apply_plan({"phase": "idle"}, decision("Projeto inicial"))
        identifier = active["goal_id"]
        active = goal_context.apply_plan(active, decision("Projeto inicial atualizado", "continue", "refine"))
        self.assertEqual(active["goal_id"], identifier)
        for number in range(10):
            active = goal_context.apply_plan(active, decision(f"Projeto independente {number}", relation="switch"))
        self.assertEqual(len(active["paused_goals"]), goal_context.MAX_PAUSED)
        self.assertLessEqual(len(active["goal_decisions"]), goal_context.MAX_DECISIONS)

    def test_cancelling_goal_keeps_auditable_record(self):
        active = goal_context.apply_plan({"phase": "idle"}, decision("Montar robô"))
        cancelled = goal_context.abandon_active(active)
        self.assertEqual(cancelled["phase"], "idle")
        self.assertEqual(cancelled["paused_goals"][-1]["status"], "abandoned")
        self.assertEqual(cancelled["goal_decisions"][-1]["kind"], "abandon")


class GoalReasonerTests(unittest.TestCase):
    @patch("src.agent.intelligence.requests.post")
    def test_model_can_only_resume_a_real_goal_id(self, post):
        from test_intelligence import model_reply
        item = decision("Retomar documento", "continue", "resume", "a" * 32)
        post.return_value = model_reply(item)
        self.assertIsNone(intelligence.decide(
            "Volta para aquele outro plano", paused_goals=[{
                "id": "b" * 32, "goal": "Documento", "status": "paused",
            }],
        ))
        item["resume_goal_id"] = "b" * 32
        post.return_value = model_reply(item)
        result = intelligence.decide(
            "Volta para aquele outro plano", paused_goals=[{
                "id": "b" * 32, "goal": "Documento", "status": "paused",
            }],
        )
        self.assertEqual(result["resume_goal_id"], "b" * 32)

    def test_legacy_llm_decision_without_relation_keeps_existing_goal(self):
        first = goal_context.apply_plan({"phase": "idle"}, decision("Criar plataforma de testes"))
        update = decision("Criar plataforma com relatórios", "continue")
        update.pop("relation")
        current = goal_context.apply_plan(first, update)
        self.assertEqual(current["goal_id"], first["goal_id"])


class ToolSelectionContractTests(unittest.TestCase):
    @patch("src.agent.intelligence.requests.post")
    def test_model_can_select_only_catalog_tool_with_exact_arguments(self, post):
        from test_intelligence import model_reply
        proposal = {**decision("Listar projetos", move="act"),
                    "tool": "projects.list", "arguments": {}}
        post.return_value = model_reply(proposal)
        allowed = [{
            "name": "projects.list", "description": "Consulta projetos",
            "arguments": [], "writes": False,
        }]
        result = intelligence.decide("Mostra projetos", tools=allowed)
        self.assertEqual(result["tool"], "projects.list")
        proposal["tool"] = "shell.exec"
        post.return_value = model_reply(proposal)
        self.assertIsNone(intelligence.decide("Mostra projetos", tools=allowed))
        proposal["tool"] = "projects.list"
        proposal["arguments"] = {"command": "rm -rf /"}
        post.return_value = model_reply(proposal)
        self.assertIsNone(intelligence.decide("Mostra projetos", tools=allowed))

    @patch("src.agent.runner.perform")
    def test_readonly_tool_returns_receipt_without_approval(self, perform):
        perform.side_effect = [
            {"status": "planned", "tool": "projects.list"},
            {"status": "executed", "tool": "projects.list",
             "result": [{"name": "Estudos"}]},
        ]
        state, reply = runner._selected_tool("projects.list", {})
        self.assertEqual(state["phase"], "idle")
        self.assertEqual(reply["events"][0]["status"], "executed")
        self.assertIn("Estudos", reply["reply"])
        self.assertEqual(perform.call_count, 2)

    @patch("src.agent.runner.perform")
    def test_write_tool_needs_approval_and_cannot_execute_early(self, perform):
        perform.return_value = {"status": "planned", "tool": "projects.create"}
        state, reply = runner._selected_tool("projects.create", {"name": "Estudos"})
        self.assertEqual(state["phase"], "approval")
        self.assertIn("Posso executar?", reply["reply"])
        perform.assert_called_once_with("projects.create", {"name": "Estudos"}, dry_run=True)


class ConversationContinuityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher = patch.dict(os.environ, {
            "MENOR_DATA_DIR": temp.name, "MENOR_INTELLIGENCE_ENABLED": "1",
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        self.session = "multipleGoals01"

    @patch("src.agent.runner.intelligence.decide")
    def test_switch_and_resume_survive_restart_and_other_questions(self, think):
        think.side_effect = [
            decision("Ler PDFs e planilhas", relation="start"),
            decision("Criar música instrumental", relation="switch"),
            decision("Criar música instrumental", move="answer", relation="refine"),
            None,  # patched below before resume
        ]
        first = runner.run(self.session, "multiTurn001", "Quero analisar documentos", [], tasks=TaskStore())
        self.assertEqual(first["phase"], "goal")
        saved_first = TaskStore().inspect(self.session)
        second = runner.run(self.session, "multiTurn002", "Agora quero criar músicas", [], tasks=TaskStore())
        self.assertEqual(second["phase"], "goal")
        saved_second = TaskStore().inspect(self.session)
        self.assertEqual(saved_second["paused_goals"][0]["goal"], "Ler PDFs e planilhas")
        question = runner.run(self.session, "multiTurn003", "Explique formatos de áudio", [], tasks=TaskStore())
        self.assertTrue(question["handled"])
        self.assertEqual(TaskStore().inspect(self.session)["goal_id"], saved_second["goal_id"])
        think.side_effect = None
        think.return_value = decision(
            "Ler PDFs e planilhas", move="continue",
            relation="resume", resume_goal_id=saved_first["goal_id"],
        )
        resume = runner.run(
            self.session, "multiTurn004", "Retoma aquele plano de documentos", [], tasks=TaskStore(),
        )
        self.assertEqual(resume["phase"], "goal")
        self.assertEqual(TaskStore().inspect(self.session)["goal_id"], saved_first["goal_id"])
        self.assertEqual(len(TaskStore().inspect(self.session)["paused_goals"]), 1)
        self.assertEqual(len(TaskStore().inspect(self.session)["goal_decisions"]), 3)

    @patch("src.agent.runner.intelligence.decide")
    def test_missing_ollama_preserves_active_goal(self, think):
        think.side_effect = [decision("Cultivar horta"), None]
        runner.run(self.session, "multiTurn001", "Planeja minha horta", [], tasks=TaskStore())
        reply = runner.run(self.session, "multiTurn002", "Precisa ser offline", [], tasks=TaskStore())
        self.assertIn("Não consegui interpretar", reply["reply"])
        self.assertEqual(TaskStore().inspect(self.session)["goal"], "Cultivar horta")

    @patch("src.agent.runner.intelligence.decide")
    @patch("src.agent.runner.perform")
    def test_general_planning_never_invokes_tool(self, tool, think):
        think.return_value = decision("Construir protótipo de automação")
        runner.run(self.session, "multiTurn001", "Quero criar um robô", [], tasks=TaskStore())
        tool.assert_not_called()

    @patch("src.agent.runner._tool_loop")
    @patch("src.agent.runner.intelligence.decide")
    def test_approval_restores_active_goal_after_verified_tool_receipt(self, think, loop):
        think.side_effect = [
            decision("Criar um projeto de estudos", relation="start"),
            decision("Criar um projeto de estudos", move="act"),
        ]
        runner.run(self.session, "multiTurn001", "Vamos planejar projeto", [], tasks=TaskStore())
        first_state = TaskStore().inspect(self.session)
        loop.return_value = runner._answer(
            "Preciso de autorização", "approval",
            tool="projects.create", arguments={"name": "Estudos"},
        )
        pending = runner.run(self.session, "multiTurn002", "Pode começar a criar", [], tasks=TaskStore())
        self.assertEqual(pending["phase"], "approval")
        self.assertEqual(TaskStore().inspect(self.session)["return_goal"]["goal_id"],
                         first_state["goal_id"])
        with patch("src.agent.runner.perform", return_value={
            "tool": "projects.create", "status": "executed",
            "result": {"path": "projetos/estudos"},
        }) as perform:
            finished = runner.run(self.session, "multiTurn003", "eu aprovo", [], tasks=TaskStore())
            duplicate = runner.run(self.session, "multiTurn003", "eu aprovo", [], tasks=TaskStore())
        self.assertEqual(finished, duplicate)
        self.assertEqual(finished["phase"], "goal")
        self.assertEqual(TaskStore().inspect(self.session)["goal_id"], first_state["goal_id"])
        perform.assert_called_once_with("projects.create", {"name": "Estudos"}, dry_run=False)

    @patch("src.agent.runner._tool_loop")
    @patch("src.agent.runner.intelligence.decide")
    def test_rejecting_one_action_keeps_plan(self, think, loop):
        think.side_effect = [
            decision("Criar aplicativo", relation="start"),
            decision("Criar aplicativo", move="act"),
        ]
        runner.run(self.session, "multiTurn001", "Planejar aplicativo", [], tasks=TaskStore())
        loop.return_value = runner._answer(
            "Ação requer autorização", "approval",
            tool="projects.create", arguments={"name": "Aplicativo"},
        )
        runner.run(self.session, "multiTurn002", "Inicie trabalho", [], tasks=TaskStore())
        reply = runner.run(self.session, "multiTurn003", "não autorizo", [], tasks=TaskStore())
        self.assertEqual(reply["phase"], "goal")
        self.assertEqual(TaskStore().inspect(self.session)["goal"], "Criar aplicativo")

    @patch("src.agent.runner.research.handle", return_value={
        "reply": "Encontrei fontes públicas para avaliar alternativas.",
    })
    @patch("src.agent.runner.intelligence.decide")
    def test_public_research_does_not_erase_goal(self, think, research):
        think.side_effect = [
            decision("Automatizar jardim", relation="start"),
            decision("Automatizar jardim", move="research"),
        ]
        runner.run(self.session, "multiTurn001", "Planeja o jardim", [], tasks=TaskStore())
        answer = runner.run(self.session, "multiTurn002", "Pesquise fontes públicas", [], tasks=TaskStore())
        self.assertEqual(answer["phase"], "goal")
        self.assertIn("fontes públicas", answer["reply"])
        self.assertEqual(TaskStore().inspect(self.session)["goal"], "Automatizar jardim")

    @patch("src.agent.runner.intelligence.decide")
    def test_cancellation_does_not_erase_prior_goals(self, think):
        think.side_effect = [
            decision("Criar sistema de documentos"),
            decision("Criar laboratório de programação", relation="switch"),
        ]
        runner.run(self.session, "multiTurn001", "Criar leitor", [], tasks=TaskStore())
        runner.run(self.session, "multiTurn002", "Fazer novo laboratório", [], tasks=TaskStore())
        reply = runner.run(self.session, "multiTurn003", "cancela", [], tasks=TaskStore())
        self.assertEqual(reply["phase"], "idle")
        saved = TaskStore().inspect(self.session)
        self.assertEqual(len(saved["paused_goals"]), 2)
        self.assertEqual(saved["paused_goals"][-1]["status"], "abandoned")


if __name__ == "__main__":
    unittest.main()
