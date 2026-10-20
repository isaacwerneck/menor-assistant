"""Calculadora segura: precisão, limites e contratos de recibo."""
import unittest
from unittest.mock import patch

from src.tools.calculator import calculate
from src.tools.registry import TOOLS, perform


class CalculatorToolTests(unittest.TestCase):
    def test_correct_previous_real_math_failures(self):
        self.assertEqual(calculate("250*(1-12/100)")["value"], "220")
        self.assertEqual(calculate("45+60+35")["value"], "140")
        self.assertEqual(calculate("(2/5)*100")["value"], "40")
        self.assertEqual(calculate("1000*(1+2*3/100)")["value"], "1060")
        self.assertEqual(calculate("(18/4)*10")["value"], "45")

    def test_decimal_without_binary_float_artifacts(self):
        self.assertEqual(calculate("0.1 + 0.2")["value"], "0.3")
        self.assertEqual(calculate("1/4")["value"], "0.25")
        self.assertEqual(calculate("-5 + +3")["value"], "-2")

    def test_tool_is_readonly_and_result_does_not_claim_intent_verified(self):
        self.assertFalse(TOOLS["math.calculate"].writes)
        self.assertEqual(TOOLS["math.calculate"].arguments, ("expression",))
        self.assertEqual(perform("math.calculate", {"expression": "2+3"}, dry_run=True)["status"], "planned")
        receipt = perform("math.calculate", {"expression": "2+3"}, dry_run=False)
        self.assertEqual(receipt["status"], "executed")
        self.assertEqual(receipt["result"]["value"], "5")
        self.assertFalse(receipt["result"]["request_interpretation_verified"])
        self.assertTrue(receipt["result"]["expression_verified"])

    def test_rejects_execution_and_bombs(self):
        for item in (
            "__import__('os').system('id')", "2**10000000", "9/0", "sin(1)",
            "1<<12", "1e100", "1 + x", "1; 2", "5 // 2",
            "1" * 121, None, "", [], "(((((((((((((((((((1)))))))))))))))))))",
        ):
            with self.subTest(item=str(item)[:20]), self.assertRaises(ValueError):
                calculate(item)

    def test_rejects_large_result_without_system_effects(self):
        with patch("os.system") as shell:
            for item in ("99999999999999*9", "99999999999999+99999999999999"):
                with self.assertRaises(ValueError):
                    calculate(item)
        shell.assert_not_called()

    def test_registry_rejects_unexpected_args(self):
        with self.assertRaises(ValueError):
            perform("math.calculate", {"expression": "1+1", "command": "rm -rf /"}, dry_run=False)


if __name__ == "__main__":
    unittest.main()
