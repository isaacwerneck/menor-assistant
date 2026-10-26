import shutil
import tempfile
import unittest
from pathlib import Path

from src.agent.morning_digest import MorningDigestEngine
from src.memory.store import BrainStore


class TestMorningDigestV2(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.store = BrainStore(data_dir=self.temp_dir)
        self.store.initialize()
        self.engine = MorningDigestEngine(store=self.store)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_generate_digest_structure(self):
        digest = self.engine.generate_digest(synthesize_audio=False)

        self.assertIn("briefing_text", digest)
        self.assertIn("Bom dia, Isaac!", digest["briefing_text"])
        self.assertIn("Hub Central", digest["briefing_text"])
        self.assertIn("date", digest)
        self.assertIn("weekday", digest)
        self.assertTrue(self.engine.cache_file.exists())

    def test_generate_digest_with_audio_buffer(self):
        digest = self.engine.generate_digest(synthesize_audio=True)
        self.assertTrue(digest["audio_synthesized"])
        self.assertTrue(digest.get("audio_bytes_length", 0) > 0)


if __name__ == "__main__":
    unittest.main()
