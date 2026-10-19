"""Unittests sem servidor: garantem que o smoke não modifica o Menor."""

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from ops import smoke


def fake_http(status, body=b""):
    connection = MagicMock()
    response = connection.getresponse.return_value
    response.status = status
    response.read.return_value = body
    return connection


def healthy():
    return json.dumps({
        "status": "online",
        "service": "Menor API",
        "api_contract": 1,
        "default_model": "qwen2.5-coder:7b",
        "version": "0.4.1",
        "ollama_status": "offline",
    }).encode("utf-8")


class SmokeTests(unittest.TestCase):
    @patch("ops.smoke.http.client.HTTPConnection")
    def test_reads_only_loopback_and_never_reads_private_response_bodies(self, conn):
        instances = [fake_http(200, healthy())]
        instances += [fake_http(401, b"CONTEUDO PRIVADO") for _ in smoke.PRIVATE_GET]
        conn.side_effect = instances
        report = smoke.run_smoke(port=8022, timeout=1.25)
        self.assertEqual(report["status"], "ok")
        self.assertTrue(report["read_only"])
        self.assertFalse(report["authenticated"])
        self.assertEqual(len(report["checks"]), len(smoke.PRIVATE_GET) + 1)
        for index, instance in enumerate(instances):
            path = "/health" if index == 0 else smoke.PRIVATE_GET[index - 1][1]
            instance.request.assert_called_once_with("GET", path, headers={"Accept": "application/json"})
            instance.close.assert_called_once()
            if index:
                instance.getresponse.return_value.read.assert_not_called()
        self.assertEqual(conn.call_count, len(instances))
        for args, kwargs in conn.call_args_list:
            self.assertEqual(args, ("127.0.0.1", 8022))
            self.assertEqual(kwargs, {"timeout": 1.25})

    @patch("ops.smoke.http.client.HTTPConnection")
    def test_accessible_private_route_is_critical(self, conn):
        responses = [fake_http(200, healthy())]
        responses += [fake_http(200 if index == 2 else 403) for index in range(len(smoke.PRIVATE_GET))]
        conn.side_effect = responses
        result = smoke.run_smoke()
        self.assertEqual(result["status"], "critical")
        self.assertEqual(result["checks"][3]["status"], "critical")
        self.assertNotIn("CONTEUDO PRIVADO", json.dumps(result))

    @patch("ops.smoke.http.client.HTTPConnection")
    def test_redirect_missing_or_server_error_are_not_success(self, conn):
        for invalid_code in (302, 404, 500):
            with self.subTest(code=invalid_code):
                conn.side_effect = (
                    [fake_http(200, healthy())]
                    + [fake_http(invalid_code)]
                    + [fake_http(401) for _ in smoke.PRIVATE_GET[1:]]
                )
                result = smoke.run_smoke()
                self.assertEqual(result["status"], "critical")
                self.assertEqual(result["checks"][1]["status"], "critical")

    @patch("ops.smoke.http.client.HTTPConnection")
    def test_invalid_health_skips_private_requests(self, conn):
        for payload in (b"{}", b"[]", b"not json", b'{"status":"online"}', b"x" * 8200):
            with self.subTest(payload=payload[:10]):
                conn.reset_mock()
                conn.side_effect = [fake_http(200, payload)]
                report = smoke.run_smoke()
                self.assertEqual(report["checks"][0]["status"], "critical")
                self.assertTrue(all(c["status"] == "skipped" for c in report["checks"][1:]))
                self.assertEqual(conn.call_count, 1)

    @patch("ops.smoke.http.client.HTTPConnection")
    def test_health_response_status_must_be_200(self, conn):
        conn.return_value = fake_http(503, healthy())
        report = smoke.run_smoke()
        self.assertEqual(report["status"], "critical")
        conn.assert_called_once()

    def test_contract_must_have_typed_version_and_model(self):
        good = json.loads(healthy())
        self.assertTrue(smoke._health_contract(good))
        for name, invalid in (("api_contract", True), ("api_contract", 0),
                              ("default_model", ""), ("version", ""),
                              ("ollama_status", "unknown"), ("service", "fake")):
            with self.subTest(name=name, value=invalid):
                bad = dict(good, **{name: invalid})
                self.assertFalse(smoke._health_contract(bad))

    @patch("ops.smoke.http.client.HTTPConnection")
    def test_connection_failure_never_exposes_exception_message(self, conn):
        conn.return_value.request.side_effect = OSError("senha-e-token-secreto")
        report = smoke.run_smoke()
        self.assertEqual(report["status"], "critical")
        self.assertNotIn("senha-e-token-secreto", json.dumps(report))
        conn.return_value.close.assert_called_once()

    @patch("ops.smoke.run_smoke")
    def test_cli_json_and_exit_status(self, probe):
        probe.return_value = {"status": "critical", "read_only": True, "authenticated": False, "checks": []}
        output = io.StringIO()
        with redirect_stdout(output):
            result = smoke.main(["--json", "--port", "8012"])
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "critical")
        probe.assert_called_once_with(port=8012, timeout=2.0)

    def test_invalid_ports_and_timeouts_are_rejected(self):
        for args in (["--port", "0"], ["--port", "65536"], ["--timeout", "-1"]):
            with self.subTest(args=args):
                with patch("sys.stderr", new=io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        smoke.main(args)
                self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
