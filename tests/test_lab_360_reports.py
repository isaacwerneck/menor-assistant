"""Auditoria agregada sem conteúdo privado e revisão humana de formatos equivalentes."""
import json
import tempfile
import unittest
from pathlib import Path

from ops import lab_batch_audit, lab_eval_analysis
from src.api import lab_batches


class ReviewOnlyTests(unittest.TestCase):
    def test_accents_and_numbers_written_are_flagged_not_regraded(self):
        scenarios = [
            ({"expected_contains": ["relatorios"]},
             {"automatic_pass": False, "result": {"status": "answered",
                                                  "reply": 'Nome da pasta: "relatórios".'}}, True),
            ({"expected_contains": ["7"]},
             {"automatic_pass": False, "result": {"status": "answered",
                                                  "reply": "Foram sete relatórios."}}, True),
            ({"expected_exact": "SIM"},
             {"automatic_pass": False, "result": {"status": "answered",
                                                  "reply": "NÃO"}}, False),
            ({"expected_exact": "220"},
             {"automatic_pass": False, "result": {"status": "answered",
                                                  "reply": "217"}}, False),
        ]
        for spec, case, flag in scenarios:
            with self.subTest(spec=spec):
                self.assertEqual(lab_eval_analysis._possible_format_mismatch(spec, case),
                                 flag)
                self.assertIs(case["automatic_pass"], False)

    def test_math_wrong_value_stays_wrong(self):
        self.assertFalse(lab_batches.grade_case(
            {"grader": "numeric", "expected_exact": "896"},
            {"status": "answered", "reply": "R$ 960"}))


class AggregateAuditTests(unittest.TestCase):
    def report(self, folder, suffix, question, status="answered", grade=True):
        run_id = "20261020T162713Z-" + suffix
        data = {
            "run_id": run_id, "suite_id": "teste-relatorios",
            "cases": [{"id": "c1", "mode": "direct", "question": question,
                       "history": [], "automatic_pass": grade, "elapsed_seconds": 2.5,
                       "result": {"status": status, "reply": "CONTEUDO_SOMENTE_NO_ARQUIVO",
                                  "performance": {"prompt_eval_duration": 900_000_000,
                                                  "eval_duration": 2_000_000_000}}}],
        }
        (folder / (run_id + ".json")).write_text(json.dumps(data), encoding="utf-8")

    def test_reports_are_counted_but_repeated_questions_not_double_unique(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.report(root, "12345678", "Pergunta privada número 1")
            self.report(root, "87654321", "Pergunta privada número 1",
                        status="inference_failed", grade=None)
            (root / "not-report.json").write_text("{}")
            stats = lab_batch_audit.inspect(root)
        self.assertEqual(stats["reports"], 2)
        self.assertEqual(stats["cases_executed"], 2)
        self.assertEqual(stats["unique_prompt_history_pairs"], 1)
        self.assertEqual(stats["graded_passes"], 1)
        self.assertEqual(stats["ungraded"], 1)
        self.assertEqual(stats["technical_failures"], 1)
        self.assertEqual(stats["prefill_p50_seconds"], 0.9)
        self.assertEqual(stats["generation_p50_seconds"], 2)
        self.assertNotIn("CONTEUDO_SOMENTE_NO_ARQUIVO", json.dumps(stats))
        self.assertNotIn("Pergunta privada", json.dumps(stats))

    def test_limits_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.report(root, "12345678", "Questão um")
            self.report(root, "87654321", "Questão dois")
            self.assertEqual(lab_batch_audit.inspect(root, limit=1)["reports"], 1)
            with self.assertRaises(ValueError):
                lab_batch_audit.inspect(root, limit=0)


class ComparativeCasesTests(unittest.TestCase):
    def test_paired_batteries_are_exactly_equivalent_except_profile(self):
        original = lab_batches.load_suite("comparacao-qualidade-baseline-v1")
        upgraded = lab_batches.load_suite("comparacao-qualidade-assistente-v1")
        self.assertEqual(original["comparison_group"], upgraded["comparison_group"])
        self.assertEqual(len(original["cases"]), 46)
        self.assertEqual(len(upgraded["cases"]), 46)
        for a, b in zip(original["cases"], upgraded["cases"]):
            for key in ("id", "message", "history", "expected_exact",
                        "expected_contains", "grader", "mode"):
                self.assertEqual(a.get(key), b.get(key))
            self.assertEqual(a["profile"], "baseline")
            self.assertEqual(b["profile"], "assistant")


if __name__ == "__main__":
    unittest.main()
