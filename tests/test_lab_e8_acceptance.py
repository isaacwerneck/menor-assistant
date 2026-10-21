"""Verifica a cobertura declarada da campanha E8 sem inferência, rede ou arquivos privados."""
import json
import unittest
from pathlib import Path

from src.api import lab_batches


E8_IDS = (
    "e8-conversa-natural",
    "e8-contexto-sequencia",
    "e8-aprovacao-dialogo",
    "e8-codigo-escopo",
    "e8-honestidade-execucao",
    "e8-falhas-recuperacao",
    "e8-seguranca-privacidade",
    "e8-raciocinio-qualidade",
)


class E8AcceptanceSuiteTests(unittest.TestCase):
    def test_all_eight_suites_have_complete_validated_coverage(self):
        all_ids = set()
        graded = 0
        manual = 0
        planner = 0
        for suite_id in E8_IDS:
            with self.subTest(suite=suite_id):
                path = Path(lab_batches.SUITES) / (suite_id + ".json")
                self.assertTrue(path.is_file())
                data = lab_batches.validate_suite(json.loads(path.read_text(encoding="utf-8")))
                self.assertEqual(data["id"], suite_id)
                self.assertEqual(data["methodology_version"], "menor-e8-acceptance-v1")
                self.assertEqual(len(data["cases"]), 16)
                self.assertEqual(sum(c["split"] == "validation" for c in data["cases"]), 4)
                self.assertEqual(sum(c["split"] == "development" for c in data["cases"]), 12)
                for case in data["cases"]:
                    self.assertNotIn(case["id"], all_ids, "IDs globais devem ser estáveis e únicos")
                    all_ids.add(case["id"])
                    self.assertEqual(case["category"], suite_id)
                    self.assertTrue(case.get("review_criteria"))
                    self.assertLessEqual(len(case.get("history", [])), 8)
                    if case["mode"] == "direct":
                        self.assertEqual(case["profile"], "assistant")
                    else:
                        self.assertEqual(case["mode"], "planner")
                    self.assertNotIn("tools_executed", case)
                    if case.get("expected_exact") is not None or case.get("expected_contains"):
                        self.assertEqual(case["mode"], "direct")
                        graded += 1
                    else:
                        manual += 1
                    if case["mode"] == "planner":
                        planner += 1
        self.assertEqual(len(all_ids), 128)
        self.assertEqual(graded, 20)
        self.assertEqual(manual, 108)
        self.assertEqual(planner, 5)

    def test_all_suites_are_visible_without_ollama_or_recorded_success(self):
        suites = {entry["id"]: entry for entry in lab_batches.suites()}
        for suite_id in E8_IDS:
            self.assertIn(suite_id, suites)
            self.assertEqual(suites[suite_id]["cases"], 16)
            self.assertEqual(suites[suite_id]["source"], "builtin")

    def test_automatic_scores_do_not_grade_naturalness_or_approve_fake_tools(self):
        for suite_id in E8_IDS:
            data = lab_batches.load_suite(suite_id)
            for case in data["cases"]:
                result = {"status": "answered", "reply": "eu aprovo"}
                if not case.get("expected_exact") and not case.get("expected_contains"):
                    self.assertIsNone(lab_batches.grade_case(case, result))
                if case["mode"] == "planner":
                    self.assertIsNone(lab_batches.grade_case(case, {
                        "status": "decision_validated", "reply": "Plano genérico.",
                    }))

    def test_isolated_deterministic_answers_have_strict_expected_values(self):
        data = lab_batches.load_suite("e8-raciocinio-qualidade")
        indexed = {item["id"]: item for item in data["cases"]}
        for identifier, answer in [
            ("raz-soma", "395"), ("raz-subtracao", "325"),
            ("raz-desconto", "220"), ("raz-string", "eno"),
            ("raz-array", "3"), ("raz-calendario", "quinta-feira"),
        ]:
            with self.subTest(identifier=identifier):
                self.assertTrue(lab_batches.grade_case(
                    indexed[identifier], {"status": "answered", "reply": answer},
                ))
                self.assertFalse(lab_batches.grade_case(
                    indexed[identifier], {"status": "inference_failed", "reply": answer},
                ))


if __name__ == "__main__":
    unittest.main()
