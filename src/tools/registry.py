"""Catálogo de ferramentas permitidas e validadas no backend (Menor v2).

Integra as ferramentas reais do SO de src/tools/core.py com suporte a contratos
e listagem para o painel web e API.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.tools.core import CORE_TOOLS_SCHEMA, TOOL_DISPATCHER


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    risk: str
    writes: bool
    arguments: Tuple[str, ...]


TOOLS: Dict[str, Tool] = {}

# Mapeia ferramentas com efeitos de escrita no sistema
WRITE_TOOLS = {
    "fs_write", "fs_patch", "terminal_run", "save_plan",
    "create_new_tool", "update_core_memory", "improve_knowledge",
    "schedule_study_topic", "trial_code_refactoring",
}

# Popula TOOLS dinamicamente a partir do CORE_TOOLS_SCHEMA do Menor v2
for item in CORE_TOOLS_SCHEMA:
    fn = item.get("function", {})
    t_name = fn.get("name", "")
    t_desc = fn.get("description", "")
    params = fn.get("parameters", {}).get("properties", {})
    arg_names = tuple(params.keys())
    is_write = t_name in WRITE_TOOLS
    risk_level = "modifica_estado" if is_write else "leitura_segura"
    TOOLS[t_name] = Tool(
        name=t_name,
        description=t_desc,
        risk=risk_level,
        writes=is_write,
        arguments=arg_names,
    )


def list_tools(agent_scope: Optional[str] = None) -> List[Dict[str, Any]]:
    """Catálogo de ferramentas disponíveis para inspeção e execução."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "risk": t.risk,
            "writes": t.writes,
            "arguments": list(t.arguments),
        }
        for t in TOOLS.values()
    ]


def perform(name: str, arguments: Dict[str, Any], dry_run: bool = True) -> Dict[str, Any]:
    """Executa a ferramenta solicitada através do TOOL_DISPATCHER do Menor v2."""
    tool = TOOLS.get(name)
    if tool is None:
        raise ValueError(f"Ferramenta desconhecida: '{name}'.")
    if not isinstance(arguments, dict):
        raise ValueError("Argumentos devem ser fornecidos como um dicionário.")

    if dry_run and tool.writes:
        return {
            "status": "planned",
            "tool": name,
            "writes": tool.writes,
            "arguments": list(tool.arguments),
        }

    fn = TOOL_DISPATCHER.get(name)
    if fn is None:
        raise ValueError(f"Executor não registrado para a ferramenta '{name}'.")

    try:
        result = fn(**arguments)
        return {
            "status": "executed",
            "tool": name,
            "result": result,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "tool": name,
            "error": str(exc),
        }
