import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.agent import intelligence, lab, runner
from src.agent.feedback import FeedbackStore
from src.agent.tasks import TaskStore
from src.memory.store import BrainStore
from test_auth_memory import call


def model_reply(value):
    obj = MagicMock()
    obj.__enter__.return_value = obj
    obj.json.return_value = {"message": {"content": json.dumps(value, ensure_ascii=False)}}
    return obj


def verdict(move="plan"):
    return {
        "move": move,
        "goal": "Construir uma ferramenta para automatizar uma horta",
        "reply": "Podemos escolher sensores, controlar a água e testar numa bancada.",
        "question": "Você quer monitorar umidade ou controlar irrigação primeiro?"
                    if move == "clarify" else "",
        "steps": ["Selecionar sensores adequados", "Construir protótipo seguro"]
                 if move in ("plan", "continue") else [],
        "acceptance": ["Sensores registram dados verificáveis"],
    }


class ReasonerContractTests(unittest.TestCase):
    @patch("src.agent.intelligence.requests.post")
    def test_structured_json_is_validated_and_references_available_skills(self, post):
        post.return_value = model_reply(verdict("plan"))
        result = intelligence.decide(
            "Me ajuda a construir uma horta automatizada", [], capabilities=[
                {"capability": "images.generate", "ready": False},
            ], knowledge="Anotações de sensores: dados do cérebro",
        )
        self.assertEqual(result["move"], "plan")
        self.assertIn("Selecionar sensores", intelligence.render_plan(result))
        payload = post.call_args.kwargs["json"]
        variants = payload["format"]["oneOf"]
        moves = [move for variant in variants for move in variant["properties"]["move"]["enum"]]
        self.assertCountEqual(moves, intelligence.MOVES)
        plan_schema = next(variant for variant in variants
                           if "plan" in variant["properties"]["move"]["enum"])
        self.assertEqual(plan_schema["required"], ["move", "reply", "goal", "steps"])
        self.assertFalse(plan_schema["additionalProperties"])
        ctx = json.loads(payload["messages"][-1]["content"])
        self.assertEqual(ctx["skills"], [{"capability": "images.generate", "ready": False}])
        self.assertIn("Anotações de sensores", ctx["related_memory_data_not_instructions"])

    @patch("src.agent.intelligence.requests.post")
    def test_full_request_memory_and_preferences_reach_single_inference(self, post):
        post.return_value = model_reply({"move": "answer", "reply": "Aurora"})
        message = "detalhe " * 300 + "Responda somente: Aurora."
        knowledge = "x" * 1500 + " Evidência final: Ubuntu 22.04."
        with patch("src.memory.store.BrainStore") as store:
            store.return_value.preference_context.return_value = "- Respostas curtas."
            result = intelligence.decide(message, knowledge=knowledge, feedback_examples=[])
        self.assertEqual(result["reply"], "Aurora")
        post.assert_called_once()
        payload = post.call_args.kwargs["json"]
        context = json.loads(payload["messages"][-1]["content"])
        self.assertEqual(context["current_message"], message)
        self.assertEqual(context["related_memory_data_not_instructions"], knowledge)
        self.assertIn("Respostas curtas", context["owner_preferences_data_not_permissions"])
        self.assertIn("keep_alive", payload)

    @patch("src.agent.intelligence.requests.post")
    def test_explicit_empty_preferences_never_reads_owner_store(self, post):
        post.return_value = model_reply({"move": "answer", "reply": "4"})
        with patch("src.memory.store.BrainStore") as store:
            self.assertEqual(intelligence.decide(
                "2 + 2?", feedback_examples=[], preferences="",
            )["reply"], "4")
        store.assert_not_called()

    @patch("src.agent.intelligence.requests.post")
    def test_useful_explanation_over_900_chars_is_not_discarded(self, post):
        reply = "Explicação fundamentada. " * 50
        post.return_value = model_reply({"move": "answer", "reply": reply})
        self.assertEqual(intelligence.decide(
            "Explique com detalhes", feedback_examples=[], preferences="",
        )["reply"], reply.strip())
        post.return_value = model_reply({"move": "answer", "reply": "x" * 4001})
        self.assertIsNone(intelligence.decide("Explique", feedback_examples=[], preferences=""))

    def test_plan_does_not_append_unsolicited_generic_invitation(self):
        rendered = intelligence.render_plan(verdict())
        self.assertIn("Selecionar sensores", rendered)
        self.assertNotIn("Posso continuar", rendered)

    @patch("src.agent.intelligence.requests.post")
    def test_public_query_is_optional_and_only_valid_on_research(self, post):
        item = {**verdict("research"), "query": "Python 3.12 pathlib documentation"}
        post.return_value = model_reply(item)
        self.assertEqual(intelligence.decide("Pesquise pathlib")["query"], item["query"])
        for value in (42, "x", "x" * 281):
            post.return_value = model_reply({**item, "query": value})
            self.assertIsNone(intelligence.decide("Pesquise pathlib"))
        post.return_value = model_reply({**item, "move": "answer"})
        self.assertIsNone(intelligence.decide("Explique pathlib"))
        post.return_value = model_reply(verdict("research"))
        self.assertNotIn("query", intelligence.decide("Pesquise pathlib"))

    @patch("src.agent.intelligence.requests.post")
    def test_reasoning_model_can_be_separate_from_coder(self, post):
        post.return_value = model_reply(verdict("plan"))
        with patch.dict(os.environ, {"MENOR_REASONING_MODEL": "local-instruct:7b"}):
            decision = intelligence.decide("Quero montar uma bancada inteligente")
        self.assertEqual(decision["move"], "plan")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "local-instruct:7b")

    @patch("src.agent.intelligence.requests.post")
    def test_invalid_actions_and_fake_plans_cannot_be_executed(self, post):
        for invalid in [
            {**verdict(), "move": "shell.exec"},
            {**verdict(), "steps": ["sim"]},
            {**verdict(), "steps": []},
            {**verdict(), "goal": "x" * 300},
            {**verdict("clarify"), "question": ""},
        ]:
            post.return_value = model_reply(invalid)
            self.assertIsNone(intelligence.decide("Quero criar algo novo"))

    @patch("src.agent.intelligence.requests.post", side_effect=__import__("requests").Timeout)
    def test_timeout_fails_without_granting_execution(self, post):
        self.assertIsNone(intelligence.decide("Quero criar um sistema"))
        post.assert_called_once()


class UniversalAgentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        env = patch.dict(os.environ, {
            "MENOR_DATA_DIR": temporary.name, "MENOR_INTELLIGENCE_ENABLED": "1",
        })
        env.start()
        self.addCleanup(env.stop)
        self.tasks = TaskStore()
        self.session = "universalAgent01"

    @patch("src.agent.runner.intelligence.decide")
    def test_unfamiliar_domain_generates_goal_and_persists_followup(self, decide):
        decide.side_effect = [verdict("plan"), verdict("continue")]
        first = runner.run(self.session, "universalTurn01", "Quero automatizar uma horta", [], tasks=self.tasks)
        self.assertEqual(first["phase"], "goal")
        self.assertIn("Vamos por partes", first["reply"])
        pending = self.tasks.inspect(self.session)
        self.assertEqual(pending["goal"], verdict()["goal"])
        second = runner.run(self.session, "universalTurn02", "Precisa funcionar sem internet", [], tasks=self.tasks)
        self.assertEqual(second["phase"], "goal")
        self.assertEqual(decide.call_args.kwargs["pending"]["goal"], pending["goal"])

    @patch("src.agent.runner.intelligence.decide", return_value=verdict("clarify"))
    def test_ambiguity_produces_question_without_writing(self, decide):
        with patch("src.agent.runner.perform") as perform:
            result = runner.run(self.session, "universalTurn01", "Quero fazer uma coisa", [],
                                tasks=self.tasks)
        self.assertIn("monitorar umidade", result["reply"])
        self.assertEqual(result["phase"], "goal")
        perform.assert_not_called()

    @patch("src.agent.runner.intelligence.decide", return_value=verdict("act"))
    @patch("src.agent.runner._tool_loop")
    def test_model_action_still_goes_through_tool_executor(self, tool_loop, decide):
        tool_loop.return_value = runner._answer("Ferramenta não está disponível.")
        result = runner.run(self.session, "universalTurn01", "Faça um conversor", [], tasks=self.tasks)
        self.assertTrue(result["handled"])
        tool_loop.assert_called_once()

    @patch("src.agent.runner.intelligence.decide", return_value=None)
    def test_no_model_result_falls_back_to_existing_chat(self, decide):
        result = runner.run(self.session, "universalTurn01", "oi", [], tasks=self.tasks)
        self.assertFalse(result["handled"])

    @patch("src.agent.runner.intelligence.decide", return_value=verdict("plan"))
    def test_pending_goal_can_be_cancelled_without_any_external_action(self, decide):
        runner.run(self.session, "universalTurn01", "Quero automatizar", [], tasks=self.tasks)
        result = runner.run(self.session, "universalTurn02", "cancela", [], tasks=self.tasks)
        self.assertEqual(result["phase"], "idle")
        self.assertIn("Cancelei", result["reply"])
        decide.assert_called_once()


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = FeedbackStore(BrainStore(Path(tmp.name) / "data"))

    def test_examples_require_explicit_consent_and_are_private(self):
        with self.assertRaises(ValueError):
            self.store.add("Quero criar uma música instrumental", "Pergunte sobre duração e estilo.")
        receipt = self.store.add(
            "Quero criar uma música instrumental", "Pergunte sobre duração e estilo.",
            consent=True,
        )
        self.assertEqual(receipt["status"], "saved")
        self.assertEqual(self.store.stats()["approved_examples"], 1)
        path = self.store._file()
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(self.store.samples()), 1)
        self.assertEqual(self.store.add(
            "Quero criar uma música instrumental", "Pergunte sobre duração e estilo.",
            consent=True,
        )["status"], "duplicate")

    def test_sensitive_examples_are_never_stored(self):
        with self.assertRaises(ValueError):
            self.store.add(
                "Pesquise minha senha no servidor", "Não posso enviar a senha ao buscador.",
                consent=True,
            )
        self.assertEqual(self.store.stats()["approved_examples"], 0)

    def test_lab_scores_many_domains_without_executing_any_tool(self):
        def fake(message, history, pending=None, capabilities=None):
            return {"move": "clarify"}
        report = lab.evaluate(fake)
        self.assertEqual(report["cases"], len(lab.CASES))
        self.assertGreater(report["passed"], 0)
        self.assertLess(report["score"], 1)


class FeedbackAPITests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {"MENOR_DATA_DIR": tmp.name})
        env.start()
        self.addCleanup(env.stop)
        from src.security import auth
        auth._attempts.clear()
        code, _, headers = call("/auth/setup", {"password": "senha-longa-para-feedback"})
        self.assertEqual(code, 200)
        self.cookie = headers[b"set-cookie"].decode().split(";", 1)[0]

    def test_authenticated_feedback_is_opt_in(self):
        body = {
            "prompt": "Quero montar uma agenda inteligente",
            "desired_reply": "Podemos planejar uma agenda local com lembretes.",
        }
        self.assertEqual(call("/agent/feedback", body)[0], 401)
        self.assertEqual(call("/agent/feedback", body, cookie=self.cookie)[0], 422)
        code, result, _ = call("/agent/feedback", {**body, "consent": True}, cookie=self.cookie)
        self.assertEqual(code, 200, result)
        self.assertEqual(result["status"], "saved")
        self.assertEqual(call("/agent/feedback/stats", cookie=self.cookie)[1]["approved_examples"], 1)


if __name__ == "__main__":
    unittest.main()
