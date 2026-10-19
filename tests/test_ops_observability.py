"""Contrato de observabilidade V1: testes sem servidor nem dados pessoais."""

import json
import unittest

from ops import smoke, receipt_contract
from ops.doctor import Check
from ops.observability import BoundedHistory, build_snapshot


SECRET = "SECRET_xPrivada:/home/alguem/cerebro/chave-123"


def doctor_report(ollama="ok"):
    return {
        "status": "ok", "read_only": True,
        "checks": [
            {"name": name, "status": ollama if name == "ollama" else "ok", "detail": SECRET}
            for name in ("api", "ollama", "service", "disk", "memory")
        ],
    }


def smoke_report(overrides=None):
    values = {"api_contract": "ok"}
    values.update({name: "ok" for name, _path in smoke.PRIVATE_GET})
    values.update(overrides or {})
    return {
        "status": "ok", "read_only": True, "authenticated": False,
        "checks": [{"name": name, "status": status, "detail": SECRET}
                   for name, status in values.items()],
    }


def zero_metrics():
    return {
        "queues": {"pending": 0, "active": 0},
        "tasks": {"running": 0, "blocked": 0, "failed": 0},
        "errors": {"recent": 0},
    }


def full_snapshot(**changes):
    kwargs = {
        "doctor_report": doctor_report(),
        "smoke_report": smoke_report(),
        "receipt_checks": [Check("tool_receipt", "ok", SECRET)],
        "aggregates": zero_metrics(),
    }
    kwargs.update(changes)
    return build_snapshot(**kwargs)


