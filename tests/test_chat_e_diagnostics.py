"""Chat E E5: API local consultiva deve ser autenticada e minimizada."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src.security import auth
from test_auth_memory import call
from test_file_api import request


class DiagnosticsEndpointTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        scope = patch.dict(os.environ, {"MENOR_DATA_DIR": tmp.name})
        scope.start()
        self.addCleanup(scope.stop)
        auth._attempts.clear()
        status, _, headers = call("/auth/setup", {"password": "senha-testes-privados-123"})
        self.assertEqual(status, 200)
        self.cookie = headers[b"set-cookie"].decode().split(";", 1)[0]

    def test_authentication_precedes_probes(self):
        with patch("src.api.private_diagnostics.run_checks") as probe:
            self.assertEqual(request("GET", "/ops/diagnostics")[0], 401)
            self.assertEqual(request("GET", "/ops/diagnostics", cookie="menor_session=invalid")[0], 401)
            probe.assert_not_called()

    def test_allowlist_removes_details_and_secret_inputs(self):
        fake = {"read_only": True, "status": "ok", "checks": [
            {"name": "api", "status": "ok", "detail": "API secret-password"},
            {"name": "ollama", "status": "warning", "detail": "/home/user/.ssh/id_ed25519"},
            {"name": "service", "status": "ok", "detail": "service private stuff"},
            {"name": "disk", "status": "ok", "detail": "volume name private"},
            {"name": "memory", "status": "ok", "detail": "1024 bytes"},
        ], "token": "do-not-publish"}
        with patch("src.api.private_diagnostics.run_checks", return_value=fake) as probe:
            status, answer = request("GET", "/ops/diagnostics", cookie=self.cookie)
        probe.assert_called_once_with()
        self.assertEqual(status, 200)
        self.assertEqual(answer["contract"], "menor.ops.observability")
        self.assertTrue(answer["read_only"])
        self.assertEqual(answer["components"]["api"]["status"], "ok")
        self.assertEqual(answer["components"]["ollama"]["status"], "warning")
        dumped = json.dumps(answer)
        for secret in ("secret-password", ".ssh", "id_ed25519", "do-not-publish",
                       "volume name", "private stuff"):
            self.assertNotIn(secret, dumped)
        self.assertNotIn("details", dumped)

    def test_unknown_states_are_not_upgraded_to_green(self):
        with patch("src.api.private_diagnostics.run_checks",
                   return_value={"read_only": True, "checks": []}):
            status, answer = request("GET", "/ops/diagnostics", cookie=self.cookie)
        self.assertEqual(status, 200)
        self.assertEqual(answer["components"]["service"]["status"], "unknown")
        self.assertNotEqual(answer["status"], "ok")

    def test_diagnostic_error_is_generic_and_not_leaked(self):
        with patch("src.api.private_diagnostics.run_checks", side_effect=OSError("secret=/tmp/passwords")):
            status, reply = request("GET", "/ops/diagnostics", cookie=self.cookie)
        self.assertEqual(status, 503)
        self.assertEqual(reply, {"status": "unavailable", "error": "diagnostics_unavailable"})

    def test_busy_probe_slots_refuse_extra_request(self):
        # O limite protege inclusive threads que continuem após timeout HTTP.
        from src.api.private_diagnostics import _SLOTS
        self.assertTrue(_SLOTS.acquire(blocking=False))
        self.assertTrue(_SLOTS.acquire(blocking=False))
        try:
            with patch("src.api.private_diagnostics.run_checks") as probe:
                status, answer = request("GET", "/ops/diagnostics", cookie=self.cookie)
            self.assertEqual(status, 503)
            self.assertEqual(answer["error"], "diagnostics_unavailable")
            probe.assert_not_called()
        finally:
            _SLOTS.release()
            _SLOTS.release()

    def test_probes_have_no_client_supplied_commands(self):
        with patch("src.api.private_diagnostics.run_checks",
                   return_value={"read_only": True, "checks": []}) as probe:
            status, _ = request("GET", "/ops/diagnostics?command=rm%20-rf%20--%20%2F",
                                cookie=self.cookie)
        self.assertEqual(status, 200)
        probe.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
