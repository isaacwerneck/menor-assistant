from pathlib import Path
import tempfile
import unittest

from src.tools.core import (
    fs_read,
    fs_write,
    fs_list,
    terminal_run,
    save_plan,
    web_search,
    web_read,
    create_new_tool,
    TOOL_DISPATCHER,
)
from src.memory.store import BrainStore


class TestCoreTools(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_fs_write_and_read(self):
        target = self.base / "sub" / "test.txt"
        content = "Olá, Menor v2!"
        res_write = fs_write(str(target), content)
        self.assertTrue(res_write["success"])

        res_read = fs_read(str(target))
        self.assertTrue(res_read["success"])
        self.assertEqual(res_read["content"], content)

    def test_fs_list(self):
        (self.base / "file1.txt").write_text("1")
        (self.base / "file2.txt").write_text("2")
        (self.base / "folder").mkdir()

        res = fs_list(str(self.base))
        self.assertTrue(res["success"])
        names = [item["name"] for item in res["items"]]
        self.assertIn("file1.txt", names)
        self.assertIn("file2.txt", names)
        self.assertIn("folder", names)

    def test_terminal_run_echo(self):
        res = terminal_run("echo hello", cwd=str(self.base))
        self.assertTrue(res["success"])
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("hello", res["stdout"])

    def test_save_plan(self):
        store = BrainStore(data_dir=str(self.base))
        res = save_plan("meu-projeto", "# Plano\n- [ ] Tarefa 1", store=store)
        self.assertTrue(res["success"])
        self.assertTrue(Path(res["plan_path"]).exists())
        self.assertIn("Tarefa 1", Path(res["plan_path"]).read_text(encoding="utf-8"))

    def test_create_new_tool(self):
        tool_code = """
def add_magic(a: int, b: int) -> int:
    return a + b + 42
"""
        test_cmd = 'python -c "assert True"'
        res = create_new_tool(
            name="add_magic",
            code=tool_code,
            test_command=test_cmd,
            description="Adiciona números com um fator mágico",
        )
        self.assertTrue(res["success"], res.get("error"))
        self.assertIn("add_magic", TOOL_DISPATCHER)
        result = TOOL_DISPATCHER["add_magic"](a=1, b=2)
        self.assertEqual(result, 45)
        # Cleanup
        if res.get("filepath") and Path(res["filepath"]).exists():
            Path(res["filepath"]).unlink(missing_ok=True)

    def test_web_search_and_read_schema(self):
        self.assertIn("web_search", TOOL_DISPATCHER)
        self.assertIn("web_read", TOOL_DISPATCHER)
        self.assertIn("create_new_tool", TOOL_DISPATCHER)
        self.assertTrue(callable(web_search))
        self.assertTrue(callable(web_read))


if __name__ == "__main__":
    unittest.main()