class ObservabilityTests(unittest.TestCase):
    def test_unknown_is_not_silently_healthy_when_no_evidence(self):
        report = build_snapshot()
        self.assertEqual(report["contract"], "menor.ops.observability")
        self.assertEqual(report["contract_version"], 1)
        self.assertTrue(report["read_only"])
        self.assertEqual(report["assurance"], "partial_structural_observation")
        self.assertEqual(report["status"], "unknown")
        self.assertEqual(report["history"], [])
        self.assertTrue(all(value["status"] == "unknown"
                            for value in report["components"].values()))
        self.assertTrue(report["collected_at"].endswith("Z"))
        json.dumps(report)

    def test_all_components_covered_does_not_claim_real_execution(self):
        result = full_snapshot()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["components"]["receipts"]["checked"], 1)
        self.assertEqual(result["components"]["ollama"]["evidence"], "api_health_claim_only")
        self.assertEqual(result["components"]["private_routes"]["evidence"], "known_anonymous_routes_only")
        self.assertNotIn(SECRET, json.dumps(result))

    def test_offline_ollama_is_warning_even_when_api_responds(self):
        result = full_snapshot(doctor_report=doctor_report(ollama="warning"))
        self.assertEqual(result["components"]["api"]["status"], "ok")
        self.assertEqual(result["components"]["ollama"]["status"], "warning")
        self.assertEqual(result["status"], "warning")

    def test_denied_anonymous_access_requires_all_known_routes(self):
        first_name = smoke.PRIVATE_GET[0][0]
        report = full_snapshot(smoke_report=smoke_report({first_name: "critical"}))
        self.assertEqual(report["components"]["private_routes"]["status"], "critical")
        self.assertEqual(report["status"], "critical")
        missing = smoke_report()
        missing["checks"] = [row for row in missing["checks"] if row["name"] != first_name]
        report = full_snapshot(smoke_report=missing)
        self.assertEqual(report["components"]["private_routes"]["status"], "unknown")
        self.assertNotEqual(report["status"], "ok")

    def test_untrusted_anonymous_or_inconsistent_reports_fail_closed(self):
        authenticated = smoke_report()
        authenticated["authenticated"] = True
        result = full_snapshot(smoke_report=authenticated)
        self.assertEqual(result["components"]["private_routes"]["status"], "unknown")
        invalid = smoke_report()
        invalid["read_only"] = "yes"
        self.assertEqual(full_snapshot(smoke_report=invalid)
                         ["components"]["api_contract"]["status"], "unknown")
        duplicate = doctor_report()
        duplicate["checks"].append({"name": "api", "status": "ok", "detail": SECRET})
        self.assertEqual(full_snapshot(doctor_report=duplicate)
                         ["components"]["api"]["status"], "critical")

    def test_no_raw_values_error_messages_and_private_paths_are_serialized(self):
        data = zero_metrics()
        data["message"] = SECRET
        data["errors"]["last_exception"] = SECRET
        data["tasks"]["session_id"] = SECRET
        data["queues"]["items"] = [{"prompt": SECRET}]
        injected = full_snapshot(aggregates=data)
        self.assertNotIn(SECRET, json.dumps(injected, ensure_ascii=False))
        self.assertNotIn("session_id", json.dumps(injected))
        self.assertEqual(injected["components"]["errors"]["bands"]["recent"], "0")

    def test_non_integer_negative_and_oversized_counts_are_not_accepted(self):
        for value in (True, -1, 1.2, SECRET, 1_000_000_001, None):
            with self.subTest(value=value):
                counts = zero_metrics()
                counts["queues"]["pending"] = value
                result = full_snapshot(aggregates=counts)
                self.assertEqual(result["components"]["queues"]["status"], "unknown")
                self.assertEqual(result["status"], "unknown")

    def test_metrics_emit_only_bands_and_warning_thresholds(self):
        counts = zero_metrics()
        counts["queues"] = {"pending": 78, "active": 2}
        counts["tasks"] = {"running": 11, "blocked": 1, "failed": 0}
        counts["errors"] = {"recent": 1}
        report = full_snapshot(aggregates=counts)
        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["components"]["queues"]["bands"]["pending"], "50+")
        self.assertEqual(report["components"]["tasks"]["bands"]["running"], "10-49")
        self.assertNotIn("78", json.dumps(report))

    def test_receipts_are_structural_evidence_and_contained(self):
        valid = receipt_contract.tool_receipt(
            {"tool": "projects.list", "status": "planned", "writes": False, "arguments": []}
        )
        report = full_snapshot(receipt_checks=[valid])
        self.assertEqual(report["components"]["receipts"]["status"], "ok")
        self.assertEqual(report["components"]["receipts"]["evidence"], "structure_only")
        bad = receipt_contract.tool_receipt(
            {"tool": "projects.list", "status": "executed", "result": SECRET}
        )
        self.assertEqual(bad.status, "ok")
        report = full_snapshot(receipt_checks=[bad])
        self.assertNotIn(SECRET, json.dumps(report))
        report = full_snapshot(receipt_checks=[{"name": SECRET}])
        self.assertEqual(report["components"]["receipts"]["status"], "unknown")

    def test_history_is_bounded_and_does_not_capture_or_alias_snapshots(self):
        history = BoundedHistory(max_entries=2)
        for status in ("ok", "warning", SECRET):
            history.add({"status": status, "payload": SECRET})
        entries = history.recent()
        self.assertEqual(len(entries), 2)
        self.assertEqual([row["status"] for row in entries], ["warning", "unknown"])
        entries[0]["status"] = SECRET
        self.assertEqual(history.recent()[0]["status"], "warning")
        result = build_snapshot(history=history)
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertEqual(len(result["history"]), 2)

    def test_history_rejects_unbounded_config_and_untrusted_history(self):
        for value in (0, 25, True, "24"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                BoundedHistory(value)
        report = full_snapshot(history=[{"raw": SECRET}])
        self.assertEqual(report["history"], [])

    def test_snapshot_never_performs_probes_or_network_io(self):
        # Interface pura: nenhuma dependência de API, banco ou disco.
        report = build_snapshot(
            doctor_report=doctor_report(), smoke_report=smoke_report(),
            receipt_checks=[Check("tool_receipt", "ok", SECRET)], aggregates=zero_metrics(),
        )
        self.assertTrue(report["read_only"])
        self.assertEqual(report["components"]["api"]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
