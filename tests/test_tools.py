import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent.diagnostics import analyze
from src.memory.store import BrainStore
from src.tools.audit import record
from src.tools.registry import list_tools, perform
from test_auth_memory import call


class ToolRegistryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"MENOR_DATA_DIR": temp.name})
        env.start()
        self.addCleanup(env.stop)

    def test_catalog_contains_explicit_risks_and_arguments(self):
        listing = {x["name"]: x for x in list_tools()}
        self.assertFalse(listing["projects.list"]["writes"])
        self.assertTrue(listing["brain.remember"]["writes"])
        self.assertEqual(listing["projects.add_task"]["arguments"], ["slug", "text"])

    def test_dry_run_never_creates_any_project(self):
        before = BrainStore().data_dir / "cerebro" / "projetos" / "cidade-noturna"
        result = perform("projects.create", {"name": "Cidade Noturna"}, dry_run=True)
        self.assertEqual(result["status"], "planned")
        self.assertFalse(before.exists())
        self.assertNotIn("Cidade Noturna", result.values())

    def test_write_tool_creates_real_project_and_task_in_authorized_root(self):
        result = perform("projects.create", {"name": "Cidade Noturna"}, dry_run=False)
        self.assertEqual(result["status"], "executed")
        note = perform("projects.add_task", {
            "slug": "cidade-noturna", "text": "Criar menu",
        }, dry_run=False)
        self.assertIn("projetos/cidade-noturna/tarefas.md", note["result"]["path"])
        self.assertIn("Criar menu", BrainStore().read_note(note["result"]["path"]))

    def test_invalid_tool_or_arguments_does_not_write(self):
        cases = [
            ("shell.exec", {"cmd": "rm -rf /"}),
            ("projects.create", {"name": "../fora"}),
            ("brain.remember", {"kind": "secret", "text": "senha"}),
            ("projects.add_task", {"slug": "../fora", "text": "oi"}),
        ]
        for name, args in cases:
            with self.subTest(name=name), self.assertRaises((ValueError, LookupError)):
                perform(name, args, dry_run=False)

    def test_audit_only_writes_names_not_memory_text(self):
        entry = record("brain.remember", "executed", ["kind", "text"])
        self.assertEqual(entry["status"], "executed")
        audit = BrainStore().brain_dir / "memoria" / "execucoes.jsonl"
        self.assertEqual(audit.stat().st_mode & 0o777, 0o600)
        payload = json.loads(audit.read_text().strip())
        self.assertEqual(payload["fields"], ["kind", "text"])
        self.assertNotIn("senha-de-acesso", audit.read_text())

    def test_diagnose_groups_failures_without_contents(self):
        record("projects.create", "failed", ["name"])
        record("projects.create", "failed", ["name"])
        record("projects.list", "executed")
        status = analyze()
        self.assertEqual(status["status"], "needs-review")
        self.assertEqual(status["failures"], 2)
        self.assertEqual(status["issues"][0]["tool"], "projects.create")
        self.assertEqual(status["issues"][0]["failures"], 2)
        result = perform("system.diagnose", {}, dry_run=False)
        self.assertEqual(result["result"]["events"], 3)
        self.assertNotIn("arguments", result["result"])

    def test_audit_rejects_symlink(self):
        store = BrainStore()
        store.initialize()
        target = Path(os.environ["MENOR_DATA_DIR"]) / "target.txt"
        target.write_text("private")
        (store.brain_dir / "memoria" / "execucoes.jsonl").symlink_to(target)
        with self.assertRaises(ValueError):
            record("projects.list", "executed")
        self.assertEqual(target.read_text(), "private")


class ToolEndpointTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"MENOR_DATA_DIR": temp.name})
        env.start()
        self.addCleanup(env.stop)
        from src.security import auth
        auth._attempts.clear()
        status, _, headers = call("/auth/setup", {"password": "teste-senha-longa-segura"})
        self.assertEqual(status, 200)
        self.cookie = headers[b"set-cookie"].decode().split(";", 1)[0]

    def test_requires_login_and_default_is_dry_run(self):
        self.assertEqual(call("/tools")[0], 401)
        self.assertEqual(call("/tools/execute", {"tool": "projects.list"})[0], 401)
        status, result, _ = call("/tools/execute", {
            "tool": "projects.create", "arguments": {"name": "Cidade Noturna"},
        }, cookie=self.cookie)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["status"], "planned")
        self.assertEqual(BrainStore().read_note("projetos/cidade-noturna/contexto.md"), "")

    def test_execute_authenticated_operation_and_audit(self):
        status, response, _ = call("/tools/execute", {
            "tool": "projects.create", "arguments": {"name": "Cidade Noturna"}, "dry_run": False,
        }, cookie=self.cookie)
        self.assertEqual(status, 200, response)
        self.assertEqual(response["status"], "executed")
        status, items, _ = call("/tools", cookie=self.cookie)
        self.assertEqual(status, 200)
        self.assertTrue(any(x["name"] == "projects.create" for x in items["items"]))

    def test_origin_protection(self):
        code, _, _ = call("/tools/execute", {
            "tool": "projects.create", "arguments": {"name": "Cidade Noturna"}, "dry_run": False,
        }, cookie=self.cookie, origin="http://evil.invalid")
        self.assertEqual(code, 403)


if __name__ == "__main__":
    unittest.main()
