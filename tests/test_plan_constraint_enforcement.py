"""Regression checks for explicit constraints before persisting the Menor's plans.

These do not execute Ollama or system tools and keep live data outside the suite.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from src.agent import plan_constraints, runner
from src.agent.tasks import TaskStore


def proposal(goal="Organizar documentos", steps=None, relation="start"):
    return {
        "move": "plan", "goal": goal, "reply": "Plano proposto.",
        "question": "", "steps": steps or ["Inventariar arquivos e validar itens"],
        "acceptance": ["Inventário pronto e conferido"],
        "relation": relation, "resume_goal_id": "",
    }


class RestrictionsTests(unittest.TestCase):
    def test_prohibition_matches_multiple_actions_and_accents(self):
        request = "Quero identificar duplicados sem apagar, substituir ou mover nenhum arquivo."
        steps = ["Apagar os repetidos", "Substituir originais", "Mover os demais"]
        self.assertEqual(len(plan_constraints.warnings(request, steps)), 3)

    def test_read_only_and_explicit_negation_are_not_flagged(self):
        request = "Identifique duplicatas sem apagar, substituir ou mover arquivo algum."
        steps = ["Comparar hashes sem alterar originais", "Não apagar nem mover nenhum arquivo"]
        self.assertEqual(plan_constraints.warnings(request, steps), [])

    def test_file_prohibition_not_diluted_by_previous_negation(self):
        request = "Organize minha pasta sem apagar ou mover arquivo algum."
        steps = ["Não apagar nenhum arquivo; mover os repetidos para outra pasta"]
        problems = plan_constraints.warnings(request, steps)
        self.assertTrue(any("mover" in problem for problem in problems), problems)

    def test_no_change_request_covers_positive_file_mutations(self):
        request = "Faça apenas uma análise; não mexer em nada."
        steps = ["Editar os documentos", "Transferir os arquivos", "Excluir duplicatas"]
        self.assertGreaterEqual(len(plan_constraints.warnings(request, steps)), 3)

    def test_negative_stage_in_request_is_not_mistaken_for_required_deploy(self):
        request = "Planeje o layout de um app, sem fazer deploy agora."
        self.assertNotIn("deploy", " ".join(plan_constraints.required_stage_warnings(
            request, ["Definir layout da tela"])) )

    def test_required_steps_not_satisfied_by_acceptance_or_negative_mentions(self):
        request = "Planeje migrar com backup, rollback, testes e autorização antes da mudança."
        steps = ["Mapear dados existentes", "Não executar backup nem rollback"]
        missing = plan_constraints.required_stage_warnings(request, steps)
        self.assertTrue(any("backup" in item for item in missing), missing)
        self.assertTrue(any("rollback" in item for item in missing), missing)
        self.assertTrue(any("autorização" in item for item in missing), missing)
        self.assertTrue(any("testes" in item for item in missing), missing)

    def test_deploy_must_be_explicit_in_steps(self):
        request = "Criar site com acessibilidade, testes e deploy."
        warnings = plan_constraints.required_stage_warnings(
            request, ["Projetar a interface", "Criar testes funcionais"])
        self.assertTrue(any("deploy" in item for item in warnings))
        self.assertTrue(any("acessibilidade" in item for item in warnings))
        safe = ["Planejar acessibilidade", "Criar testes", "Executar deploy e verificar acesso"]
        self.assertFalse(plan_constraints.required_stage_warnings(request, safe))


class AgentPlanIntegrityTests(unittest.TestCase):
    def setUp(self):
        data = tempfile.TemporaryDirectory()
        self.addCleanup(data.cleanup)
        env = patch.dict(os.environ, {
            "MENOR_DATA_DIR": data.name,
            "MENOR_INTELLIGENCE_ENABLED": "1",
            "MENOR_PLAN_REVIEW_ENABLED": "0",
        })
        env.start()
        self.addCleanup(env.stop)
        self.tasks = TaskStore()
        self.session = "planIntegrity01"

    def run_with(self, response, message, turn="turn0001"):
        with (
            patch.object(runner.intelligence, "decide", return_value=response),
            patch.object(runner, "relevant_context", return_value=""),
            patch.object(runner, "contextual_knowledge", return_value=""),
            patch.object(runner, "perform") as action,
            patch.object(runner.plan_review, "review") as review,
        ):
            result = runner.run(self.session, turn, message, [], tasks=self.tasks)
            action.assert_not_called()
            review.assert_not_called()
            return result

    def test_unsafe_plan_does_not_create_goal(self):
        proposed = proposal(steps=["Listar arquivos", "Mover os originais", "Excluir duplicatas"])
        result = self.run_with(proposed, "Liste arquivos sem apagar nem mover os originais.")
        self.assertEqual(result["plan_review_status"], "constraint_warning")
        self.assertEqual(result["phase"], "idle")
        self.assertIn("revisão", result["reply"])
        self.assertTrue(result["plan_warnings"])
        self.assertNotEqual(self.tasks.inspect(self.session).get("phase"), "goal")

    def test_rejected_refinement_preserves_existing_goal_and_steps(self):
        safe = proposal(steps=["Inventariar os arquivos", "Comparar hashes"])
        initial = self.run_with(safe, "Quero organizar documentos sem apagar nada.")
        self.assertEqual(initial["phase"], "goal")
        before = self.tasks.inspect(self.session)
        bad = proposal("Organizar documentos", ["Excluir os arquivos repetidos"], "refine")
        result = self.run_with(bad, "Continue sem apagar arquivos.", turn="turn0002")
        self.assertEqual(result["phase"], "goal")
        self.assertEqual(result["plan_review_status"], "constraint_warning")
        after = self.tasks.inspect(self.session)
        self.assertEqual(after["goal_id"], before["goal_id"])
        self.assertEqual(after["steps"], before["steps"])
        self.assertNotIn("Excluir", " ".join(after["steps"]))

    def test_revised_plan_is_checked_again_without_extra_revision(self):
        safe = proposal(steps=["Listar documentos", "Comparar hashes"])
        unsafe = proposal(steps=["Mover arquivos originais", "Comparar hashes"])
        with (
            patch.dict(os.environ, {"MENOR_PLAN_REVIEW_ENABLED": "1"}),
            patch.object(runner.intelligence, "decide", side_effect=[safe, unsafe]) as decide,
            patch.object(runner.plan_review, "review", return_value={
                "verdict": "revise", "issues": ["Plano não cobre auditoria"], "question": "",
            }) as review,
            patch.object(runner, "relevant_context", return_value=""),
            patch.object(runner, "contextual_knowledge", return_value=""),
            patch.object(runner, "perform") as tool,
        ):
            result = runner.run(
                self.session, "turn0001", "Sem mover arquivos, analise duplicatas.",
                [], tasks=self.tasks,
            )
        self.assertEqual(decide.call_count, 2)
        review.assert_called_once()
        tool.assert_not_called()
        self.assertEqual(result["plan_review_status"], "constraint_warning")
        self.assertEqual(result["phase"], "idle")
        self.assertNotEqual(self.tasks.inspect(self.session).get("phase"), "goal")


if __name__ == "__main__":
    unittest.main()
