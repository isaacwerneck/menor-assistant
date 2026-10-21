"""Testes sem inferência real para a gaveta de avaliação."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException
from src.api import lab_batches
from src.api import lab_batches_routes


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patcher = patch.object(lab_batches, "DATA", Path(self.temp.name))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        runtime = patch.multiple(lab_batches, STATE={"status": "idle"}, _RUNNING=False)
        runtime.start()
        self.addCleanup(runtime.stop)

    def test_builtin_suite(self):
        suite = lab_batches.load_suite("diagnostico-inicial")
        self.assertGreaterEqual(len(suite["cases"]), 4)

    def test_duplicate_ids_rejected(self):
        case = {"id": "same", "mode": "direct", "message": "Oi"}
        with self.assertRaises(ValueError):
            lab_batches.validate_suite({"id": "my-suite", "cases": [case, case]})

    def test_import_kept_outside_checkout(self):
        suite = {"id": "minha-suite", "cases": [
            {"id": "c1", "mode": "direct", "message": "Oi"}]}
        raw = json.dumps(suite).encode()
        self.assertEqual(lab_batches.save_suite(raw), "minha-suite")
        self.assertTrue((Path(self.temp.name) / "suites" / "minha-suite.json").exists())

    def test_report_id_path_traversal(self):
        with self.assertRaises(ValueError):
            lab_batches.report_path("../../etc/passwd")

    def test_routes_require_auth(self):
        with patch.object(lab_batches_routes.auth, "require_owner",
                          side_effect=HTTPException(401, "Unauthorized")):
            for endpoint in (lab_batches_routes.list_batches, lab_batches_routes.batch_reports):
                with self.assertRaises(HTTPException) as caught:
                    endpoint(None)
                self.assertEqual(caught.exception.status_code, 401)
            with self.assertRaises(HTTPException) as caught:
                lab_batches_routes.run_batch("diagnostico-inicial", None)
            self.assertEqual(caught.exception.status_code, 401)

    @patch.object(lab_batches.subprocess, "run")
    def test_checkout_snapshot_exports_only_validated_revision_and_dirty_flag(self, run):
        root = Path(lab_batches.__file__).resolve().parents[2]
        for changed in (0, 1):
            with self.subTest(changed=changed):
                run.side_effect = [Mock(returncode=0, stdout=str(root) + "\n" + "a" * 40 + "\n"),
                                   Mock(returncode=changed, stderr="PRIVATE")]
                snapshot = lab_batches._checkout_snapshot()
                self.assertEqual(snapshot, {"status": "observed", "revision": "a" * 40,
                                            "tracked_changes": changed == 1})
                self.assertNotIn(str(root), json.dumps(snapshot))
                self.assertNotIn("PRIVATE", json.dumps(snapshot))
                self.assertEqual(run.call_args.kwargs["timeout"], 2)

    @patch.object(lab_batches.subprocess, "run")
    def test_checkout_failures_never_export_error_text_or_guess_revision(self, run):
        root = Path(lab_batches.__file__).resolve().parents[2]
        for failure in (FileNotFoundError("PRIVATE"), subprocess.TimeoutExpired("PRIVATE", 2),
                        UnicodeError("PRIVATE"), Mock(returncode=128, stdout="PRIVATE"),
                        Mock(returncode=0, stdout=str(root) + "\nPRIVATE\n"),
                        Mock(returncode=0, stdout=str(root.parent) + "\n" + "a" * 40)):
            with self.subTest(kind=type(failure).__name__):
                run.side_effect = failure if isinstance(failure, Exception) else None
                run.return_value = failure
                self.assertEqual(lab_batches._checkout_snapshot(), {"status": "unavailable"})

    @patch.object(lab_batches.remote_lab, "_direct", return_value={"status": "answered", "reply": "4"})
    def test_report_records_checkout_checkpoints_without_changing_grades_or_summaries(self, direct):
        original = {"status": "observed", "revision": "a" * 40, "tracked_changes": False}
        changed = {"status": "observed", "revision": "b" * 40, "tracked_changes": False}
        dirty = {**original, "tracked_changes": True}
        suite = {"id": "test-provenance", "cases": [
            {"id": "simple", "mode": "direct", "message": "2+2?", "expected_exact": "4"}]}
        for index, (first, last, expected_changed, expected_dirty) in enumerate((
            (original, original, False, False), (original, changed, True, False),
            (changed, changed, True, False), (dirty, original, False, True),
            ({"status": "unavailable"}, original, None, None),
        )):
            with (
                self.subTest(index=index),
                patch.object(lab_batches, "_MODULE_IMPORT_CHECKOUT", original),
                patch.object(lab_batches, "_checkout_snapshot", side_effect=[first, last]),
            ):
                run_id = f"20261020T120000Z-{index:08x}"
                self.assertTrue(lab_batches._run(suite, run_id))
                report = json.loads((Path(self.temp.name) / (run_id + ".json")).read_text(encoding="utf-8"))
                provenance = report["code_provenance"]
                self.assertEqual(provenance["checkpoints"], {
                    "module_import": original, "run_start": first, "run_finish": last,
                })
                self.assertIs(provenance["revision_changed"], expected_changed)
                self.assertIs(provenance["tracked_changes"], expected_dirty)
                self.assertEqual(report["automatic_passes"], 1)
                summary = json.loads((Path(self.temp.name) / (run_id + ".summary.json")).read_text())
                self.assertNotIn("code_provenance", summary)
                self.assertNotIn("2+2?", json.dumps(summary))


if __name__ == "__main__":
    unittest.main()
