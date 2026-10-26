"""Client MCP Universal para Ferramentas Externas (Pilar 10 - Padrão Anthropic Claude Code & MCP).

Permite conectar servidores locais MCP (Model Context Protocol) via stdio (JSON-RPC 2.0)
e registrar suas ferramentas nativamente no catálogo do Menor v2.
"""
import json
import logging
import subprocess
import threading
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger(__name__)


class UniversalMCPClient:
    """Cliente universal do Model Context Protocol via stdio JSON-RPC 2.0."""

    def __init__(self, command: str, args: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None):
        self.command = command
        self.args = args or []
        self.env = env
        self.process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._lock = threading.Lock()
        self.server_capabilities: Dict[str, Any] = {}
        self.discovered_tools: List[Dict[str, Any]] = []

    def start(self) -> bool:
        """Inicia o subprocesso do servidor MCP e negocia o handshake inicial."""
        try:
            full_cmd = [self.command] + self.args
            self.process = subprocess.Popen(
                full_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=self.env,
            )

            # Handshake de inicialização JSON-RPC (MCP initialize)
            init_payload = {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": "Menor-MCP-Client", "version": "2.0.0"},
                    "capabilities": {"tools": {}},
                },
            }
            resp = self._send_request(init_payload)
            if resp and "result" in resp:
                self.server_capabilities = resp["result"].get("capabilities", {})
                self.discover_tools()
                LOGGER.info("Servidor MCP conectado com sucesso: %s (%d ferramentas)", self.command, len(self.discovered_tools))
                return True
        except Exception as exc:
            LOGGER.warning("Falha ao iniciar servidor MCP (%s): %s", self.command, exc)

        return False

    def discover_tools(self) -> List[Dict[str, Any]]:
        """Descobre ferramentas expostas pelo servidor MCP."""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
            "params": {},
        }
        resp = self._send_request(payload)
        tools = []
        if resp and "result" in resp:
            raw_tools = resp["result"].get("tools", [])
            for t in raw_tools:
                tools.append({
                    "name": t.get("name"),
                    "description": t.get("description", ""),
                    "inputSchema": t.get("inputSchema", {}),
                })
        self.discovered_tools = tools
        return tools

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Executa uma ferramenta no servidor MCP remoto."""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments,
            },
        }
        resp = self._send_request(payload)
        if not resp:
            return {"success": False, "error": "Servidor MCP não respondeu à solicitação."}

        if "error" in resp:
            return {"success": False, "error": resp["error"].get("message", "Erro MCP desconhecido")}

        result_content = resp.get("result", {}).get("content", [])
        text_parts = [c.get("text", "") for c in result_content if isinstance(c, dict) and c.get("type") == "text"]
        return {
            "success": True,
            "output": "\n".join(text_parts) if text_parts else str(resp.get("result")),
        }

    def _next_id(self) -> int:
        with self._lock:
            self._request_id += 1
            return self._request_id

    def _send_request(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Envia mensagem JSON-RPC e aguarda resposta síncrona."""
        if not self.process or self.process.poll() is not None:
            return None

        line = json.dumps(payload) + "\n"
        with self._lock:
            try:
                assert self.process.stdin is not None
                assert self.process.stdout is not None
                self.process.stdin.write(line)
                self.process.stdin.flush()

                response_line = self.process.stdout.readline()
                if response_line:
                    return json.loads(response_line.strip())
            except Exception as exc:
                LOGGER.debug("Erro de comunicação MCP JSON-RPC: %s", exc)

        return None

    def close(self):
        """Finaliza o subprocesso com segurança."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
