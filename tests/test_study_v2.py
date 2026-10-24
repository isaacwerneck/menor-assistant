"""Testes unitários do motor de estudo contínuo, preempção e auto-diagnóstico."""

import os
import shutil
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

from src.agent.study import CheckpointManager, DiagnosticEngine, StudyWorker, TopicManager
from src.memory.store import BrainStore
from src.tools.core import TOOL_DISPATCHER, schedule_study_topic
from src.tools.web import multi_search


class TestStudyEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_study_")
        self.store = BrainStore(data_dir=self.temp_dir)
        self.store.initialize()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_topic_manager_save_and_list(self):
        tm = TopicManager(store=self.store)
        topics = tm.list_topics(uncompleted_only=True)
        self.assertTrue(len(topics) >= 4)

        res = tm.save_topic("FastAPI WebSockets Avançado", category="software", priority="high")
        self.assertTrue(res["success"])

        updated_topics = tm.list_topics(uncompleted_only=True)
        found = any("FastAPI WebSockets Avançado" in t["text"] for t in updated_topics)
        self.assertTrue(found)

        marked = tm.mark_completed("FastAPI WebSockets Avançado")
        self.assertTrue(marked)

        remaining = tm.list_topics(uncompleted_only=True)
        self.assertFalse(any("FastAPI WebSockets Avançado" in t["text"] for t in remaining))

    def test_topic_manager_auto_generation(self):
        tm = TopicManager(store=self.store)
        tm.file_path.write_text("# Temas de Estudo\n\n", encoding="utf-8")
        generated = tm.auto_generate_topics(count=2)
        self.assertEqual(len(generated), 2)
        active = tm.list_topics(uncompleted_only=True)
        self.assertEqual(len(active), 2)

    def test_checkpoint_manager_save_load_clear(self):
        cm = CheckpointManager(store=self.store)
        self.assertIsNone(cm.load_checkpoint())

        cm.save_checkpoint("CSS Container Queries", step="reading", urls_processed=["https://example.com"])
        data = cm.load_checkpoint()
        self.assertIsNotNone(data)
        self.assertEqual(data["topic"], "CSS Container Queries")
        self.assertEqual(data["step"], "reading")
        self.assertEqual(data["urls_processed"], ["https://example.com"])

        cm.clear_checkpoint()
        self.assertIsNone(cm.load_checkpoint())

    @patch("src.agent.study.web_read")
    @patch("src.agent.study.multi_search")
    def test_study_cycle_with_abort_preemption(self, mock_search, mock_read):
        mock_search.return_value = {
            "query": "Test Topic",
            "results": [{"url": "https://example.com", "title": "Example"}],
            "sources": ["web"],
        }
        mock_read.return_value = {"text": "Documentação sobre concorrência e event loop."}

        worker = StudyWorker(store=self.store, ollama_url="http://mocked-offline:11434")
        abort_event = threading.Event()
        abort_event.set()

        res = worker.study_cycle(max_topics=1, abort_event=abort_event)
        self.assertTrue(res["interrupted"])
        self.assertEqual(res["studied"], 0)

    @patch("requests.post")
    @patch("src.agent.study.web_read")
    @patch("src.agent.study.multi_search")
    def test_study_cycle_full(self, mock_search, mock_read, mock_post):
        mock_search.return_value = {
            "query": "Test Topic",
            "results": [{"url": "https://example.com", "title": "Example"}],
            "sources": ["web"],
        }
        mock_read.return_value = {"text": "Documentação sobre concorrência e event loop."}

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "content": (
                    "- Conceito: Padrão moderno de concorrência.\n"
                    "- Código: async def run(): pass\n"
                    "- Gotchas: Cuidado com loops bloqueantes."
                )
            }
        }
        mock_post.return_value = mock_resp

        worker = StudyWorker(store=self.store)
        res = worker.study_cycle(max_topics=1)
        self.assertTrue(res["success"])
        self.assertGreaterEqual(res["studied"], 1)

    @patch("requests.post")
    def test_diagnostic_engine_high_score(self, mock_post):
        mock_resp_student = MagicMock()
        mock_resp_student.status_code = 200
        mock_resp_student.json.return_value = {
            "message": {"content": "Use starlette run_in_threadpool para não travar o loop."}
        }

        mock_resp_judge = MagicMock()
        mock_resp_judge.status_code = 200
        mock_resp_judge.json.return_value = {
            "message": {
                "content": '{"score": 9.0, "critique": "Excelente resposta.", "gap_identified": ""}'
            }
        }
        mock_post.side_effect = [mock_resp_student, mock_resp_judge]

        engine = DiagnosticEngine(store=self.store)
        res = engine.run_self_eval()
        self.assertTrue(res["success"])
        self.assertEqual(res["score"], 9.0)
        self.assertFalse(res["gap_scheduled"])
        self.assertTrue(os.path.exists(res["report_path"]))

    @patch("requests.post")
    def test_diagnostic_engine_low_score_triggers_gap(self, mock_post):
        mock_resp_student = MagicMock()
        mock_resp_student.status_code = 200
        mock_resp_student.json.return_value = {"message": {"content": "Resposta superficial."}}

        mock_resp_judge = MagicMock()
        mock_resp_judge.status_code = 200
        mock_resp_judge.json.return_value = {
            "message": {
                "content": (
                    '{"score": 5.0, "critique": "Faltou citar async/await.", '
                    '"gap_identified": "FastAPI async traps"}'
                )
            }
        }
        mock_post.side_effect = [mock_resp_student, mock_resp_judge]

        engine = DiagnosticEngine(store=self.store)
        res = engine.run_self_eval()
        self.assertTrue(res["success"])
        self.assertEqual(res["score"], 5.0)
        self.assertTrue(res["gap_scheduled"])

        tm = TopicManager(store=self.store)
        active = tm.list_topics(uncompleted_only=True)
        self.assertTrue(any("FastAPI async traps" in t["text"] for t in active))

    def test_tool_schedule_study_topic(self):
        res = schedule_study_topic(
            topic="Arquitetura de Transformers MoE",
            category="ia",
            priority="high",
            user_note="Focar em Mixtral 8x7B",
            store=self.store,
        )
        self.assertTrue(res["success"])

        tm = TopicManager(store=self.store)
        topics = tm.list_topics(uncompleted_only=True)
        found = [t for t in topics if "Arquitetura de Transformers MoE" in t["text"]]
        self.assertTrue(len(found) > 0)
        self.assertEqual(found[0]["priority"], "high")

    def test_tool_dispatcher_has_schedule_study_topic(self):
        self.assertIn("schedule_study_topic", TOOL_DISPATCHER)
        dispatch_fn = TOOL_DISPATCHER["schedule_study_topic"]
        res = dispatch_fn(topic="Test Dispatch", store=self.store)
        self.assertTrue(res.get("success"))

    @patch("src.tools.web._search_hn")
    @patch("src.tools.web._search_github")
    def test_multi_search_basic(self, mock_gh, mock_hn):
        mock_hn.return_value = [{"url": "https://news.ycombinator.com/item?id=1", "title": "HN Topic"}]
        mock_gh.return_value = [{"url": "https://github.com/fastapi/fastapi", "title": "FastAPI Repo"}]
        res = multi_search("python unittest", category="software")
        self.assertIn("results", res)
        self.assertIn("sources", res)
        self.assertIsInstance(res["results"], list)
        self.assertGreaterEqual(len(res["results"]), 2)

    def test_tool_get_study_report(self):
        from src.tools.core import get_study_report
        # Inicialmente sem relatório
        r1 = get_study_report(store=self.store)
        self.assertTrue(r1["success"])
        self.assertFalse(r1["has_report"])

        # Cria relatório simulado
        rep_dir = self.store.brain_dir / "relatorios"
        rep_dir.mkdir(parents=True, exist_ok=True)
        (rep_dir / "ultimo_estudo.md").write_text("# Resumo de teste", encoding="utf-8")
        (rep_dir / "ultimo_estudo.json").write_text('{"timestamp": "2026-10-24T00:00:00Z"}', encoding="utf-8")

        r2 = get_study_report(store=self.store)
        self.assertTrue(r2["success"])
        self.assertTrue(r2["has_report"])
        self.assertIn("# Resumo de teste", r2["report_markdown"])

    @patch("src.agent.study.DiagnosticEngine.run_self_eval")
    @patch("src.agent.study.StudyWorker.study_cycle")
    @patch("src.agent.reflection.ReflectionWorker.reflect")
    def test_run_autonomous_cycle(self, mock_refl, mock_study, mock_diag):
        from src.agent.study import run_autonomous_cycle
        mock_refl.return_value = {"learnings_added": 2, "anti_patterns_added": 1}
        mock_study.return_value = {"topics": ["Web Audio API"], "studied": 1}
        mock_diag.return_value = {"score": 8.5, "gap_identified": ""}

        res = run_autonomous_cycle(store=self.store)
        self.assertIsNotNone(res)
        self.assertIn("report_markdown", res)
        self.assertIn("Web Audio API", res["report_markdown"])
        self.assertIn("8.5/10", res["report_markdown"])

        # Verifica se gravou arquivos em relatorios/
        rep_file = self.store.brain_dir / "relatorios" / "ultimo_estudo.md"
        self.assertTrue(rep_file.exists())

    def test_dynamic_study_anchors_from_core_memory(self):
        from src.memory.core_memory import CoreMemoryManager
        cm = CoreMemoryManager(store=self.store)
        cm.set_block("study_anchors", "Game Development em C++ e Unreal Engine 5\nShaders GLSL")

        tm = TopicManager(store=self.store)
        tm.file_path.write_text("# Temas\n\n", encoding="utf-8")
        generated = tm.auto_generate_topics(count=1)
        self.assertGreaterEqual(len(generated), 1)


if __name__ == "__main__":
    unittest.main()
