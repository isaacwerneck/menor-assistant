"""Grade aritmético opcional: separa valor matemático de formato solicitado."""
import unittest

from src.api import lab_batches


class NumericGradeTests(unittest.TestCase):
    def test_semantic_matches_with_units_and_brazilian_currency(self):
        cases = [
            ("45", "45 MB"), ("1060", "R$ 1.060"), ("0.3", "0,3"),
            ("220", "R$ 220"), ("40", "40 minutos"),
        ]
        for expected, reply in cases:
            with self.subTest(reply=reply):
                spec = {"grader": "numeric", "expected_exact": expected}
                result = {"status": "answered", "reply": reply}
                self.assertTrue(lab_batches.grade_case(spec, result))
                self.assertFalse(lab_batches.numeric_format_compliance(spec, result))

    def test_actual_math_errors_still_fail(self):
        for expected, reply in (("220", "R$ 217"), ("140", "100 minutos"),
                                ("40", "33.33%"), ("60", "59")):
            with self.subTest(expected=expected, reply=reply):
                self.assertFalse(lab_batches.grade_case(
                    {"grader": "numeric", "expected_exact": expected},
                    {"status": "answered", "reply": reply}
                ))

    def test_valid_strict_format_and_rejected_fake_answer(self):
        case = {"grader": "numeric", "expected_exact": "45"}
        self.assertTrue(lab_batches.grade_case(case, {"status": "answered", "reply": "45"}))
        self.assertTrue(lab_batches.numeric_format_compliance(
            case, {"status": "answered", "reply": "45"}))
        for text in ("O resultado é 45", "45 e depois 100", "1+44", "45%", "45GB e mais", "nan"):
            with self.subTest(text=text):
                self.assertFalse(lab_batches.grade_case(case, {"status": "answered", "reply": text}))

    def test_numeric_gabarito_validation_excludes_non_numbers_and_mixed_criteria(self):
        for expected in ("10%%", "100MB", "1e5", "Infinity", "vinte", None):
            bad = {"id": "a", "mode": "direct", "message": "Quanto é?",
                   "grader": "numeric", "expected_exact": expected}
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                lab_batches.validate_suite({"id": "teste-numero", "cases": [bad]})
        with self.assertRaises(ValueError):
            lab_batches.validate_suite({"id": "teste-numero", "cases": [{
                "id": "a", "mode": "direct", "message": "Quanto é?",
                "grader": "numeric", "expected_exact": "45", "expected_contains": ["45"],
            }]})

    def test_offline_suite_is_valid_without_ollama(self):
        suite = lab_batches.load_suite("matematica-validacao-v2")
        self.assertEqual(len(suite["cases"]), 12)
        self.assertTrue(all(c["grader"] == "numeric" for c in suite["cases"]))


if __name__ == "__main__":
    unittest.main()
