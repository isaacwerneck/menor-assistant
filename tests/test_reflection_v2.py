from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from src.agent.reflection import ReflectionWorker
from src.agent.workers import TaskQueue
from src.memory.core_memory import CoreMemoryManager
from src.memory.store import BrainStore


class TestReflectionWorker(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = BrainStore(data_dir=self.temp_dir.name)
        self.store.initialize()
        self.db_path = Path(self.temp_dir.name) / "tasks.db"
        self.queue = TaskQueue(db_path=str(self.db_path))
        self.worker = ReflectionWorker(
            store=self.store,
            queue=self.queue,
            ollama_url="http://127.0.0.1:11434",
            model="qwen-fast:latest",
        )

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_reflect_empty_events(self):
        res = self.worker.reflect(events=[])
        self.assertTrue(res["success"])
        self.assertEqual(res["events_analyzed"], 0)
        self.assertEqual(res["learnings_added"], 0)

    @patch("requests.post")
    def test_reflect_with_llm_synthesis(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "content": '{"learnings": ["Testes unitários automatizados evitam regressões"], '
                           '"profile_updates": ["Isaac prefere código direto sem boilerplate"]}'
            }
        }
        mock_post.return_value = mock_resp

        events = [
            "Projeto [menor]: Criou testes unitários para a busca híbrida -> Concluído com sucesso",
        ]
        res = self.worker.reflect(events=events)

        self.assertTrue(res["success"])
        self.assertEqual(res["learnings_added"], 1)
        self.assertEqual(res["profile_updates"], 1)

        # Verificar se gravou no aprendizados_gerais.md
        note = self.store.read_note("conhecimentos/aprendizados_gerais.md")
        self.assertIn("Testes unitários automatizados evitam regressões", note)

        # Verificar se gravou no perfil do Core Memory
        core_mem = CoreMemoryManager(self.store)
        profile = core_mem.get_block("user_profile")
        self.assertIn("Isaac prefere código direto sem boilerplate", profile)

    @patch("requests.post")
    def test_reflect_anti_pattern_separation(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "content": (
                    '{"learnings": [], "anti_patterns": ["Usar time.sleep no async loop"], '
                    '"profile_updates": []}'
                )
            }
        }
        mock_post.return_value = mock_resp

        events = [
            "Projeto [menor]: Adicionar sleep síncrono -> FALHOU / BUG ENCONTRADO: EventLoop bloqueado",
        ]
        res = self.worker.reflect(events=events)
        self.assertTrue(res["success"])
        self.assertEqual(res["anti_patterns_added"], 1)
        self.assertEqual(res["learnings_added"], 0)
        note = self.store.read_note("conhecimentos/aprendizados_gerais.md")
        self.assertIn("[ANTI-PADRÃO - EVITAR]", note)

    @patch("requests.post", side_effect=Exception("Connection refused"))
    def test_reflect_fallback_when_offline(self, mock_post):
        # Quando Ollama estiver offline ou der timeout, deve acionar fallback heurístico
        task_id = self.queue.enqueue("Refatorar endpoint SSE", "api")
        self.queue.update_status(task_id, "completed", result="Reduziu latência em 400ms")

        res = self.worker.reflect()
        self.assertTrue(res["success"])
        self.assertGreaterEqual(res["events_analyzed"], 1)


if __name__ == "__main__":
    unittest.main()
