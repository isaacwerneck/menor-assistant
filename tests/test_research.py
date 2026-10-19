import os
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.agent import code_sandbox, research, runner, tool_builder
from src.agent.self_edit import ImprovementUnavailable
from src.memory.search import KnowledgeIndex
from src.memory.store import BrainStore
from src.tools import web
from src.tools.registry import perform

PAGE = {
    "url": "https://docs.python.org/3/tutorial/",
    "text": "Python functions are defined with the def keyword. " * 8,
    "accessed_at": "2026-10-18T22:00:00+00:00",
}
CLAIM = {"text": "Python define funções com def.", "source": 0,
         "quote": "Python functions are defined with the def keyword."}


class ResearchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.env = patch.dict(os.environ, {"MENOR_DATA_DIR": temporary.name, "MENOR_AUTONOMY_ENABLED": "0"})
        self.env.start()
        self.addCleanup(self.env.stop)
        if not hasattr(os, "fchmod"):
            permission = patch.object(os, "fchmod", create=True)
            permission.start()
            self.addCleanup(permission.stop)

    def test_private_dns_and_mixed_dns_are_rejected(self):
        for addresses in (["127.0.0.1"], ["10.0.0.1"], ["::1"], ["169.254.169.254"],
                          ["93.184.216.34", "192.168.0.1"], ["::ffff:127.0.0.1"]):
            records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in addresses]
            with self.subTest(addresses=addresses), patch.object(socket, "getaddrinfo", return_value=records):
                with self.assertRaises(ValueError):
                    web._address("example.org")

    def test_unsafe_url_and_dry_run_never_access_network(self):
        for url in ("file:///etc/passwd", "http://example.org", "https://user:pass@example.org",
                    "https://localhost/x", "https://example.org:8443/x"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                web.public_url(url)
        with patch.object(web, "_download") as download:
            self.assertEqual(perform("web.read", {"url": PAGE["url"]})["status"], "planned")
            download.assert_not_called()

    def test_html_reader_removes_scripts_and_search_resolves_result_links(self):
        html = '<script>secret()</script><h1>Python</h1><p>Funções com def.</p>'
        with patch.object(web, "_download", return_value=(PAGE["url"], html, "text/html")):
            result = web.read(PAGE["url"])
        self.assertIn("Funções com def.", result["text"])
        self.assertNotIn("secret", result["text"])
        result_html = (
            '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.python.org%2F">Python</a>'
            '<a class="result__a" href="javascript:bad()">Ruim</a><a class href>Incompleto</a>'
        )
        with patch.object(web, "_download", return_value=("https://html.duckduckgo.com", result_html, "text/html")):
            self.assertEqual(web.search("Python funções")["results"], [
                {"url": "https://docs.python.org/", "title": "Python"},
            ])

    @patch.object(research, "_model")
    def test_claim_must_reference_exact_page_text(self, model):
        model.return_value = {"claims": [{**CLAIM, "quote": "Isso não existe na página"}], "limitations": ""}
        with self.assertRaises(ValueError):
            research._claims("Python", [PAGE])
        model.return_value = {"claims": [{**CLAIM, "source": True}], "limitations": ""}
        with self.assertRaises(ValueError):
            research._claims("Python", [PAGE])

    @patch.object(research, "_model")
    def test_study_saves_sources_is_retrieved_and_deletion_is_indexed(self, model):
        model.return_value = {"claims": [CLAIM], "limitations": "Documentação Python 3; exemplos não executados."}
        with patch.object(web, "search", return_value={"results": [{"url": PAGE["url"]}]}):
            with patch.object(web, "read", return_value=PAGE):
                result = research.investigate("Como definir funções em Python?", "programacao")
        self.assertTrue(result["saved"].startswith("conhecimentos/programacao/"))
        store = BrainStore()
        note = store.read_note(result["saved"])
        self.assertIn(PAGE["url"], note)
        self.assertIn(PAGE["accessed_at"], note)
        matches = KnowledgeIndex(store).search("Python funções")
        self.assertEqual(matches[0]["source"], result["saved"])
        store._note_path(result["saved"]).unlink()
        self.assertEqual(KnowledgeIndex(store).search("Python funções"), [])

    @patch.object(research, "plan")
    @patch.object(web, "search")
    def test_unavailable_search_abstains_and_does_not_save(self, search, plan):
        plan.return_value = {"action": "research", "query": "Python funções"}
        search.side_effect = web.WebUnavailable("CAPTCHA")
        result = research.handle("Pesquise Python funções", [])
        self.assertIn("Não consegui confirmar", result["reply"])
        self.assertIsNone(result["saved"])
        self.assertEqual(list(BrainStore().brain_dir.glob("conhecimentos/*/*.md")), [])

    @patch.object(research, "handle")
    def test_runner_routes_explicit_study_before_tool_building(self, handle):
        handle.return_value = {"reply": "Estudo com fontes.", "saved": None}
        _, response = runner._advance({"phase": "idle"}, "Estude programação Python", [])
        self.assertEqual(response["reply"], "Estudo com fontes.")
        handle.assert_called_once()

    def test_browser_is_optional_and_reports_unavailability(self):
        with patch.dict(os.environ, {"MENOR_BROWSER_ENABLED": "0"}):
            with self.assertRaises(web.WebUnavailable):
                web.browse(PAGE["url"])

    def test_public_connection_uses_validated_ip_and_tls_hostname(self):
        response = MagicMock()
        response.status = 200
        response.getheader.side_effect = lambda name, default=None: {
            "Content-Type": "text/plain", "Content-Encoding": "identity",
        }.get(name, default)
        response.headers.get_content_charset.return_value = "utf-8"
        response.read1.side_effect = [b"public documentation", b""]
        with patch.object(web, "_address", return_value="93.184.216.34"):
            with patch.object(web.socket, "create_connection") as connect:
                with patch.object(web.ssl, "create_default_context") as tls:
                    with patch.object(web.http.client, "HTTPSConnection") as https:
                        https.return_value.getresponse.return_value = response
                        final, body, _ = web._download("https://example.org/docs")
        self.assertEqual(final, "https://example.org/docs")
        self.assertEqual(body, "public documentation")
        connect.assert_called_once_with(("93.184.216.34", 443), timeout=12)
        tls.return_value.wrap_socket.assert_called_once_with(connect.return_value, server_hostname="example.org")
        https.return_value.close.assert_called_once()

    @patch.object(research, "handle", return_value={"reply": "Fato com fonte.", "saved": None})
    def test_both_chat_endpoints_use_research_before_general_model(self, handle):
        from src.api import main
        request = main.ChatRequest(message="Pesquise funções Python")
        with patch.object(main, "open_ollama") as ollama:
            self.assertEqual(main.chat_sync(request).reply, "Fato com fonte.")
            response = main.chat_stream(request)
            self.assertEqual(response.media_type, "text/plain")
            ollama.assert_not_called()
        self.assertEqual(handle.call_count, 2)

    def test_explicit_programming_uses_existing_tool_loop(self):
        with patch.object(runner, "_tool_loop", return_value=({}, {"handled": True, "reply": "Plano"})) as loop:
            runner._advance({"phase": "idle"}, "Crie um conversor de texto em Python", [])
        loop.assert_called_once()

    def test_search_falls_back_without_accepting_xml_entities(self):
        rss = (
            "<rss><channel><item><title>Python</title>"
            "<link>https://docs.python.org/3/</link></item></channel></rss>"
        )
        with patch.object(web, "_download", side_effect=[
            web.WebUnavailable("HTTP 202"), ("https://www.bing.com", rss, "text/xml"),
        ]):
            self.assertEqual(web.search("Python funções")["provider"], "bing-rss")
        with patch.object(web, "_download", side_effect=[
            web.WebUnavailable("HTTP 202"),
            ("https://www.bing.com", '<!DOCTYPE rss [<!ENTITY x "unsafe">]><rss/>', "text/xml"),
        ]):
            with self.assertRaises(web.WebUnavailable):
                web.search("Python funções")

    @patch.object(runner, "_model_step")
    def test_build_still_requires_explicit_review_permission(self, model):
        model.return_value = {"action": "tool", "tool": "developer.build",
                              "arguments": {"name": "conversor", "goal": "Converter texto para maiúsculas"}}
        with patch.object(runner, "perform", return_value={"status": "planned"}) as execute:
            state, response = runner._tool_loop("Crie um conversor", [])
        self.assertEqual(state["phase"], "approval")
        self.assertIn("developer.build", response["reply"])
        execute.assert_called_once_with("developer.build", model.return_value["arguments"], dry_run=True)

    @unittest.skipUnless(os.environ.get("MENOR_LIVE_WEB") == "1", "Leitura real exige opção explícita.")
    def test_live_public_documentation(self):
        page = web.read("https://docs.python.org/3/tutorial/controlflow.html")
        self.assertIn("def", page["text"])
        self.assertTrue(web.search("site:docs.python.org Python def")["results"])


class BuilderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        environment = patch.dict(os.environ, {"MENOR_DATA_DIR": temporary.name})
        environment.start()
        self.addCleanup(environment.stop)

    def test_disabled_build_does_not_mutate_github(self):
        with patch.dict(os.environ, {"MENOR_AUTODEV_ENABLED": "0"}):
            with patch.object(tool_builder, "_github") as github:
                self.assertEqual(tool_builder.build("exemplo", "Converter texto em maiúsculas")["status"], "planned")
                with self.assertRaises(ImprovementUnavailable):
                    tool_builder.build("exemplo", "Converter texto em maiúsculas", dry_run=False)
                github.assert_not_called()
        for name in ("../bad", "os.system", "A", "_"):
            with self.assertRaises(ValueError):
                tool_builder.build(name, "Objetivo de programação")

    @patch.object(tool_builder, "verify")
    @patch.object(tool_builder, "_generate")
    @patch.object(tool_builder, "_source")
    @patch.object(tool_builder, "_github")
    def test_failed_sandbox_prevents_any_remote_write(self, github, source, generate, verify):
        github.return_value = {"object": {"sha": "snapshot123"}}
        source.side_effect = ["{}", "# Arquitetura"]
        generate.return_value = ("def run(text): return text", "test", "Identidade")
        verify.side_effect = ImprovementUnavailable("Testes falharam")
        with patch.dict(os.environ, {"MENOR_AUTODEV_ENABLED": "1", "MENOR_GITHUB_TOKEN": "fake"}):
            with self.assertRaises(ImprovementUnavailable):
                tool_builder.build("identidade", "Retornar o texto de entrada", dry_run=False)
        self.assertEqual([call.args[0] for call in github.call_args_list], ["GET"])

    @patch.object(tool_builder, "verify", return_value={"status": "passed", "log": "2 testes OK"})
    @patch.object(tool_builder, "_generate", return_value=("def run(text): return text", "test", "Identidade"))
    @patch.object(tool_builder, "_source", side_effect=["{}", "# Arquitetura"])
    @patch.object(tool_builder, "_github")
    def test_bundle_is_atomic_draft_and_not_ready(self, github, source, generate, verify):
        github.side_effect = [
            {"object": {"sha": "base123"}}, {"tree": {"sha": "tree123"}},
            {"sha": "newtree"}, {"sha": "newcommit"}, {},
            {"html_url": "https://github.com/owner/repo/pull/1"},
        ]
        with patch.dict(os.environ, {"MENOR_AUTODEV_ENABLED": "1", "MENOR_GITHUB_TOKEN": "fake"}):
            result = tool_builder.build("identidade", "Retornar o texto de entrada", dry_run=False)
        self.assertFalse(result["ready"])
        self.assertEqual(result["tests"], "passed")
        self.assertTrue(result["branch"].startswith("codex/"))
        calls = github.call_args_list
        self.assertEqual(len(calls[2].kwargs["json"]["tree"]), 4)
        self.assertTrue(calls[-1].kwargs["json"]["draft"])
        self.assertTrue(all(call.args[1] != "/merges" for call in calls))
        self.assertTrue(all(call.args[1] == "base123" for call in source.call_args_list))

    @patch.object(code_sandbox.shutil, "which", return_value="/usr/bin/docker")
    @patch.object(code_sandbox.subprocess, "run")
    def test_sandbox_limits_network_secrets_and_cleans_container(self, run, which):
        run.side_effect = [
            MagicMock(returncode=0, stdout="container", stderr=""),
            MagicMock(returncode=0, stdout="0\n", stderr=""),
            MagicMock(returncode=0, stdout="", stderr="Ran 2 tests in 0.001s\nOK"),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]
        with patch.dict(os.environ, {"MENOR_GITHUB_TOKEN": "never-copy"}):
            result = code_sandbox.verify("example", "def run(text): return text", "test")
        self.assertEqual(result["status"], "passed")
        first = run.call_args_list[0]
        self.assertIn("--network=none", first.args[0])
        self.assertIn("--read-only", first.args[0])
        self.assertIn("--pull=never", first.args[0])
        self.assertNotIn("MENOR_GITHUB_TOKEN", first.kwargs["env"])
        self.assertEqual(run.call_args_list[-1].args[0][1:3], ["rm", "--force"])

    @patch.object(code_sandbox.shutil, "which", return_value="/usr/bin/docker")
    @patch.object(code_sandbox.subprocess, "run")
    def test_timeout_still_removes_container(self, run, which):
        run.side_effect = [
            MagicMock(returncode=0, stdout="container", stderr=""),
            subprocess.TimeoutExpired("docker wait", 25),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]
        with self.assertRaises(ImprovementUnavailable):
            code_sandbox.verify("example", "def run(text): return text", "test")
        self.assertEqual(run.call_args_list[-1].args[0][1:3], ["rm", "--force"])


if __name__ == "__main__":
    unittest.main()
