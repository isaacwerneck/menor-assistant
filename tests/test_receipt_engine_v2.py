import shutil
import tempfile
import unittest
from pathlib import Path

from src.tools.receipt_engine import ReceiptEngine, ReceiptV1
from src.memory.store import BrainStore


class TestReceiptEngineV2(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.store = BrainStore(data_dir=self.temp_dir)
        self.store.initialize()
        self.engine = ReceiptEngine(store=self.store)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_classify_reversible_vs_sensitive_action(self):
        is_sens, _ = self.engine.classify_action("fs_read", {"filepath": "index.html"})
        self.assertFalse(is_sens)

        is_sens_cmd, reason = self.engine.classify_action("terminal_run", {"command": "rm -rf /tmp/test"})
        self.assertTrue(is_sens_cmd)
        self.assertIn("destrutivo", reason.lower())

        is_sens_file, _ = self.engine.classify_action("fs_write", {"filepath": "/etc/shadow", "content": "..."})
        self.assertTrue(is_sens_file)

    def test_create_and_mark_executed(self):
        receipt = self.engine.create_receipt(
            session_id="sess_abc",
            tool_name="fs_read",
            args={"filepath": "main.py"},
        )
        self.assertTrue(receipt.receipt_id.startswith("rcpt_"))
        self.assertEqual(receipt.status, "planned")
        self.assertFalse(receipt.is_sensitive)

        self.engine.mark_executed(receipt.receipt_id, {"success": True, "bytes": 120})

    def test_uncertain_state_blocks_blind_replay(self):
        receipt = self.engine.create_receipt(
            session_id="sess_xyz",
            tool_name="terminal_run",
            args={"command": "npm install"},
        )
        self.engine.mark_uncertain(receipt.receipt_id, "Timeout após 60s")

        # Verifica bloqueio de replay cego
        is_blocked = self.engine.is_uncertain_or_duplicate(
            session_id="sess_xyz",
            tool_name="terminal_run",
            args={"command": "npm install"},
        )
        self.assertTrue(is_blocked)


if __name__ == "__main__":
    unittest.main()
