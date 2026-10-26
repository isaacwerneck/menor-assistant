import shutil
import tempfile
import unittest
from pathlib import Path

from src.observability.prompt_traces import PromptTraceLogger
from src.memory.store import BrainStore


class TestPromptTracesV2(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.store = BrainStore(data_dir=self.temp_dir)
        self.store.initialize()
        self.tracer = PromptTraceLogger(store=self.store)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_record_and_list_traces(self):
        trace_id = self.tracer.record_trace(
            session_id="sess_123",
            turn_index=1,
            model="qwen2.5:14b",
            provider="ollama",
            input_tokens=150,
            output_tokens=45,
            duration_ms=620,
            context_layers={"protected": 80, "consultative": 70},
            raw_prompt="Olá Menor, como você está?",
            raw_response="Estou ótimo e pronto para programar!",
            tool_calls=[],
        )

        self.assertTrue(trace_id.startswith("trace_"))
        traces = self.tracer.list_traces(limit=10)
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0]["id"], trace_id)
        self.assertEqual(traces[0]["session_id"], "sess_123")
        self.assertEqual(traces[0]["model"], "qwen2.5:14b")
        self.assertEqual(traces[0]["context_layers"]["protected"], 80)

    def test_get_trace_by_id(self):
        trace_id = self.tracer.record_trace(
            session_id="sess_456",
            turn_index=2,
            model="qwen2.5:14b",
            provider="ollama",
            input_tokens=200,
            output_tokens=60,
            duration_ms=850,
            context_layers={"is_casual": True},
            raw_prompt="Crie um arquivo teste.txt",
            raw_response="Arquivo criado com sucesso.",
            tool_calls=[{"name": "fs_write", "arguments": {"filepath": "teste.txt"}}],
        )

        trace = self.tracer.get_trace(trace_id)
        self.assertIsNotNone(trace)
        self.assertEqual(trace["session_id"], "sess_456")
        self.assertEqual(len(trace["tool_calls"]), 1)
        self.assertEqual(trace["tool_calls"][0]["name"], "fs_write")


if __name__ == "__main__":
    unittest.main()
