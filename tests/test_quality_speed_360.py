"""Regressões de qualidade/latência guiadas pelos relatórios reais (sem Ollama).

Os testes não enviam textos privados para rede. Respostas do modelo são fake.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ops import lab_batch_audit, lab_eval_analysis
from src.agent import intelligence, runner
from src.agent.tasks import TaskStore
from src.agent.response_budget import output_budget
from src.agent.voice import LAB_ASSISTANT_VOICE, LAB_BASELINE_VOICE
from src.api import lab_batches, remote_lab, main


def fake_direct_reply(text="NÃO", *, tokens=2):
    response = MagicMock()
    response.__enter__.return_value = response
    response.json.return_value = {
        "message": {"content": text},
        "prompt_eval_duration": 1_400_000_000,
        "eval_duration": 300_000_000,
        "eval_count": tokens, "prompt_eval_count": 70,
        "done_reason": "stop",
    }
    return response


class OutputBudgetTests(unittest.TestCase):
    def test_explicit_one_word_and_numeric_requests_use_small_budget(self):
        for text in (
            "Responda só SIM ou NÃO.", "Apenas o número.",
            "Só o comando.", "Apenas nome do campo.",
        ):
            with self.subTest(text=text):
                self.assertEqual(output_budget(text), 56)

    def test_long_and_detailed_answers_remain_possible(self):
        self.assertEqual(output_budget("Explique com detalhes"), 256)
        self.assertEqual(output_budget("Explique com detalhes", chat=True), 512)
        self.assertEqual(output_budget("Conte sobre segurança", chat=True), 256)
        self.assertEqual(output_budget("Explique em duas frases", chat=True), 96)
        self.assertEqual(output_budget(None), 256)

    @patch("src.api.remote_lab.requests.post")
    def test_baseline_still_preserves_old_prompt_and_256_tokens(self, post):
        post.return_value = fake_direct_reply()
        reply = remote_lab._direct(remote_lab.LabRequest(
            mode="direct", message="Responda só SIM ou NÃO."
        ))
        sent = post.call_args.kwargs["json"]
        self.assertEqual(sent["options"]["num_predict"], 256)
        self.assertEqual(sent["messages"][0]["content"], LAB_BASELINE_VOICE)
        self.assertEqual(reply["profile"], "baseline")
        self.assertEqual(reply["output_budget_tokens"], 256)

    @patch("src.api.remote_lab.requests.post")
    def test_new_profile_preserves_history_and_has_safe_instruction_boundary(self, post):
        post.return_value = fake_direct_reply("OK", tokens=3)
        request = remote_lab.LabRequest(
            mode="direct", profile="assistant",
            message="Responda só o comando.",
            history=[{"role": "user", "content": "Tenho um servidor Ubuntu."}],
        )
        reply = remote_lab._direct(request)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["options"]["num_predict"], 56)
        self.assertEqual(payload["messages"][1]["content"], "Tenho um servidor Ubuntu.")
        self.assertEqual(payload["messages"][0]["content"], LAB_ASSISTANT_VOICE)
        self.assertIn("menor confiança", LAB_ASSISTANT_VOICE)
        self.assertIn("recibo", LAB_ASSISTANT_VOICE)
        self.assertEqual(reply["output_budget_tokens"], 56)
        self.assertEqual(reply["profile"], "assistant")
        self.assertEqual(reply["performance"]["prompt_eval_count"], 70)

    @patch("src.api.main.requests.post")
    @patch("src.api.main.capability_context", return_value="")
    @patch("src.api.main.prompt_with_preferences", return_value="Sistema")
    def test_chat_fallback_streaming_keeps_context_and_limits_length(self, prefs, cap, post):
        response = MagicMock()
        post.return_value = response
        req = main.ChatRequest(message="Só o número.", history=[
            {"role": "user", "content": "Contexto prévio."},
        ])
        self.assertIs(main.open_ollama(req, stream=True), response)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["options"]["num_predict"], 56)
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["messages"][-1]["content"], "Só o número.")
        self.assertEqual(payload["messages"][-2]["content"], "Contexto prévio.")


class ContractSchemaTests(unittest.TestCase):
    def test_no_tools_schema_disallows_action_at_decoder_level(self):
        schema = intelligence._schema_for_tools([])
        allowed = {x for branch in schema["oneOf"]
                   for x in branch["properties"]["move"]["enum"]}
        self.assertNotIn("act", allowed)
        self.assertIn("plan", allowed)
        self.assertIn("answer", allowed)
        self.assertIn("research", allowed)
        self.assertIn("inspect_result", allowed)
        for choice in schema["oneOf"]:
            self.assertNotIn("tool", choice["properties"])
            self.assertNotIn("arguments", choice["properties"])

    def test_no_tools_schema_does_not_mutate_real_agent_contract(self):
        baseline = json.dumps(intelligence.DECISION_SCHEMA, sort_keys=True)
        intelligence._schema_for_tools([])
        self.assertEqual(json.dumps(intelligence.DECISION_SCHEMA, sort_keys=True), baseline)
        self.assertIs(intelligence._schema_for_tools(None), intelligence.DECISION_SCHEMA)
        self.assertIs(intelligence._schema_for_tools([{"name": "math.calculate"}]),
                      intelligence.DECISION_SCHEMA)

    @patch("src.agent.intelligence.requests.post")
    def test_planner_without_tools_sends_restricted_schema_with_diagnostics(self, post):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {"message": {"content": '{"move":"answer","reply":"Não."}'}}
        post.return_value = response
        diag = {}
        self.assertEqual(intelligence.decide(
            "Quero só planejar, sem ferramentas", tools=[], preferences=[],
            feedback_examples=[], diagnostics=diag,
        )["move"], "answer")
        payload = post.call_args.kwargs["json"]
        self.assertNotIn("act", str(payload["format"]["oneOf"][0]["properties"]["move"]["enum"]))
        self.assertEqual(diag["outcome"], "validated")
        self.assertNotIn("reply", json.dumps(diag))


class GraderReviewTests(unittest.TestCase):
    def test_accented_word_only_raises_review_flag(self):
        spec = {"grader": "strict", "expected_contains": ["relatorios"]}
        case = {"automatic_pass": False,
                "result": {"status": "answered", "reply": 'A pasta se chama "relatórios".'}}
        self.assertTrue(lab_eval_analysis._possible_format_mismatch(spec, case))
        self.assertIs(case["automatic_pass"], False)

    def test_number_word_only_raises_review_flag(self):
        spec = {"expected_contains": ["7"]}
        case = {"automatic_pass": False,
                "result": {"status": "answered", "reply": "Havia sete relatórios."}}
        self.assertTrue(lab_eval_analysis._possible_format_mismatch(spec, case))

    def test_incorrect_or_contradictory_answers_not_silently_credited(self):
        for text in ("Não é válido; SIM", "A resposta é 8", "Senha: 7"):
            spec = {"grader": "boolean", "expected_exact": "NÃO"}
            case = {"automatic_pass": False, "result": {"status": "answered", "reply": text}}
            self.assertFalse(lab_eval_analysis._possible_format_mismatch(spec, case))
        wrong = {"automatic_pass": False, "result": {"status": "answered", "reply": "Seis relatórios"}}
        self.assertFalse(lab_eval_analysis._possible_format_mismatch(
            {"expected_contains": ["7"]}, wrong))

    def test_separate_incident_does_not_mutate_historical_scores(self):
        suite = {"id": "old", "cases": [
            {"id": "one", "mode": "direct", "expected_contains": ["relatorios"]},
        ]}
        report = {"run_id": "run", "suite_id": "old", "cases": [
            {"id": "one", "automatic_pass": False, "elapsed_seconds": 2,
             "result": {"status": "answered", "reply": "relatórios"}},
        ]}
        result = lab_eval_analysis.summarize(report, suite)
        self.assertEqual(result["graded_failures"], 1)
        self.assertEqual(result["incidents"]["possible_format_mismatch"], 1)


class RealisticABTests(unittest.TestCase):
    def test_46_cases_are_identical_except_profile_and_metadata(self):
        first = lab_batches.load_suite("comparacao-qualidade-baseline-v1")
        second = lab_batches.load_suite("comparacao-qualidade-assistente-v1")
        self.assertEqual(len(first["cases"]), 46)
        self.assertEqual(first["comparison_group"], second["comparison_group"])
        for a, b in zip(first["cases"], second["cases"]):
            self.assertEqual(a["id"], b["id"])
            self.assertEqual({k: v for k, v in a.items() if k != "profile"},
                             {k: v for k, v in b.items() if k != "profile"})
            self.assertEqual(a["profile"], "baseline")
            self.assertEqual(b["profile"], "assistant")


class OfflineAuditTests(unittest.TestCase):
    def test_private_text_not_in_aggregate_and_overlapping_questions_not_double_unique(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for n, suite in enumerate(("suite-one", "suite-two")):
                run = f"20261020T16540{n}Z-{n:08x}"
                data = {"run_id": run, "suite_id": suite, "cases": [
                    {"id": "x", "question": "SECRET PROMPT", "history": [],
                     "automatic_pass": True, "elapsed_seconds": 12,
                     "result": {"status": "answered", "reply": "SECRET ANSWER",
                                "performance": {"prompt_eval_duration": 2_000_000_000,
                                                "eval_duration": 10_000_000_000,
                                                "generation_tokens_per_second": 6.5}}},
                ]}
                (directory / (run + ".json")).write_text(json.dumps(data), encoding="utf-8")
            summary = lab_batch_audit.inspect(directory)
            self.assertEqual(summary["reports"], 2)
            self.assertEqual(summary["cases_executed"], 2)
            self.assertEqual(summary["unique_prompt_history_pairs"], 1)
            self.assertEqual(summary["graded_passes"], 2)
            self.assertEqual(summary["prefill_p50_seconds"], 2.0)
            for secret in ("SECRET PROMPT", "SECRET ANSWER"):
                self.assertNotIn(secret, json.dumps(summary))

    def test_orphan_summaries_and_symlinks_do_not_count(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root / "20261020T165400Z-ffffffff.summary.json").write_text("{}")
            (root / "not-a-run.json").write_text("{}")
            self.assertEqual(lab_batch_audit.inspect(root)["reports"], 0)


class ToolReceiptIntegrationTests(unittest.TestCase):
    def test_math_receipt_survives_next_turn_and_is_not_faked(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {"MENOR_DATA_DIR": directory, "MENOR_INTELLIGENCE_ENABLED": "1"}
            with (
                patch.dict(os.environ, env),
                patch.object(runner, "relevant_context", return_value=""),
                patch.object(runner, "contextual_knowledge", return_value=""),
                patch.object(runner.intelligence, "decide", side_effect=[
                    {"move": "act", "tool": "math.calculate",
                     "arguments": {"expression": "250*(1-12/100)"}, "reply": "Calculando."},
                    {"move": "inspect_result", "reply": "Qual foi o resultado anterior?"},
                ]),
            ):
                store = TaskStore()
                session = "receiptIntegration01"
                first = runner.run(session, "receiptTurn01",
                                   "Qual preço após 12% de desconto de 250?", [],
                                   tasks=store)
                self.assertEqual(first["events"][0]["status"], "executed")
                self.assertIn("Resultado calculado: 220", first["reply"])
                self.assertNotIn('"value"', first["reply"])
                state = store.inspect(session)
                self.assertEqual(state["last_result"]["tool"], "math.calculate")
                self.assertFalse(state["last_result"]["content_verified"])
                with patch.object(runner, "perform") as repeat:
                    second = runner.run(session, "receiptTurn02",
                                        "O que a calculadora respondeu antes?", [],
                                        tasks=store)
                    repeat.assert_not_called()
                self.assertIn("math.calculate", second["reply"])


if __name__ == "__main__":
    unittest.main()
