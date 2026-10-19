"""Dialogue benchmark contracts; never executes a tool or calls Ollama in tests."""
import unittest

from src.agent.dialogue_bench import DIALOGUES, evaluate_dialogues


class DialogueBenchTests(unittest.TestCase):
    def test_all_cases_have_expected_move_and_explicit_reference(self):
        self.assertGreaterEqual(len(DIALOGUES), 10)
        names = [item.name for item in DIALOGUES]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(case.allowed_moves for case in DIALOGUES))

    def test_mocked_benchmark_catches_wrong_reply_and_preserves_no_tool_execution(self):
        called = []

        def wrong_model(message, history, capabilities=None, tools=None, preferences=None, feedback_examples=None):
            self.assertEqual(preferences, "")
            self.assertEqual(feedback_examples, [])
            called.append((message, history, capabilities, tools))
            return {"move": "answer", "relation": "start", "reply": "Não sei"}

        report = evaluate_dialogues(decider=wrong_model)
        self.assertEqual(report["cases"], len(DIALOGUES))
        self.assertLess(report["score"], 0.5)
        self.assertEqual(len(called), len(DIALOGUES))
        self.assertTrue(all(tools == [] for _, _, _, tools in called))
        self.assertEqual(len(report["details"]), len(DIALOGUES))
        self.assertNotIn("Meu servidor usa Ubuntu", str(report["details"]))

    def test_no_model_reports_explicit_unavailable(self):
        report = evaluate_dialogues(decider=lambda *a, **k: None)
        self.assertEqual(report["passed"], 0)
        self.assertTrue(all(item["move"] == "unavailable" for item in report["details"]))


if __name__ == "__main__":
    unittest.main()
