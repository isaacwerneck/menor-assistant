"""Pesquisa com contexto limitado e dados públicos sintéticos; sem Ollama real."""
import json
import os
import unittest
from unittest.mock import MagicMock, patch

import requests

from src.agent import research
from src.agent.context_engine import select_passages
from src.tools import web

URL = "https://docs.python.org/3/tutorial/controlflow.html"
PAGE = {"url": URL, "text": "Functions use the def keyword. " * 100,
        "accessed_at": "2026-10-19T22:00:00+00:00"}
CLAIMS = ([{"text": "Funções usam def.", "quote": "Functions use the def keyword.", "source": PAGE}], "")


class ResearchBudgetTests(unittest.TestCase):
    def test_late_relevant_passage_is_selected_literally(self):
        text = "navegação e índice " * 1200 + "\nFunctions use the def keyword.\n" + "rodapé " * 500
        selected = select_passages(text, "Python functions def")
        self.assertIn("Functions use the def keyword.", selected)
        self.assertLessEqual(len(selected), 2400)
        self.assertIn("[trecho omitido]", selected)
        for passage in selected.split("\n[trecho omitido]\n"):
            self.assertIn(passage, text)

    def test_small_sources_and_invalid_budgets(self):
        self.assertEqual(select_passages("texto curto", "texto"), "texto curto")
        for budget in (True, 0, 399, 12001, "2400"):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                select_passages("texto", "consulta", budget)

    @patch.object(web, "_download")
    def test_reader_selects_before_old_12000_character_cutoff(self, download):
        text = "navegação " * 1800 + "\nFunctions use the def keyword.\n"
        download.return_value = (URL, text, "text/plain")
        result = web.read(URL, query="functions def")
        self.assertIn("Functions use the def keyword.", result["text"])
        self.assertTrue(result["truncated"])
        self.assertLessEqual(len(result["text"]), 2400)
        self.assertNotIn("Functions use the def keyword.", web.read(URL)["text"])

    @patch.object(research.requests, "post")
    def test_planner_uses_small_typed_response_and_preserves_query(self, post):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {"message": {"content": json.dumps({
            "action": "research", "query": "Python functions def", "study": False,
        })}}
        post.return_value = response
        result = research.plan("Pesquise funções Python", [])
        self.assertEqual(result["query"], "Python functions def")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["options"]["num_predict"], 180)
        self.assertEqual(payload["format"]["properties"]["action"]["enum"], ["chat", "research"])
        self.assertIn("keep_alive", payload)
        post.assert_called_once()

    @patch.object(research, "investigate", return_value={"reply": "com fontes"})
    @patch.object(research, "plan")
    def test_no_save_decision_overrides_study_word(self, plan, investigate):
        for study in (False, None, "true"):
            plan.return_value = {"action": "research", "query": "Python functions", "study": study}
            research.handle("Pesquise Python; não estude nem salve nada.", [])
            investigate.assert_called_with("Python functions", None)
        plan.return_value = {"action": "research", "query": "Python functions", "study": True}
        research.handle("Estude programação Python e salve o estudo.", [])
        investigate.assert_called_with("Python functions", "programacao")

    @patch.object(research, "investigate", return_value={"reply": "evidência"})
    @patch.object(research, "plan")
    def test_contextual_query_skips_duplicate_model_classification(self, plan, investigate):
        result = research.handle("E a documentação dessa versão?", [], automatic=True,
                                 planned_query="Python 3.12 pathlib documentation")
        self.assertEqual(result["reply"], "evidência")
        plan.assert_not_called()
        investigate.assert_called_once_with("Python 3.12 pathlib documentation", None)

    @patch.object(research, "investigate")
    @patch.object(research, "plan")
    def test_preplanned_query_does_not_bypass_privacy_or_allow_study(self, plan, investigate):
        for query in ("api_key=segredo", "/home/isaac/segredo", "x", "x" * 281):
            with self.subTest(query=query):
                result = research.handle("Pesquise Python", [], planned_query=query)
                self.assertIn("Não consegui confirmar", result["reply"])
        plan.assert_not_called()
        investigate.assert_not_called()
        result = research.handle("pesquise minha senha do servidor", [],
                                 planned_query="Python documentation")
        self.assertIn("privados", result["reply"])
        investigate.assert_not_called()
        plan.return_value = {"action": "chat", "query": "", "study": False}
        result = research.handle("Estude Python mas não pesquise nem salve", [],
                                 planned_query="Python documentation")
        self.assertIsNone(result)
        plan.assert_called_once()
        investigate.assert_not_called()

    @patch.object(research, "_claims", return_value=CLAIMS)
    @patch.object(web, "read")
    @patch.object(web, "search")
    def test_failed_first_sources_do_not_hide_readable_fourth_result(self, search, read, claims):
        search.return_value = {"results": [{"url": URL + "?n=" + str(i)} for i in range(5)]}
        read.side_effect = [web.WebUnavailable("bloqueado")] * 3 + [PAGE, PAGE]
        result = research.investigate("Python functions def")
        self.assertIn("Funções usam def", result["reply"])
        self.assertEqual(read.call_count, 5)
        self.assertEqual(len(claims.call_args.args[1]), 2)

    @patch.object(research, "_claims", return_value=CLAIMS)
    @patch.object(web, "browse", return_value={**PAGE, "text": PAGE["text"] * 20})
    @patch.object(web, "read", return_value={**PAGE, "text": "curto"})
    @patch.object(web, "search", return_value={"results": [{"url": URL}] * 5})
    def test_browser_and_reader_share_context_and_source_limits(self, search, read, browse, claims):
        with patch.dict(os.environ, {"MENOR_BROWSER_ENABLED": "1"}):
            research.investigate("Python functions def")
        self.assertEqual(read.call_count, 3)
        sources = claims.call_args.args[1]
        self.assertEqual(len(sources), 3)
        self.assertLessEqual(sum(len(source["text"]) for source in sources), 7200)

    @patch.object(web, "search", side_effect=web.WebUnavailable("erro privado"))
    def test_search_failure_is_distinct_and_does_not_leak_error(self, search):
        result = research.investigate("Python functions")
        self.assertEqual(result["failure_stage"], "search")
        self.assertNotIn("erro privado", result["reply"])
        self.assertIsNone(result["saved"])

    @patch.object(web, "read", side_effect=web.WebUnavailable("bloqueado"))
    @patch.object(web, "search", return_value={"results": [{"url": URL}]})
    def test_unreadable_sources_are_distinct(self, search, read):
        self.assertEqual(research.investigate("Python functions")["failure_stage"], "read")

    @patch.object(research, "_claims", side_effect=requests.Timeout("erro privado"))
    @patch.object(web, "read", return_value=PAGE)
    @patch.object(web, "search", return_value={"results": [{"url": URL}]})
    def test_synthesis_failure_is_distinct_and_never_saves(self, search, read, claims):
        with patch.object(research, "_save") as save:
            result = research.investigate("Python functions", "programacao")
        self.assertEqual(result["failure_stage"], "synthesis")
        self.assertNotIn("erro privado", result["reply"])
        save.assert_not_called()

    @unittest.skipUnless(os.environ.get("MENOR_LIVE_WEB") == "1", "Leitura pública opt-in.")
    def test_live_python_documentation_with_selected_passages(self):
        result = web.read(URL, query="def functions Fibonacci")
        self.assertIn("def ", result["text"])
        self.assertLessEqual(len(result["text"]), 2400)
        self.assertEqual(result["url"], URL)

    @unittest.skipUnless(os.environ.get("MENOR_LIVE_WEB") == "1", "Busca pública opt-in.")
    def test_live_search_returns_public_results(self):
        result = web.search("site:docs.python.org Python functions def")
        self.assertTrue(result["results"])
        self.assertIn(result["provider"], ("duckduckgo-html", "bing-rss"))
        for item in result["results"]:
            web.public_url(item["url"])

    @patch.object(research, "_model")
    def test_omission_marker_is_never_accepted_as_source_quote(self, model):
        model.return_value = {"claims": [{"text": "Fato inventado", "source": 0,
                                         "quote": "[trecho omitido]"}], "limitations": ""}
        with self.assertRaises(ValueError):
            research._claims("Python", [{**PAGE, "text": "antes\n[trecho omitido]\ndepois"}])


if __name__ == "__main__":
    unittest.main()
