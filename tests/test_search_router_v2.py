import tempfile
import unittest
from unittest.mock import patch

from src.agent.orchestrator import Orchestrator
from src.memory.store import BrainStore
from src.tools.search_router import (
    classify_intent,
    reformulate_query,
    GroundedSearchEngine,
)


class TestSearchRouter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = BrainStore(data_dir=self.temp_dir.name)
        self.store.initialize()
        self.engine = GroundedSearchEngine(store=self.store)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_classify_intent(self):
        # 1. Pergunta de notícia/incidente recente (Web Grounding)
        q1 = "oq aconteceu esses dias que o pessoal tava falando de um ataque no php sla?"
        self.assertEqual(classify_intent(q1), "WEB_GROUNDING")

        q2 = "ouvi falar de um novo ataque de ransomware, o que aconteceu?"
        self.assertEqual(classify_intent(q2), "WEB_GROUNDING")

        q3 = "pesquise a documentação do FastAPI"
        self.assertEqual(classify_intent(q3), "WEB_GROUNDING")

        q4 = "qual o impacto da CVE-2024-4577?"
        self.assertEqual(classify_intent(q4), "WEB_GROUNDING")

        # 2. Saudação casual (Conversação pura)
        q5 = "opa eai menor, tudo bem com vc hj?"
        self.assertEqual(classify_intent(q5), "CONVERSATION")

        # 3. Ação local no sistema
        q6 = "leia o arquivo src/api/main.py e execute os testes com pytest"
        self.assertEqual(classify_intent(q6), "LOCAL_ACTION")

    def test_reformulate_query(self):
        raw = "oq aconteceu esses dias que o pessoal tava falando de um ataque no php sla?"
        ref = reformulate_query(raw)
        self.assertIn("primary_query", ref)
        self.assertIn("secondary_query", ref)
        # Termos de preenchimento devem ter sido removidos
        self.assertNotIn("esses dias", ref["primary_query"].lower())
        self.assertNotIn("que o pessoal tava falando", ref["primary_query"].lower())
        self.assertIn("php", ref["primary_query"].lower())
        self.assertIn("ataque", ref["primary_query"].lower())

    @patch("src.tools.search_router.search")
    @patch("src.tools.search_router.read")
    def test_search_and_ground_with_citations(self, mock_read, mock_search):
        mock_search.return_value = {
            "results": [
                {
                    "title": "CVE-2024-4577: Falha crítica de RCE no PHP para Windows",
                    "url": "https://example.com/cve-2024-4577",
                },
                {
                    "title": "PHP lança atualização de emergência para correção",
                    "url": "https://example.com/php-patch",
                },
            ]
        }
        mock_read.return_value = {
            "text": "A falha CVE-2024-4577 permite execução remota de código via Best-Fit mapping no PHP-CGI.",
        }

        res = self.engine.search_and_ground("ataque php recente")
        self.assertTrue(res["success"])
        self.assertEqual(len(res["citations"]), 2)
        self.assertIn("[1]", res["grounded_context"])
        self.assertIn("CVE-2024-4577", res["grounded_context"])
        self.assertIn("Análise de Risco no Ambiente", res["environment_risk"])
        # Como é PHP e nós usamos Python/FastAPI, deve confirmar segurança
        self.assertIn("imune", res["environment_risk"].lower())

    @patch("src.tools.search_router.GroundedSearchEngine.search_and_ground")
    @patch("src.agent.orchestrator.requests.post")
    def test_orchestrator_grounding_injection(self, mock_post, mock_ground):
        mock_ground.return_value = {
            "grounded_context": "=== CONTEXTO DE PESQUISA EM TEMPO REAL ===\n[1] CVE-2024-4577 PHP RCE",
            "environment_risk": "Ambiente seguro.",
        }
        mock_resp = unittest.mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "A falha recente é a CVE-2024-4577 [1], nosso ambiente está imune.",
            }
        }
        mock_post.return_value = mock_resp

        orch = Orchestrator(store=self.store)
        msgs = [{"role": "user", "content": "oq aconteceu esses dias no ataque do php?"}]

        # _needs_tools deve detectar WEB_GROUNDING
        self.assertTrue(orch._needs_tools(msgs))

        result = orch.run_turn(messages=msgs)
        self.assertIn("grounded_search", result.get("tools_executed", []))
        self.assertIn("CVE-2024-4577", result["reply"])


if __name__ == "__main__":
    unittest.main()
