"""Testes para o Client MCP Universal (Pilar 10 - Model Context Protocol stdio)."""
import json
import unittest
from unittest.mock import MagicMock, patch

from src.tools.mcp_client import UniversalMCPClient


class TestMCPClientV2(unittest.TestCase):

    def setUp(self):
        self.client = UniversalMCPClient(command="dummy-mcp-server", args=["--port", "0"])

    def tearDown(self):
        self.client.close()

    def test_init_and_request_id_increment(self):
        self.assertEqual(self.client._request_id, 0)
        req_id1 = self.client._next_id()
        req_id2 = self.client._next_id()
        self.assertEqual(req_id1, 1)
        self.assertEqual(req_id2, 2)

    @patch("subprocess.Popen")
    def test_start_and_discover_tools(self, mock_popen):
        # Mock de processo stdio com respostas JSON-RPC
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        # Simula resposta do initialize e tools/list
        mock_proc.stdout.readline.side_effect = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {"tools": {}}}}) + "\n",
            json.dumps({
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "tools": [
                        {
                            "name": "sqlite_query",
                            "description": "Executa query SQLite",
                            "inputSchema": {"type": "object"},
                        }
                    ]
                },
            }) + "\n",
        ]

        started = self.client.start()
        self.assertTrue(started)
        self.assertEqual(len(self.client.discovered_tools), 1)
        self.assertEqual(self.client.discovered_tools[0]["name"], "sqlite_query")

    @patch("subprocess.Popen")
    def test_call_tool(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        self.client.process = mock_proc

        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [
                    {"type": "text", "text": "Query executada: 42 registros encontrados."}
                ]
            },
        }) + "\n"

        result = self.client.call_tool("sqlite_query", {"query": "SELECT count(*) FROM users"})
        self.assertTrue(result["success"])
        self.assertIn("42 registros encontrados", result["output"])
