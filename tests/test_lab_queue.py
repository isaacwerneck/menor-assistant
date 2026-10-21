"""Fila do Lab: ordem sequencial, relatórios independentes e contagem durável."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from src.api import lab_batches, lab_batches_routes


class InlineThread:
    """Executa alvo no mesmo processo de teste, sem timing de CPU ou Ollama."""
    def __init__(self, target, args=(), daemon=False):
        self.target, self.args = target, args
        self.daemon = daemon

    def start(self):
        self.target(*self.args)


class QueueTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Path(temp.name)
        self.data_patch = patch.object(lab_batches, "DATA", self.store)
        self.data_patch.start()
        self.addCleanup(self.data_patch.stop)
        snapshot = patch.object(lab_batches, "_checkout_snapshot", return_value={"status": "unavailable"})
        snapshot.start()
        self.addCleanup(snapshot.stop)
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

    def suite(self, name, messages):
        raw = json.dumps({"id": name, "title": "Bateria " + name, "cases": [
            {"id": "c" + str(i), "mode": "direct", "message": message,
             "expected_exact": "OK"} for i, message in enumerate(messages)
        ]}).encode("utf-8")
        lab_batches.save_suite(raw)

    def test_multiple_suites_run_serially_and_each_saves_report(self):
        self.suite("primeira-bateria", ["a1", "a2"])
        self.suite("segunda-bateria", ["b1"])
        calls = []
        states = []

        def direct(payload):
            calls.append(payload.message)
            states.append(lab_batches.state())
            return {"status": "answered", "reply": "OK"}

        with (
            patch.object(lab_batches.threading, "Thread", InlineThread),
            patch.object(lab_batches.remote_lab, "_direct", side_effect=direct),
        ):
            launch = lab_batches.start_queue(["primeira-bateria", "segunda-bateria"])
        self.assertEqual(calls, ["a1", "a2", "b1"])
        self.assertEqual(len(launch["run_ids"]), 2)
        self.assertEqual(launch["total"], 3)
        self.assertEqual([s["queue_index"] for s in states], [1, 1, 2])
        self.assertEqual([s["overall_done"] for s in states], [0, 1, 2])
        final = lab_batches.state()
        self.assertEqual(final["status"], "completed")
        self.assertEqual(final["overall_done"], 3)
        self.assertEqual(final["overall_total"], 3)
        self.assertEqual(len(final["queue_finished"]), 2)
        self.assertFalse(lab_batches._RUNNING)
        for run_id in launch["run_ids"]:
            report = json.loads(lab_batches.report_path(run_id).read_text())
            self.assertEqual(report["automatic_failures"], 0)
            self.assertEqual(report["total"], len(report["cases"]))
            self.assertIsNone(report["code_provenance"]["revision_changed"])
        progress = {x["id"]: x for x in lab_batches.suites()}
        self.assertEqual(progress["primeira-bateria"]["status"], "completed")
        self.assertEqual(progress["segunda-bateria"]["status"], "completed")
        self.assertEqual(progress["primeira-bateria"]["run_count"], 1)
        self.assertEqual(progress["primeira-bateria"]["last_report"]["total"], 2)

    def test_failed_suite_does_not_discard_remaining_queue(self):
        self.suite("primeira-bateria", ["a1"])
        self.suite("segunda-bateria", ["b1"])
        original = lab_batches.grade_case
        attempts = []

        def flaky(case, output):
            attempts.append(case["id"])
            if len(attempts) == 1:
                raise RuntimeError("test-only report failure")
            return original(case, output)

        with (
            patch.object(lab_batches.threading, "Thread", InlineThread),
            patch.object(lab_batches.remote_lab, "_direct",
                         return_value={"status": "answered", "reply": "OK"}),
            patch.object(lab_batches, "grade_case", side_effect=flaky),
        ):
            launch = lab_batches.start_queue(["primeira-bateria", "segunda-bateria"])
        final = lab_batches.state()
        self.assertEqual(final["status"], "completed_with_errors")
        self.assertEqual(final["queue_failures"], ["primeira-bateria"])
        self.assertEqual([x["status"] for x in final["queue_finished"]],
                         ["failed", "completed"])
        self.assertFalse((self.store / (launch["run_ids"][0] + ".json")).exists())
        self.assertTrue((self.store / (launch["run_ids"][1] + ".json")).exists())

    def test_invalid_queue_is_rejected_before_any_inference(self):
        self.suite("primeira-bateria", ["a1"])
        for ids in ([], ["primeira-bateria"] * 2,
                    ["primeira-bateria", "nao-existe"],
                    ["../../foo"], [None], list(range(25))):
            with self.subTest(ids=ids), self.assertRaises(
                    (ValueError, FileNotFoundError)):
                lab_batches.start_queue(ids)
        self.assertFalse(lab_batches._RUNNING)
        self.assertEqual(lab_batches.state()["status"], "idle")
        self.assertFalse(list(self.store.glob("*.summary.json")))

    def test_model_override_is_local_to_run_and_saved_in_full_report(self):
        from ops.eval_compare import compare
        self.suite("bateria-modelos", ["pergunta pública"])
        original = lab_batches.load_suite("bateria-modelos")
        runs = []

        def direct(payload):
            return {"status": "answered", "reply": "OK", "model": payload.model}

        with (
            patch.object(lab_batches.threading, "Thread", InlineThread),
            patch.object(lab_batches.remote_lab, "_direct", side_effect=direct),
        ):
            for model in ("control:7b", "candidate:14b"):
                run = lab_batches.start_queue(["bateria-modelos"], model=model)
                report = json.loads(lab_batches.report_path(run["run_ids"][0]).read_text())
                self.assertEqual(report["evaluation_model"], model)
                self.assertEqual(report["cases"][0]["requested_model"], model)
                self.assertEqual(report["cases"][0]["result"]["model"], model)
                runs.append(report)
        self.assertEqual(lab_batches.load_suite("bateria-modelos"), original)
        self.assertEqual(compare(*runs)["graded_pass_delta"], 0)

    def test_invalid_model_does_not_start_queue(self):
        self.suite("bateria-modelos", ["pergunta pública"])
        with patch.object(lab_batches.threading, "Thread") as worker:
            with self.assertRaises(ValueError):
                lab_batches.start_queue(["bateria-modelos"], model="../../privado")
            worker.assert_not_called()
        self.assertFalse(lab_batches._RUNNING)

    def test_cannot_start_second_queue_while_active(self):
        self.suite("primeira-bateria", ["a1"])
        with lab_batches._LOCK:
            lab_batches._RUNNING = True
        with self.assertRaises(RuntimeError):
            lab_batches.start_queue(["primeira-bateria"])
        self.assertEqual(lab_batches.state()["status"], "idle")

    def test_local_summaries_count_every_run_not_only_first_hundred(self):
        suite_id = "primeira-bateria"
        self.suite(suite_id, ["a1"])
        for i in range(104):
            run_id = "20261020T" + str(i).zfill(6) + "Z-" + f"{i:08x}"
            summary = {
                "run_id": run_id, "suite_id": suite_id, "total": 1,
                "automatic_passes": 1, "automatic_failures": 0, "ungraded": 0,
            }
            (self.store / (run_id + ".summary.json")).write_text(json.dumps(summary))
            (self.store / (run_id + ".json")).write_text("{}")
        listed = {item["id"]: item for item in lab_batches.suites()}[suite_id]
        self.assertEqual(listed["run_count"], 104)
        self.assertEqual(listed["status"], "completed")
        self.assertEqual(listed["last_report"]["run_id"],
                         "20261020T000103Z-00000067")
        self.assertEqual(len(lab_batches.reports()), 100)

    def test_malformed_or_orphan_summary_does_not_mark_suite_completed(self):
        self.suite("primeira-bateria", ["a1"])
        (self.store / "fake.summary.json").write_text('{"suite_id":"primeira-bateria"}')
        run_id = "20261020T020000Z-deadbeef"
        (self.store / (run_id + ".summary.json")).write_text(json.dumps({
            "run_id": run_id, "suite_id": "primeira-bateria",
            "total": 1, "automatic_passes": 1, "ungraded": 0,
        }))
        item = next(x for x in lab_batches.suites() if x["id"] == "primeira-bateria")
        self.assertEqual(item["run_count"], 0)
        self.assertEqual(item["status"], "pending")
        (self.store / (run_id + ".json")).write_text("{}")
        updated = next(x for x in lab_batches.suites() if x["id"] == "primeira-bateria")
        self.assertEqual(updated["run_count"], 1)
        self.assertEqual(updated["last_report"]["automatic_failures"], 0)

    def test_routes_forward_optional_model_without_changing_default_calls(self):
        request = lab_batches_routes.QueueRequest(
            suite_ids=["primeira-bateria"], model="candidate:14b")
        with patch.object(lab_batches_routes.auth, "require_owner"), patch.object(
                lab_batches, "start_queue") as start_queue, patch.object(
                lab_batches, "start", return_value="run") as start:
            lab_batches_routes.run_batch_queue(request, None)
            start_queue.assert_called_once_with(["primeira-bateria"], model="candidate:14b")
            lab_batches_routes.run_batch("primeira-bateria", None, model="candidate:14b")
            start.assert_called_once_with("primeira-bateria", model="candidate:14b")
            lab_batches_routes.run_batch("primeira-bateria", None)
            start.assert_called_with("primeira-bateria")

    def test_invalid_model_route_returns_422_before_worker(self):
        self.suite("primeira-bateria", ["a1"])
        request = lab_batches_routes.QueueRequest(
            suite_ids=["primeira-bateria"], model="../../privado")
        with patch.object(lab_batches_routes.auth, "require_owner"):
            with self.assertRaises(HTTPException) as response:
                lab_batches_routes.run_batch_queue(request, None)
            self.assertEqual(response.exception.status_code, 422)
            self.assertFalse(lab_batches._RUNNING)

    def test_api_auth_and_input_errors_are_not_bypassed(self):
        request = lab_batches_routes.QueueRequest(suite_ids=["primeira-bateria"])
        with patch.object(lab_batches_routes.auth, "require_owner",
                          side_effect=HTTPException(401, "Unauthorized")):
            with self.assertRaises(HTTPException) as response:
                lab_batches_routes.run_batch_queue(request, None)
            self.assertEqual(response.exception.status_code, 401)
        with patch.object(lab_batches_routes.auth, "require_owner", return_value=None):
            with self.assertRaises(HTTPException) as response:
                lab_batches_routes.run_batch_queue(request, None)
            self.assertEqual(response.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
