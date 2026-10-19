"""Testes sem Ollama e sem ferramentas para o benchmark do Chat A."""
import json
import unittest

from src.agent.benchmark import Scenario, benchmark, main


def plan(**changes):
    return {"move": "plan", "relation": "start", "resume_goal_id": "", "tool": "",
            "arguments": {}, "question": "", **changes}


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.cases = (Scenario("documento", "Planeje a leitura de PDF", ("plan", "clarify")),)

    def test_no_live_mode_does_not_use_ollama(self):
        self.assertEqual(main([]), 0)

    def test_baseline_skips_critic_completely(self):
        def forbidden(*args, **kwargs):
            self.fail("A revisão não deveria rodar")

        result = benchmark(lambda *a, **kw: plan(), forbidden, self.cases)
        self.assertEqual(result["baseline"]["passed"], 1)
        self.assertIsNone(result["reviewed"])
        self.assertEqual(result["details"][0]["review_status"], "skipped")

    def test_compare_reuses_initial_plan_and_times_additional_cost(self):
        calls = []
        times = iter([0, .1, .1, .3])

        def planner(*a, **kw):
            calls.append("planner")
            return plan()

        def critic(*a, **kw):
            calls.append("critic")
            return {"verdict": "ok", "issues": [], "question": ""}

        result = benchmark(planner, critic, self.cases, True, lambda: next(times))
        self.assertEqual(calls, ["planner", "critic"])
        self.assertEqual(result["reviewed"]["passed"], 1)
        self.assertEqual(result["latency_ms"]["baseline_total"], 100.0)
        self.assertEqual(result["latency_ms"]["review_extra_total"], 200.0)

    def test_single_revision_preserves_identity_and_can_improve_move(self):
        calls = []
        case = (Scenario("retomar", "Volte ao projeto de arquivo", ("continue",),
                         relation="resume", active="Fazer música", paused="Ler documentos"),)

        def planner(*args, **kw):
            calls.append(kw)
            if kw.get("review_issues"):
                return plan(move="continue", relation="switch", resume_goal_id="injetado")
            return plan(move="plan", relation="resume", resume_goal_id="a" * 32)

        def critic(*a, **kw):
            return {"verdict": "revise", "issues": ["Corrigir etapas"], "question": ""}

        result = benchmark(planner, critic, case, True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["review_issues"], ["Corrigir etapas"])
        self.assertEqual(result["reviewed"]["passed"], 1)
        self.assertEqual(result["details"][0]["review_status"], "revised_unverified")

    def test_rejected_unsafe_revision_does_not_replace_plan(self):
        calls = []

        def planner(*a, **kw):
            calls.append(kw)
            return plan(move="act") if kw.get("review_issues") else plan()

        result = benchmark(planner, lambda *a, **kw: {"verdict": "revise", "issues": ["Revise"]},
                           self.cases, True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["details"][0]["review_status"], "revise")
        self.assertEqual(result["reviewed"]["passed"], 1)

    def test_critic_clarification_only_needs_one_question(self):
        case = (Scenario("vago", "Resolva isso", ("clarify",), question=True),)
        result = benchmark(lambda *a, **k: plan(),
                           lambda *a, **k: {"verdict": "clarify", "question": "Que arquivo?"},
                           case, True)
        self.assertEqual(result["baseline"]["passed"], 0)
        self.assertEqual(result["reviewed"]["passed"], 1)

    def test_offline_is_not_a_zero_quality_score(self):
        result = benchmark(lambda *a, **k: None, cases=self.cases, compare_review=True)
        self.assertEqual(result["baseline"]["unavailable"], 1)
        self.assertIsNone(result["baseline"]["score"])
        self.assertIsNone(result["reviewed"]["score"])
        self.assertEqual(result["latency_ms"]["review_extra_total"], 0)

    def test_unavailable_critic_does_not_fake_improvement(self):
        result = benchmark(lambda *a, **k: plan(), lambda *a, **k: None,
                           self.cases, True)
        self.assertEqual(result["details"][0]["review_status"], "unavailable")
        self.assertEqual(result["baseline"]["score"], result["reviewed"]["score"])

    def test_tools_are_not_provided_or_authorized_by_benchmark(self):
        received = []

        def planner(*a, **kw):
            received.append(kw)
            return plan(tool="shell.exec")

        result = benchmark(planner, cases=self.cases)
        self.assertEqual(received[0]["tools"], [])
        self.assertEqual(received[0]["capabilities"], [])
        self.assertEqual(result["baseline"]["passed"], 0)

    def test_output_contains_no_prompts_or_model_responses(self):
        secret = "texto-privado-que-nao-deve-aparecer"
        case = (Scenario("privado", secret, ("plan",)),)
        result = benchmark(lambda *a, **kw: {**plan(), "reply": secret}, cases=case)
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(secret, serialized)
        self.assertIn("privado", serialized)

    def test_zero_scenarios_is_empty_not_failure(self):
        result = benchmark(cases=())
        self.assertEqual(result["baseline"]["cases"], 0)
        self.assertIsNone(result["baseline"]["score"])
        self.assertIsNone(result["latency_ms"]["baseline_p50"])


if __name__ == "__main__":
    unittest.main()
