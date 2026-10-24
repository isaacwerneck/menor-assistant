import tempfile
import unittest

from src.memory.core_memory import CoreMemoryManager
from src.memory.store import BrainStore
from src.tools.core import update_core_memory, TOOL_DISPATCHER


class TestCoreMemory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = BrainStore(data_dir=self.temp_dir.name)
        self.mgr = CoreMemoryManager(self.store)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_initialization(self):
        blocks = self.mgr.list_blocks()
        self.assertIn("user_profile", blocks)
        self.assertIn("system_directives", blocks)
        self.assertIn("active_projects", blocks)
        self.assertIn("Isaac Werneck", blocks["user_profile"])

    def test_get_and_set_block_replace(self):
        self.mgr.set_block("user_profile", "Nome: Isaac Developer", mode="replace")
        content = self.mgr.get_block("user_profile")
        self.assertEqual(content, "Nome: Isaac Developer")

    def test_set_block_append(self):
        orig = self.mgr.get_block("active_projects")
        self.mgr.set_block("active_projects", "Nova meta: teste unitário", mode="append")
        updated = self.mgr.get_block("active_projects")
        self.assertIn(orig, updated)
        self.assertIn("Nova meta: teste unitário", updated)

    def test_format_system_context(self):
        ctx = self.mgr.format_system_context()
        self.assertIn("CORE MEMORY", ctx)
        self.assertIn("[USER_PROFILE]", ctx)
        self.assertIn("[SYSTEM_DIRECTIVES]", ctx)
        self.assertIn("[ACTIVE_PROJECTS]", ctx)

    def test_tool_update_core_memory(self):
        self.assertIn("update_core_memory", TOOL_DISPATCHER)
        res = update_core_memory(
            "user_profile",
            "Preferência: sempre usar pytest",
            mode="append",
            store=self.store,
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["block_key"], "user_profile")
        saved = self.mgr.get_block("user_profile")
        self.assertIn("sempre usar pytest", saved)
