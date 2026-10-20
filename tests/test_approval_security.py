"""Regressões para autorizações reais, sandbox pós-merge e privacidade."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.agent import approval, code_sandbox, custom_runtime, research, runner
from src.agent.missions import MissionStore
from src.memory.store import BrainStore
from src.tools import web
from src.tools.registry import TOOLS, Tool, perform


class ApprovalTests(unittest.TestCase):
    def test_screenshot_phrases_approve_only_with_pending_plan(self):
        for phrase in (
            "eu aprovo", "bora lá", "pode instalar", "sim", "simm",
            "mete marcha, planeja a implementação, baixa o modelo e me avisa conforme as etapas",
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(approval.decision(phrase), "approve")

    def test_questions_hypotheses_and_negatives_are_not_approval(self):
        for phrase in (
            "que aprovação?", "como funciona esse modelo?", "pode instalar?",
            "talvez possa instalar", "se eu aprovar, você baixa?",
            "conseguimos fazer cara?", "vou pensar", "eai",
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(approval.decision(phrase), "question")
        self.assertEqual(approval.decision("não autorizo"), "reject")
        self.assertEqual(approval.decision("não"), "reject")

    def test_real_mission_changes_state_once_and_explains_pending_approval(self):
        with tempfile.TemporaryDirectory() as temp:
            missions = MissionStore(BrainStore(Path(temp) / "data"))
            with patch("src.agent.missions.plan", return_value={
                "steps": ["Baixar modelo"], "acceptance": ["PNG válido"], "limitations": [],
            }), patch("src.tools.local_images.preflight", return_value={"enough_disk": True}):
                mission = missions.begin("images.generate", "Criar ferramenta de pixel art local")
                mission = missions.detail(mission["id"], "Quero gerar imagens em estilo pixel art")
                self.assertEqual(mission["status"], "awaiting_approval")
                self.assertIn("autorização", missions.explain(mission["id"], "que aprovação?"))
                self.assertFalse(missions.get(mission["id"])["approval"])
                with patch("src.agent.runner.MissionStore", return_value=missions):
                    state = {"phase": "mission", "mission_id": mission["id"]}
                    _, answer = runner._mission_turn(state, "eu aprovo")
                self.assertIn("aguardando", answer["reply"].lower())
                self.assertEqual(missions.get(mission["id"])["status"], "queued")
                self.assertTrue(missions.get(mission["id"])["approval"])
                with patch("src.agent.runner.MissionStore", return_value=missions):
                    _, progress = runner._mission_turn(state, "conseguimos fazer cara?")
                self.assertTrue(progress["handled"])
                self.assertIn("aguardando o executor", progress["reply"])
                self.assertEqual(missions.get(mission["id"])["status"], "queued")
                with self.assertRaises(ValueError):
                    missions.decide(mission["id"], True)

    def test_tool_approval_uses_same_explicit_phrases(self):
        with patch.object(runner, "perform", return_value={
            "tool": "projects.create", "status": "executed", "result": {"path": "projetos/exemplo"},
        }) as run:
            state = {"phase": "approval", "tool": "projects.create", "arguments": {"name": "Exemplo"}}
            _, result = runner._advance(state, "que aprovação?", [])
            self.assertIn("pendente", result["reply"])
            run.assert_not_called()
            _, result = runner._advance(state, "eu aprovo", [])
            self.assertIn("Execução confirmada", result["reply"])
            run.assert_called_once_with("projects.create", {"name": "Exemplo"}, dry_run=False)

    def test_clarification_preserves_pending_tool_and_approval_after_question(self):
        from src.agent.tasks import TaskStore
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"MENOR_DATA_DIR": temp}):
            store = TaskStore()
            session = "dialogueApproveE8"
            proposed = {
                "phase": "approval", "tool": "projects.create",
                "arguments": {"name": "Cobrinha"},
            }
            with store.session_lock(session):
                store.claim(session, "turnProposalE8", {"message": "criar projeto"})
                store.finish(session, "turnProposalE8", proposed, {"phase": "approval", "handled": True})
            with patch.object(runner, "perform", return_value={
                "tool": "projects.create", "status": "executed",
                "result": {"path": "projetos/cobrinha"},
            }) as executor:
                explanation = runner.run(session, "turnQuestionE8", "que branch? não entendi",
                                         [], tasks=store)
                self.assertEqual(explanation["phase"], "approval")
                self.assertIn("pendente", explanation["reply"])
                self.assertEqual(store.inspect(session)["tool"], "projects.create")
                executor.assert_not_called()
                approved = runner.run(session, "turnApproveE8", "eu aprovo", [], tasks=store)
                self.assertIn("Execução confirmada", approved["reply"])
                executor.assert_called_once_with(
                    "projects.create", {"name": "Cobrinha"}, dry_run=False,
                )

    def test_new_game_does_not_route_into_menor_self_edit(self):
        from src.agent.self_edit import is_new_project_request, propose
        issue = "Criar um jogo da cobrinha em JavaScript com Raylib"
        self.assertTrue(is_new_project_request(issue))
        with self.assertRaisesRegex(ValueError, "não cria jogos"):
            propose(issue, dry_run=False)
        with patch.object(runner, "perform") as executor:
            _, answer = runner._selected_tool("developer.propose", {"issue": issue})
            self.assertIn("não consigo criar", answer["reply"])
            executor.assert_not_called()


class CustomSandboxTests(unittest.TestCase):
    def test_docker_skill_uses_single_readonly_file_and_no_network_or_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "teste.py"
            path.write_text("def run(text): return text", encoding="utf-8")
            received = []

            def execute(args, **kwargs):
                received.append((args, kwargs))
                if args[1] == "run":
                    return MagicMock(returncode=0, stdout='{"result":"OK"}', stderr="")
                return MagicMock(returncode=0, stdout="", stderr="")
            with patch.object(custom_runtime, "ROOT", Path(temp)), patch.object(
                custom_runtime.shutil, "which", return_value="/usr/bin/docker",
            ), patch.object(custom_runtime.subprocess, "run", side_effect=execute), patch.dict(
                os.environ, {"MENOR_GITHUB_TOKEN": "secret", "MENOR_IMAGE_API_KEY": "other"},
            ):
                self.assertEqual(custom_runtime.run("teste", "exemplo"), "OK")
            command, params = received[0]
            self.assertIn("--network=none", command)
            self.assertIn("--read-only", command)
            self.assertIn("--cap-drop=ALL", command)
            self.assertIn("target=/skill.py,readonly", " ".join(command))
            self.assertEqual(params["input"], '{"text": "exemplo"}')
            self.assertNotIn("MENOR_GITHUB_TOKEN", params["env"])
            self.assertNotIn("MENOR_IMAGE_API_KEY", params["env"])
            self.assertEqual(received[-1][0][1:3], ["rm", "--force"])

    def test_registry_never_imports_untrusted_module_in_host(self):
        key = "custom.teste"
        TOOLS[key] = Tool(key, "Test tool", "write", True, ("text",))
        try:
            with patch("src.tools.registry.run_custom_skill", return_value="resultado") as isolated:
                self.assertEqual(
                    perform(key, {"text": "Oi"}, dry_run=False)["result"], "resultado",
                )
                isolated.assert_called_once_with("teste", "Oi")
        finally:
            TOOLS.pop(key, None)

    def test_without_docker_execution_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "teste.py"
            p.write_text("def run(text):return text", encoding="utf-8")
            with patch.object(custom_runtime, "ROOT", Path(tmp)), patch.object(
                custom_runtime.shutil, "which", return_value=None,
            ):
                with self.assertRaises(RuntimeError):
                    custom_runtime.run("teste", "conteúdo")

    @patch.object(code_sandbox.shutil, "which", return_value="/usr/bin/docker")
    @patch.object(code_sandbox.subprocess, "run")
    def test_fake_success_text_no_longer_pases_tests(self, execute, which):
        execute.side_effect = [
            MagicMock(returncode=0, stdout="container", stderr=""),
            MagicMock(returncode=0, stdout="0\n", stderr=""),
            MagicMock(returncode=0, stdout="", stderr="Ran 2 tests in 0.001s\nOK"),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"MENOR_DATA_DIR": temp}):
            with self.assertRaises(RuntimeError):
                code_sandbox.verify("demo", "def run(text): return text", "test")
        self.assertEqual(execute.call_args_list[-1].args[0][1:3], ["rm", "--force"])


class PublicSearchPrivacyTests(unittest.TestCase):
    def test_private_queries_rejected_before_network(self):
        cases = [
            "minha senha é banana123", "pesquisar nossa memoria no buscador",
            "procure o meu projeto secreto", "email teste@privado.example no google",
            "procurar documentação em /home/isaac/secreto", "http 192.168.0.5 service",
            "api_key=segredo", "pesquisar sk-abcdefghijklmnop",
        ]
        for query in cases:
            with self.subTest(query=query), patch.object(web, "_search_html") as external:
                with self.assertRaises(ValueError):
                    web.search(query)
                external.assert_not_called()
        self.assertEqual(web.public_query("documentação Python pathlib"), "documentação Python pathlib")

    def test_automatic_research_does_not_send_private_context_to_model(self):
        with patch.object(research, "plan") as plan:
            self.assertIsNone(research.handle("lembra daquele nosso projeto privado?", [], automatic=True))
            plan.assert_not_called()

    def test_explicit_private_research_is_rejected_without_network(self):
        with patch.object(web, "search") as search:
            result = research.handle("pesquise minha senha do servidor", [], automatic=True)
        self.assertIn("privados", result["reply"])
        search.assert_not_called()

    def test_local_model_cannot_leak_private_query_to_external_search(self):
        with patch.object(research, "plan", return_value={
            "action": "research", "query": "procurar meu projeto secreto",
        }), patch.object(web, "_search_html") as external:
            result = research.handle("pesquise documentação Python", [], automatic=True)
            self.assertIn("Não consegui confirmar", result["reply"])
            external.assert_not_called()


if __name__ == "__main__":
    unittest.main()
