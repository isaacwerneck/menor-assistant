"""E19: 14 capacidades estáveis, paráfrases reproduzíveis e escopos de evidência."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.api import lab_batches, lab_core


class NoWorker:
    def __init__(self, target, args=(), daemon=False):
        self.target = target
        self.args = args

    def start(self):
        self.target(*self.args)


class CoreCatalogTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        patcher = patch.object(lab_batches, "DATA", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        with lab_batches._LOCK:
            self.old_running = lab_batches._RUNNING
            self.old_state = dict(lab_batches.STATE)
            lab_batches._RUNNING = False
            lab_batches.STATE.clear()
            lab_batches.STATE["status"] = "idle"
        self.addCleanup(self.restore)

    def restore(self):
        with lab_batches._LOCK:
            lab_batches._RUNNING = self.old_running
            lab_batches.STATE.clear()
            lab_batches.STATE.update(self.old_state)

    def test_exactly_fourteen_capabilities_with_stable_ids_and_distinct_objectives(self):
        self.assertEqual(len(lab_core.CORE_IDS), 14)
        self.assertEqual(len(set(lab_core.CORE_IDS)), 14)
        self.assertEqual(lab_core.catalog()["count"], 14)
        suites = [lab_batches.load_suite(suite_id) for suite_id in lab_core.CORE_IDS]
        self.assertEqual({suite["methodology_version"] for suite in suites},
                         {"core-stable-domains-v1"})
        self.assertEqual(sum(lab_batches._suite_units(suite) for suite in suites), 112)
        self.assertEqual(len({suite["capability"] for suite in suites}), 14)
        self.assertTrue(all(len(suite["cases"]) == 2 for suite in suites))
        self.assertTrue(all(case["mode"] == "dialogue" for suite in suites
                            for case in suite["cases"]))
        self.assertTrue(all(suite["evidence_level"] == "model_only" for suite in suites))
        self.assertTrue(all(len(turn["review_criteria"]) > 5
                            for suite in suites for case in suite["cases"]
                            for turn in case["turns"]))
        self.assertTrue({"conversa", "memoria", "documentos", "ferramentas",
                         "seguranca", "autoaperfeicoamento", "desempenho"}.issubset(
                            {suite["capability"] for suite in suites}))

    def test_anchor_never_changes_but_paraphrases_rotate_each_round(self):
        for suite_id in lab_core.CORE_IDS:
            with self.subTest(suite=suite_id):
                rounds = [lab_core.suite(suite_id, index) for index in range(4)]
                fixed = [suite["cases"][0] for suite in rounds]
                rotated = [suite["cases"][1] for suite in rounds]
                self.assertTrue(all(case["turns"] == fixed[0]["turns"]
                                    for case in fixed))
                self.assertEqual([case["scenario_variant"] for case in fixed],
                                 [0, 0, 0, 0])
                self.assertEqual([case["scenario_variant"] for case in rotated],
                                 [0, 1, 2, 0])
                messages = [tuple(turn["message"] for turn in case["turns"])
                            for case in rotated]
                self.assertEqual(len(set(messages[:3])), 3)
                self.assertEqual(messages[0], messages[3])
                for suite in rounds:
                    self.assertIs(lab_batches.validate_suite(suite), suite)

    def test_cycle_source_is_durable_and_never_depends_on_model(self):
        self.assertEqual(lab_core.next_cycle(self.root), 0)
        for count, model in enumerate(("control:7b", "candidate:14b")):
            (self.root / f"20261022T01010{count}Z-1234ab0{count}.summary.json").write_text(
                json.dumps({"suite_id": "core-conversa", "evaluation_model": model,
                            "core_cycle": 0}))
        self.assertEqual(lab_core.next_cycle(self.root), 1)
        (self.root / "20261022T111111Z-fd111111.summary.json").write_text(
            '{"suite_id": "core-conversa", "core_cycle": 2}')
        self.assertEqual(lab_core.next_cycle(self.root), 3)

    def test_same_cycle_for_two_models_in_queue_and_subset_execution(self):
        captured = []

        def run_queue(entries):
            captured.extend(entries)
            with lab_batches._LOCK:
                lab_batches._RUNNING = False

        suites = ["core-intencao", "core-documentos"]
        with patch.object(lab_batches.threading, "Thread") as worker:
            worker.return_value.start.side_effect = lambda: run_queue(
                worker.call_args.kwargs["args"][0])
            launch = lab_batches.start_queue(suites, models=["control:7b", "candidate:14b"])
        self.assertEqual(launch["core_cycle"], 0)
        self.assertEqual(launch["total"], 32)
        self.assertEqual(len(captured), 4)
        for index in (0, 2):
            first, second = captured[index][0], captured[index + 1][0]
            self.assertEqual(first["core_cycle"], second["core_cycle"])
            a = [[x["message"] for x in case["turns"]] for case in first["cases"]]
            b = [[x["message"] for x in case["turns"]] for case in second["cases"]]
            self.assertEqual(a, b)
            self.assertNotEqual(first["evaluation_model"], second["evaluation_model"])

    def test_public_listing_has_fourteen_core_and_legacy_is_still_available(self):
        listed = lab_batches.suites()
        core = [item for item in listed if item["source"] == "core"]
        self.assertEqual(len(core), 14)
        self.assertEqual(sum(item["cases"] for item in core), 112)
        self.assertEqual(len({item["id"] for item in listed}), len(listed))
        self.assertIn("e15-intencao-sem-antigos-gatilhos", [item["id"] for item in listed])
        self.assertEqual([item["source"] for item in core], ["core"] * 14)
        self.assertTrue(all(item["evidence_level"] == "model_only" for item in core))

    def test_private_import_cannot_overwrite_builtin_fixed_capability(self):
        sample = {"id": "core-conversa", "cases": [{
            "id": "a", "mode": "direct", "message": "Texto injetado"}]}
        with self.assertRaises(ValueError):
            lab_batches.save_suite(json.dumps(sample).encode())
        self.assertEqual(lab_batches.load_suite("core-conversa")["capability"], "conversa")

    def test_tool_capability_requires_real_tool_selection_without_execution(self):
        for cycle in range(3):
            scenario = lab_core.suite("core-ferramentas", cycle)["cases"][1]
            self.assertEqual(scenario["turns"][2]["checks"]["required_tool"],
                             "projects.list")
            self.assertEqual(scenario["turns"][2]["checks"]["forbidden_tools"],
                             ["developer.propose", "developer.build"])

    def test_core_report_keeps_cycle_variant_and_no_false_execution_claims(self):
        suite = lab_core.suite("core-memoria", cycle=2)
        cases = []

        def fake(engine, message, history, model, pending):
            return {"status": "answered", "reply": "Rascunho verbal.",
                    "move": None, "tools_executed": 0}, pending

        with (patch.object(lab_batches, "_checkout_snapshot",
                           return_value={"status": "unavailable"}),
              patch("src.api.lab_dialogues.run_turn", side_effect=fake)):
            self.assertTrue(lab_batches._run(suite, "20261022T222222Z-1234abcd"))
        report = json.loads((self.root / "20261022T222222Z-1234abcd.json").read_text())
        summary = json.loads((self.root / "20261022T222222Z-1234abcd.summary.json").read_text())
        self.assertEqual(report["core_cycle"], 2)
        self.assertEqual(report["core_catalog_version"], "core-v1")
        self.assertEqual(report["evidence_level"], "model_only")
        self.assertEqual([item["scenario_variant"] for item in report["cases"]],
                         [0] * 4 + [2] * 4)
        self.assertEqual(report["dialogue_completed"], 2)
        self.assertEqual(report["ungraded"], 8)
        self.assertEqual(summary["core_cycle"], 2)
        self.assertNotIn("Rascunho verbal", json.dumps(summary, ensure_ascii=False))
        self.assertEqual(cases, [])


if __name__ == "__main__":
    unittest.main()
