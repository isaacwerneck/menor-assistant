"""Regressões do diagnóstico: nenhum teste requer Ollama ou systemd real."""

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from ops import doctor


class DoctorTests(unittest.TestCase):
    @staticmethod
    def fake_connection(status=200, payload=None):
        connection = MagicMock()
        response = connection.getresponse.return_value
        response.status = status
        response.read.return_value = json.dumps(payload if payload is not None else {
            "status": "online", "service": "Menor API", "ollama_status": "online",
        }).encode()
        return connection

    @patch("ops.doctor.http.client.HTTPConnection")
    def test_api_checks_loopback_health_without_redirects(self, conn):
        instance = self.fake_connection()
        conn.return_value = instance
        checks = doctor.check_api(port=8010, timeout=1)
        self.assertEqual([c.status for c in checks], ["ok", "ok"])
        conn.assert_called_once_with("127.0.0.1", 8010, timeout=1)
        instance.request.assert_called_once_with("GET", "/health", headers={"Accept": "application/json"})
        instance.getresponse.return_value.read.assert_called_once_with(doctor._MAX_HEALTH_BYTES + 1)
        instance.close.assert_called_once()

    @patch("ops.doctor.http.client.HTTPConnection")
    def test_ollama_offline_is_not_reported_as_healthy(self, conn):
        conn.return_value = self.fake_connection(
            payload={"status": "online", "service": "Menor API", "ollama_status": "offline"},
        )
        self.assertEqual([c.status for c in doctor.check_api()], ["ok", "warning"])

    @patch("ops.doctor.http.client.HTTPConnection")
    def test_http_redirect_and_malformed_health_are_fail_closed(self, conn):
        for status, payload in [(302, None), (200, {"status": "starting"}), (200, {"status": "online"}), (200, [])]:
            with self.subTest(status=status, payload=payload):
                conn.return_value = self.fake_connection(status, payload)
                self.assertEqual([c.status for c in doctor.check_api()], ["critical", "skipped"])

    @patch("ops.doctor.http.client.HTTPConnection")
    def test_oversized_health_is_rejected(self, conn):
        conn.return_value = self.fake_connection()
        conn.return_value.getresponse.return_value.read.return_value = b"a" * (doctor._MAX_HEALTH_BYTES + 1)
        self.assertEqual(doctor.check_api()[0].status, "critical")

    @patch("ops.doctor.http.client.HTTPConnection")
    def test_local_connection_failure_has_no_private_error_text(self, conn):
        conn.return_value.request.side_effect = OSError("token-super-secreto")
        result = doctor.check_api()
        self.assertEqual(result[0].status, "critical")
        self.assertNotIn("token-super-secreto", result[0].detail)
        conn.return_value.close.assert_called_once()

    @patch("ops.doctor.subprocess.run")
    def test_service_check_never_executes_shell(self, run):
        run.return_value = MagicMock(returncode=0, stdout="active\n")
        self.assertEqual(doctor.check_service().status, "ok")
        run.assert_called_once_with(
            ["systemctl", "--user", "is-active", "menor-api.service"],
            capture_output=True, text=True, timeout=2, check=False,
        )

    @patch("ops.doctor.subprocess.run", side_effect=FileNotFoundError)
    def test_service_missing_systemd_is_skipped(self, _run):
        self.assertEqual(doctor.check_service().status, "skipped")

    @patch("ops.doctor.shutil.disk_usage")
    @patch("ops.doctor.Path.exists", return_value=True)
    def test_disk_thresholds(self, _exists, usage):
        for free, expected in [(300 * doctor._MIB, "critical"),
                               (doctor._GIB, "warning"), (3 * doctor._GIB, "ok")]:
            with self.subTest(free=free):
                usage.return_value = MagicMock(free=free)
                self.assertEqual(doctor.check_disk().status, expected)

    @patch("ops.doctor.Path.read_text", return_value="MemTotal: 1000000 kB\nMemAvailable: 400000 kB\n")
    def test_memory_low_is_warning(self, _read):
        self.assertEqual(doctor.check_memory().status, "warning")

    @patch("ops.doctor.check_memory", return_value=doctor.Check("memory", "ok", "ok"))
    @patch("ops.doctor.check_disk", return_value=doctor.Check("disk", "ok", "ok"))
    @patch("ops.doctor.check_service", return_value=doctor.Check("service", "ok", "ok"))
    @patch("ops.doctor.check_api", return_value=[doctor.Check("api", "ok", "ok"),
                                                 doctor.Check("ollama", "warning", "offline")])
    def test_json_and_exit_code_reflect_warning(self, *_checks):
        output = io.StringIO()
        with redirect_stdout(output):
            code = doctor.main(["--json"])
        self.assertEqual(code, 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "warning")
        self.assertTrue(report["read_only"])
        self.assertEqual(len(report["checks"]), 5)

    def test_bad_arguments_are_rejected(self):
        for argv in (["--port", "0"], ["--port", "65536"], ["--timeout", "100"]):
            with self.subTest(argv=argv), redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    doctor.main(argv)
                self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
