"""E14: o roteamento é semântico e ferramentas têm escopo de produto."""
import os
import tempfile
import unittest
from unittest.mock import patch

from src.agent import runner
from src.agent.tasks import TaskStore
from src.tools.registry import list_tools


class SemanticAgentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {
            "MENOR_DATA_DIR": temp.name,
            "MENOR_INTELLIGENCE_ENABLED": "1",
            "MENOR_AGENT_SCOPE": "personal",
        })
        env.start()
        self.addCleanup(env.stop)
        self.tasks = TaskStore()

    def run_turn(self, question, index=1, project=None):
        return runner.run("semanticSession01", "semanticTurn" + str(index),
                          question, [], project=project, tasks=self.tasks)

    def test_same_semantic_intent_different_subjects_no_tool_called(self):
        for index, message in enumerate((
            "Tive uma ideia de jogo cooperativo para web",
            "Tô pensando em fazer um aplicativo para anotar minhas finanças",
            "Queria desenvolver um documento pra organizar nossa viagem",
            "Quero planejar uma loja virtual, mas ainda nem sei o que vender",
        ), 1):
            with (self.subTest(message=message),
                  patch.object(runner.intelligence, "decide", return_value={
                      "move": "answer", "reply": "Boa ideia. Me conta mais do objetivo.",
                      "relation": "switch", "steps": [], "acceptance": [],
                  }) as decide,
                  patch.object(runner, "perform") as perform):
                result = self.run_turn(message, index)
                self.assertEqual(result["phase"], "idle")
                self.assertIn("conta mais", result["reply"])
                decide.assert_called_once()
                names = [t["name"] for t in decide.call_args.kwargs["tools"]]
                self.assertNotIn("developer.propose", names)
                self.assertNotIn("developer.build", names)
                self.assertIn("projects.create", names)
                self.assertIn("projects.code.webapp", names)
                perform.assert_not_called()

    def test_explicit_action_infers_tool_from_model_not_verb_list(self):
        model = {
            "move": "act", "reply": "Preparar arquivos",
            "tool": "projects.code.webapp",
            "arguments": {"slug": "meu-projeto", "goal": "Criar jogo em JavaScript Canvas"},
        }
        with (patch.object(runner.intelligence, "decide", return_value=model),
              patch.object(runner, "perform", return_value={"status": "planned"}) as perform):
            result = self.run_turn("Agora pode tocar a implementação que combinamos",
                                   project="meu-projeto")
        self.assertEqual(result["phase"], "approval")
        self.assertEqual(result["approval"]["title"], "Gerar aplicativo web inicial")
        perform.assert_called_once_with("projects.code.webapp", model["arguments"], dry_run=True)

    def test_wrong_self_modification_from_model_is_rejected_without_approval(self):
        model = {
            "move": "act", "reply": "Vou preparar PR",
            "tool": "developer.propose",
            "arguments": {"issue": "Ajustar pipeline para app externo"},
        }
        with (patch.object(runner.intelligence, "decide", return_value=model),
              patch.object(runner, "perform") as perform,
              patch.object(runner.conversation, "reply",
                           return_value="Vamos discutir primeiro os detalhes desse projeto."),
              patch.dict(os.environ, {"MENOR_SECONDARY_INFERENCE_ENABLED": "1"})):
            result = self.run_turn("Quero desenvolver uma ideia de aplicativo")
        self.assertEqual(result["phase"], "idle")
        self.assertNotIn("approval", result)
        self.assertIn("discutir primeiro", result["reply"])
        perform.assert_not_called()

    def test_tools_are_scoped_by_operator_not_words(self):
        self.assertNotIn("developer.propose", [t["name"] for t in runner._agent_tools()])
        with patch.dict(os.environ, {"MENOR_AGENT_SCOPE": "maintenance"}):
            self.assertIn("developer.propose", [t["name"] for t in runner._agent_tools()])
            self.assertIn("developer.build", [t["name"] for t in runner._agent_tools()])
        with patch.dict(os.environ, {"MENOR_AGENT_SCOPE": "invalid"}):
            self.assertNotIn("developer.propose", [t["name"] for t in runner._agent_tools()])
        self.assertIn("developer.propose", [t["name"] for t in list_tools()])
        self.assertNotIn("developer.propose", [t["name"] for t in list_tools("personal")])
        with self.assertRaises(ValueError):
            list_tools("untrusted")


if __name__ == "__main__":
    unittest.main()
