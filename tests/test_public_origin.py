"""Public-origin and proxy authorization regressions (no network)."""
import os
import types
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from src.security import auth
from src.api import main

PUBLIC = "https://menor.example.com"


def request(host="menor.example.com", origin=PUBLIC, method="POST",
            client="127.0.0.1", scheme="http"):
    headers = {"host": host}
    if origin is not None:
        headers["origin"] = origin
    return types.SimpleNamespace(
        method=method, headers=headers,
        url=types.SimpleNamespace(scheme=scheme),
        client=types.SimpleNamespace(host=client),
        cookies={},
    )


class PublicOriginTests(unittest.TestCase):
    def test_https_canonical_and_invalid_origins(self):
        with patch.dict(os.environ, {"MENOR_PUBLIC_ORIGIN": PUBLIC}):
            self.assertEqual(auth.public_origin(), PUBLIC)
        for value in [
            "http://menor.example.com", "https://menor.example.com:8443",
            "https://menor.example.com/path", "https://user@menor.example.com",
            "https://127.0.0.1", "https://menor.example.com/",
            "https://menor.example.com?x=1",
            "https://MENOR.example.com", "https://-host.example.com",
        ]:
            with self.subTest(value=value), patch.dict(
                    os.environ, {"MENOR_PUBLIC_ORIGIN": value}):
                with self.assertRaises(RuntimeError):
                    auth.public_origin()

    def test_reverse_proxy_public_origin_enforced_even_if_internal_scheme_http(self):
        with patch.dict(os.environ, {"MENOR_PUBLIC_ORIGIN": PUBLIC}):
            auth.check_origin(request())
            for origin in (None, "http://menor.example.com",
                           "https://wrong.example.com", "null"):
                with self.subTest(origin=origin), self.assertRaises(HTTPException) as ctx:
                    auth.check_origin(request(origin=origin))
                self.assertEqual(ctx.exception.status_code, 403)

    def test_host_spoofing_denied_and_only_loopback_local_access(self):
        with patch.dict(os.environ, {"MENOR_PUBLIC_ORIGIN": PUBLIC}):
            for host in ("random.example.com", "menor.example.com.evil.net",
                         "example.com", "192.168.1.10:8000"):
                with self.subTest(host=host), self.assertRaises(HTTPException):
                    auth.check_origin(request(host=host))
            auth.check_origin(request(host="127.0.0.1:8000",
                                      origin="http://127.0.0.1:8000"))
            with self.assertRaises(HTTPException):
                auth.check_origin(request(host="127.0.0.1:8000",
                                          origin=None, client="10.10.0.2"))

    @patch("src.security.auth._private_network", return_value=True)
    def test_remote_mode_disables_first_owner_claim_even_via_loopback(self, network):
        with patch.dict(os.environ, {"MENOR_PUBLIC_ORIGIN": PUBLIC}):
            with self.assertRaises(HTTPException) as ctx:
                auth.create_owner(request(), "very-long-password")
            self.assertEqual(ctx.exception.status_code, 403)
            network.assert_not_called()

    def test_public_chat_never_reopens_anonymous_onboarding(self):
        with patch.dict(os.environ, {"MENOR_PUBLIC_ORIGIN": PUBLIC}):
            with patch("src.api.main.auth.configured", return_value=False), patch(
                    "src.api.main.auth.require_owner") as owner:
                main.require_chat_access(request())
                owner.assert_called_once()

    def test_session_cookie_secure_with_https_reverse_proxy(self):
        with patch.dict(os.environ, {"MENOR_PUBLIC_ORIGIN": PUBLIC}):
            response = MagicMock()
            auth.set_session_cookie(response, request(), "fake-token-not-a-credential")
            kwargs = response.set_cookie.call_args.kwargs
            self.assertTrue(kwargs["secure"])
            self.assertTrue(kwargs["httponly"])
            self.assertEqual(kwargs["samesite"], "strict")
            self.assertEqual(kwargs["path"], "/")

    def test_private_mode_cookie_and_origin_compatibility(self):
        with patch.dict(os.environ, {"MENOR_PUBLIC_ORIGIN": ""}):
            auth.check_origin(request(host="localhost:8000", scheme="http",
                                      origin="http://localhost:8000"))
            response = MagicMock()
            auth.set_session_cookie(response,
                request(host="localhost:8000", scheme="http",
                        origin="http://localhost:8000"), "opaque")
            self.assertFalse(response.set_cookie.call_args.kwargs["secure"])


if __name__ == "__main__":
    unittest.main()
