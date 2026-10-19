"""Cloudflare and Netlify configuration tests, no network or credential usage."""
import tempfile
import unittest
from pathlib import Path

from ops.remote_access import hostname, render_config, tunnel_uuid
from scripts.build_netlify_site import build


TUNNEL = "123e4567-e89b-42d3-a456-426614174000"


class DeploymentConfigTests(unittest.TestCase):
    def test_hostname_validation_rejects_urls_shell_and_uncontrolled_origins(self):
        self.assertEqual(hostname("menor.example.com"), "menor.example.com")
        for item in (
            "example.com", "https://menor.example.com", "menor.example.com/path",
            "a;rm.example.com", "*.example.com", "Menor.example.com",
            "menor.example.com:443", "menor..example.com", "127.0.0.1",
            "menor.example.com?x=1",
        ):
            with self.subTest(item=item), self.assertRaises(ValueError):
                hostname(item)

    def test_config_targets_only_loopback_and_deny_by_default(self):
        with tempfile.TemporaryDirectory() as root:
            rendered = render_config(
                host="menor.example.com", tunnel_id=TUNNEL, home=root)
        self.assertIn("tunnel: " + TUNNEL, rendered)
        self.assertIn("hostname: menor.example.com", rendered)
        self.assertIn("service: http://127.0.0.1:8000", rendered)
        self.assertIn("service: http_status:404", rendered)
        self.assertIn(str(Path(root) / ".cloudflared" / (TUNNEL + ".json")), rendered)
        self.assertNotIn("token:", rendered)
        self.assertNotIn("ssh://", rendered)

    def test_id_cannot_be_token_or_path(self):
        self.assertEqual(tunnel_uuid(TUNNEL), TUNNEL)
        for value in ("../../secret.json", "MY-TOKEN", TUNNEL.upper(), "", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                tunnel_uuid(value)

    def test_build_static_landing_has_safe_https_link_and_no_proxy(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "landing.html"
            path.write_text('<a href="__MENOR_PRIVATE_URL__">Menor</a>')
            dist = Path(root) / "dist"
            target = build("https://menor.example.com", template=path, output_dir=dist)
            html = target.read_text()
            self.assertEqual(html, '<a href="https://menor.example.com/">Menor</a>')
            self.assertNotIn("__MENOR_", html)
            self.assertNotIn("token", html)
            self.assertEqual(list(dist.iterdir()), [target])

    def test_build_refuses_unconfigured_or_external_urls(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.html"
            path.write_text('__MENOR_PRIVATE_URL__')
            for url in ("", "http://menor.example.com", "https://example.com",
                        "https://menor.example.com/bad", "https://menor.example.com?x=1",
                        "https://evil.example.com@menor.example.com"):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    build(url, template=path, output_dir=Path(folder) / "output")


if __name__ == "__main__":
    unittest.main()
