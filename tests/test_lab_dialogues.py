"""E15 — roteiros multiturmo reais, com avaliações seguras e sem I/O do agente."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.api import lab_batches, lab_dialogues

SUITES = (
    "e15-conversas-descoberta", "e15-conversas-memoria",
    "e15-intencao-sem-antigos-gatilhos", "e15-seguranca-e-autorizacao",
)


class LiveDialogueContracts(unittest.TestCase):
    def test_four_suites_have_32_dialogues_and_136_messages(self):
        suites = [lab_batches.load_suite(name) for name in SUITES]
        self.assertEqual([len(item["cases"]) for item in suites], [8, 8, 8, 8])
        self.assertEqual([lab_batches._suite_units(item) for item in suites], [32, 40, 32, 32])
        self.assertEqual(sum(lab_batches._suite_units(x) for x in suites), 136)
        self.assertEqual({case["engine"] for suite in suites for case in suite["cases"]},
                         {"chat", "semantic"})
        for suite in suites:
            self.assertEqual(len({case["id"] for case in suite["cases"]}), 8)
            for case in suite["cases"]:
                self.assertEqual(lab_dialogues.validate_case(case), case)
                for turn in case["turns"]:
                    self.assertTrue(turn["review_criteria"])

    def test_rejects_invalid_or_too_large_scenarios_before_ollama(self):
        base = {"mode": "dialogue", "engine": "chat",
                "turns": [{"message": "Primeira pergunta", "review_criteria": "Revisão humana"},
                          {"message": "Segunda pergunta", "review_criteria": "Revisão humana"}]}
        broken = [
            {**base, "turns": base["turns"][:1]},
            {**base, "turns": base["turns"] * 5},
            {**base, "turns": [{**base["turns"][0], "message": "  "}, base["turns"][1]]},
            {**base, "turns": [
                {**base["turns"][0], "checks": {"forbid_act": True}},
                base["turns"][1],
            ]},
            {**base, "turns": [
                {**base["turns"][0], "checks": {"code_exec": True}},
                base["turns"][1],
            ]},
            {**base, "history": [{"role": "assistant", "content": "Histórico forjado"}]},
            {**base, "engine": "terminal"},
        ]
        for case in broken:
            with self.subTest(case=str(case)[:60]), self.assertRaises(ValueError):
                lab_dialogues.validate_case(case)

    def test_chat_uses_actual_model_reply_as_next_context_and_never_runs_tools(self):
        calls = []

        def fake(engine, message, history, model, pending):
            calls.append((message, list(history), model))
            return ({"status": "answered", "reply": "Resposta " + str(len(calls)),
                     "model": model, "move": None, "tool": None}, pending)

        case = {"id": "scenario", "mode": "dialogue", "engine": "chat",
                "turns": [{"message": x, "review_criteria": "Contexto coerente"}
                          for x in ("Quero um projeto", "Mudei a cor", "Qual cor?")]}
        with (patch.object(lab_dialogues, "run_turn", side_effect=fake),
              patch("src.tools.registry.perform") as perform):
            results = list(lab_dialogues.execute(case, model="qwen2.5-coder:7b"))
        self.assertEqual([x["reply"] for x in [item["result"] for item in results]],
                         ["Resposta 1", "Resposta 2", "Resposta 3"])
        self.assertEqual(calls[1][1], [{"role": "user", "content": "Quero um projeto"},
                                       {"role": "assistant", "content": "Resposta 1"}])
        self.assertEqual(calls[2][1][-1]["content"], "Resposta 2")
        self.assertEqual(len(results), 3)
        self.assertTrue(all(x["automatic_pass"] is None for x in results))
        perform.assert_not_called()

    def test_failed_model_stops_scenario_and_marks_missing_turns(self):
        case = {"id": "failure", "mode": "dialogue", "engine": "chat",
                "turns": [{"message": "Primeira", "review_criteria": "Responde"},
                          {"message": "Segunda", "review_criteria": "Responde"},
                          {"message": "Terceira", "review_criteria": "Responde"}]}
        with patch.object(lab_dialogues, "run_turn",
                          side_effect=TimeoutError("private token in exception")) as model:
            result = list(lab_dialogues.execute(case, model="qwen2.5-coder:7b"))
        self.assertEqual([r["result"]["status"] for r in result],
                         ["inference_failed", "skipped_after_failure", "skipped_after_failure"])
        self.assertEqual(model.call_count, 1)
        self.assertNotIn("private token", json.dumps(result))
        self.assertTrue(all(item["automatic_pass"] is False for item in result))

    def test_decision_checks_detect_unwanted_action_without_fake_achievement(self):
        tests = {"forbid_act": True, "forbidden_tools": ["developer.propose"]}
        self.assertTrue(lab_dialogues.check_turn(tests, {"status": "decision_validated",
                                                         "move": "clarify", "tool": None}))
        self.assertFalse(lab_dialogues.check_turn(tests, {"status": "decision_validated",
                                                          "move": "act", "tool": "developer.propose"}))
        self.assertFalse(lab_dialogues.check_turn(tests, {"status": "no_valid_decision"}))
        self.assertIsNone(lab_dialogues.check_turn({}, {"status": "decision_validated"}))
        self.assertTrue(lab_dialogues.check_turn({"required_tool": "projects.list"},
                                                 {"status": "decision_validated",
                                                  "move": "act", "tool": "projects.list"}))

    def test_router_simulation_uses_personal_scope_and_never_performs(self):
        fake = {
            "move": "clarify", "goal": "Projetar aplicativo offline",
            "reply": "Me conte a funcionalidade central.",
            "question": "Para qual público?", "steps": [], "acceptance": [],
            "relation": "start",
        }
        with (patch.object(lab_dialogues.intelligence, "decide", return_value=fake) as decide,
              patch("src.tools.registry.perform") as perform):
            item, pending = lab_dialogues.run_turn(
                "semantic", "Tenho uma ideia", [], "qwen2.5-coder:7b", None)
        self.assertEqual(item["status"], "decision_validated")
        self.assertEqual(item["tools_executed"], 0)
        self.assertEqual(pending["goal"], fake["goal"])
        names = [tool["name"] for tool in decide.call_args.kwargs["tools"]]
        self.assertNotIn("developer.propose", names)
        self.assertNotIn("developer.build", names)
        perform.assert_not_called()

    def test_batch_persists_separate_dialogue_turns_and_report_metrics(self):
        case = {"id": "scenario", "mode": "dialogue", "engine": "chat",
                "turns": [{"message": "Uma ideia", "review_criteria": "Conversa normal"},
                          {"message": "Mais detalhes", "review_criteria": "Lembra contexto"}]}
        suite = {"id": "dialogue-contract", "cases": [case], "evaluation_model": "local:7b"}
        with tempfile.TemporaryDirectory() as temp:
            data_patch = patch.object(lab_batches, "DATA", Path(temp))
            dialogue_patch = patch.object(lab_dialogues, "run_turn", side_effect=[
                ({"status": "answered", "reply": "Entendi", "move": None}, None),
                ({"status": "answered", "reply": "Continuamos", "move": None}, None),
            ])
            checkout_patch = patch.object(lab_batches, "_checkout_snapshot",
                                          return_value={"status": "unavailable"})
            with data_patch, dialogue_patch, checkout_patch:
                run_id = "20261021T220000Z-12345678"
                self.assertTrue(lab_batches._run(suite, run_id))
                data = json.loads(lab_batches.report_path(run_id).read_text())
                self.assertEqual(data["total"], 2)
                self.assertEqual(data["dialogue_scenarios"], 1)
                self.assertEqual([r["conversation_id"] for r in data["cases"]],
                                 ["scenario", "scenario"])
                self.assertEqual(data["ungraded"], 2)
                summary = json.loads((Path(temp) / (run_id + ".summary.json")).read_text())
                self.assertNotIn("Uma ideia", json.dumps(summary))
                self.assertEqual(summary["total"], 2)


if __name__ == "__main__":
    unittest.main()
