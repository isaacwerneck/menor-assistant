"""Contrato de modelo A/B, conciliação privada, publicação e painel passivo."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.api import lab_batches, lab_report_sync, lab_batches_routes, system_workspace
from ops import model_latency


class InlineThread:
    def __init__(self, target, args=(), daemon=False):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


class DeferredThread(InlineThread):
    def start(self):
        return None


class MultiModelTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name)
        stub = patch.object(lab_batches, "DATA", self.path)
        stub.start()
        self.addCleanup(stub.stop)
        with lab_batches._LOCK:
            self.old_state, self.old_running = dict(lab_batches.STATE), lab_batches._RUNNING
            lab_batches.STATE.clear()
            lab_batches.STATE["status"] = "idle"
            lab_batches._RUNNING = False
        self.addCleanup(self.restore)
        case = {"id": "um", "mode": "direct", "message": "Teste público"}
        case["expected_exact"] = "OK"
        suite = {"id": "comparacao-nova", "title": "Teste A/B", "cases": [case]}
        lab_batches.save_suite(json.dumps(suite).encode())

    def restore(self):
        with lab_batches._LOCK:
            lab_batches._RUNNING = self.old_running
            lab_batches.STATE.clear()
            lab_batches.STATE.update(self.old_state)

    def test_two_models_sequential_separate_reports_and_original_untouched(self):
        calls = []
        original = lab_batches.load_suite("comparacao-nova")

        def direct(request):
            calls.append(request.model)
            return {"status": "answered", "reply": "OK", "model": request.model}

        with (patch.object(lab_batches.threading, "Thread", InlineThread),
              patch.object(lab_batches.remote_lab, "_direct", side_effect=direct)):
            response = lab_batches.start_queue(
                ["comparacao-nova"], models=["local:7b", "local:14b"])
        self.assertEqual(calls, ["local:7b", "local:14b"])
        self.assertEqual(response["total"], 2)
        self.assertEqual(response["models"], calls)
        self.assertEqual(len(response["run_ids"]), 2)
        for name, run_id in zip(calls, response["run_ids"]):
            report = json.loads(lab_batches.report_path(run_id).read_text())
            self.assertEqual(report["evaluation_model"], name)
            self.assertEqual(report["cases"][0]["requested_model"], name)
        self.assertEqual(lab_batches.load_suite("comparacao-nova"), original)

    def test_duplicate_and_invalid_models_reject_without_inference(self):
        for models in ([], ["local:7b"] * 2, ["a", "b", "c"],
                       ["../secrets"], "local:7b"):
            with self.subTest(models=models), self.assertRaises(ValueError):
                lab_batches.start_queue(["comparacao-nova"], models=models)
        with self.assertRaises(ValueError):
            lab_batches.start_queue(["comparacao-nova"], model="a", models=["b"])
        self.assertFalse(lab_batches._RUNNING)

    def test_route_accepts_two_models_without_changing_legacy_model(self):
        with (patch.object(lab_batches_routes.auth, "require_owner"),
              patch.object(lab_batches, "start_queue") as run):
            body = lab_batches_routes.QueueRequest(
                suite_ids=["comparacao-nova"], models=["local:7b", "local:14b"])
            lab_batches_routes.run_batch_queue(body, object())
            run.assert_called_once_with(["comparacao-nova"],
                                        models=["local:7b", "local:14b"])


class SyncTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name)
        stub = patch.object(lab_batches, "DATA", self.path)
        stub.start()
        self.addCleanup(stub.stop)

    def add(self, run_id):
        report = {"run_id": run_id, "suite_id": "publica", "cases": [{"result": {"reply": "OK"}}]}
        (self.path / (run_id + ".json")).write_text(json.dumps(report))
        (self.path / (run_id + ".summary.json")).write_text(json.dumps({
            "run_id": run_id, "suite_id": "publica", "total": 1,
            "automatic_passes": 1, "automatic_failures": 0, "ungraded": 0}))
        return report

    def test_sync_uses_exact_git_blob_sha_and_detects_conflict(self):
        ids = ["20261021T010101Z-11111111", "20261021T010102Z-22222222",
               "20261021T010103Z-33333333"]
        data = [self.add(run_id) for run_id in ids]
        remote = {"truncated": False, "tree": [
            {"type": "blob", "path": "lab/reports/full/" + ids[0] + ".json",
             "sha": lab_report_sync._blob_sha(lab_report_sync._report_bytes(data[0]))},
            {"type": "blob", "path": "lab/reports/full/" + ids[2] + ".json",
             "sha": "0" * 40},
        ]}
        session = MagicMock()
        session.get.return_value.json.return_value = remote
        with patch.dict("os.environ", {"MENOR_LAB_GITHUB_TOKEN": "FAKE"}), patch.object(
                lab_report_sync.requests, "Session", return_value=session):
            result = lab_report_sync.sync_status()
        self.assertTrue(result["available"])
        self.assertEqual([result["items"][item] for item in ids],
                         ["sent", "not_sent", "conflict"])
        self.assertEqual(result["counts"]["sent"], 1)
        session.get.assert_called_once()

    def test_no_token_or_truncated_tree_never_claims_unsent(self):
        self.add("20261021T010101Z-11111111")
        with patch.dict("os.environ", {"MENOR_LAB_GITHUB_TOKEN": ""}):
            result = lab_report_sync.sync_status()
            self.assertFalse(result["available"])
            self.assertEqual(result["items"], {})
        session = MagicMock()
        session.get.return_value.json.return_value = {"truncated": True, "tree": []}
        with patch.dict("os.environ", {"MENOR_LAB_GITHUB_TOKEN": "FAKE"}), patch.object(
                lab_report_sync.requests, "Session", return_value=session):
            self.assertFalse(lab_report_sync.sync_status()["available"])

    def test_batch_validation_and_explicit_opt_in(self):
        run_id = "20261021T010101Z-11111111"
        self.add(run_id)
        with patch.dict("os.environ", {"MENOR_LAB_REPORTS_ALLOW_FULL_PUSH": "0",
                                       "MENOR_LAB_GITHUB_TOKEN": "FAKE"}):
            with self.assertRaises(RuntimeError):
                lab_report_sync.start_batch([run_id])
        with patch.dict("os.environ", {"MENOR_LAB_REPORTS_ALLOW_FULL_PUSH": "1",
                                       "MENOR_LAB_GITHUB_TOKEN": "FAKE"}):
            for ids in ([], [run_id, run_id], ["../invalido"]):
                with self.assertRaises((ValueError, FileNotFoundError)):
                    lab_report_sync.start_batch(ids)
            with patch.object(lab_report_sync.threading, "Thread", DeferredThread):
                result = lab_report_sync.start_batch([run_id])
                self.assertEqual(result["total"], 1)
                self.assertEqual(lab_report_sync.batch_state()["status"], "running")
        with lab_report_sync._LOCK:
            lab_report_sync._JOB = {"status": "idle"}


class LiveAndPerformanceTests(unittest.TestCase):
    def test_live_system_monitor_no_guessed_gpu_or_model_usage(self):
        cpu1 = {"cpu": (100, 30)}
        cpu2 = {"cpu": (200, 55)}
        info = {"MemTotal": 1024**3, "MemAvailable": 512 * 1024**2}
        session = MagicMock()
        session.__enter__.return_value = session
        session.json.return_value = {"models": [
            {"name": "qwen2.5-coder:7b", "size": 500 * 1024**2, "size_vram": 0}]}
        with (patch.object(system_workspace.auth, "require_owner"),
              patch.object(system_workspace.monitor, "cpu_times", side_effect=[cpu1, cpu2]),
              patch.object(system_workspace.monitor, "meminfo", return_value=info),
              patch.object(system_workspace, "_gpu_busy", return_value=None),
              patch.object(system_workspace.requests, "get", return_value=session),
              patch.object(system_workspace, "_PREVIOUS_CPU", None)):
            first = system_workspace.live_resources(object())
            second = system_workspace.live_resources(object())
        self.assertIsNone(first["cpu_percent"])
        self.assertEqual(second["cpu_percent"], 75.0)
        self.assertEqual(second["ram_percent"], 50.0)
        self.assertIsNone(second["gpu_percent"])
        self.assertEqual(second["loaded_models"][0]["gpu_loaded_mib"], 0)

    def test_thread_sweep_explicit_opt_in_and_no_secret_payload(self):
        reply = MagicMock()
        reply.__enter__.return_value = reply
        reply.json.return_value = {"message": {"content": "PUBLIC"},
                                   "eval_count": 16, "eval_duration": 2_000_000_000}
        post = MagicMock(return_value=reply)
        result = model_latency.thread_sweep(samples=2, post=post, model="local:7b")
        self.assertEqual([x["threads"] for x in result["variants"]], [1, 2, 4, 6, 8])
        self.assertEqual(post.call_count, 10)
        self.assertEqual([x.kwargs["json"]["options"]["num_thread"]
                          for x in post.call_args_list], [1, 2, 4, 6, 8, 8, 6, 4, 2, 1])
        self.assertNotIn("PUBLIC", str(result))


if __name__ == "__main__":
    unittest.main()
