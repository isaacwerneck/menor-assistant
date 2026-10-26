"""Ferramentas reais do sistema operacional para o Menor v2.

Permite leitura/escrita de arquivos, execução de comandos no terminal e gestão
de planos de projeto de maneira real e verificável.
"""
from pathlib import Path
import json
import subprocess
from typing import Any, Dict, Optional

from src.memory.store import BrainStore

MAX_READ_BYTES = 256 * 1024  # 256 KB


def _resolve_safe_path(filepath: str, base_dir: Optional[str] = None) -> Path:
    """Resolve o caminho de arquivo com segurança."""
    if not filepath or not isinstance(filepath, str):
        raise ValueError("Caminho de arquivo inválido.")

    path = Path(filepath).expanduser()
    if not path.is_absolute():
        base = Path(base_dir).expanduser() if base_dir else Path.cwd()
        path = (base / path).resolve()
    else:
        path = path.resolve()

    return path


def fs_read(filepath: str, max_bytes: int = MAX_READ_BYTES) -> Dict[str, Any]:
    """Lê o conteúdo textual de um arquivo no disco."""
    try:
        path = _resolve_safe_path(filepath)
        if not path.exists():
            return {"success": False, "error": f"Arquivo não encontrado: {filepath}"}
        if not path.is_file():
            return {"success": False, "error": f"O caminho não é um arquivo: {filepath}"}

        size = path.stat().st_size
        if size > max_bytes:
            content = path.read_text(encoding="utf-8", errors="replace")[:max_bytes]
            return {
                "success": True,
                "filepath": str(path),
                "content": content,
                "truncated": True,
                "size_bytes": size,
            }

        content = path.read_text(encoding="utf-8", errors="replace")
        return {
            "success": True,
            "filepath": str(path),
            "content": content,
            "truncated": False,
            "size_bytes": size,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def fs_write(filepath: str, content: str) -> Dict[str, Any]:
    """Cria ou atualiza um arquivo no disco, criando diretórios pais se necessário."""
    try:
        if not isinstance(content, str):
            content = str(content)
        path = _resolve_safe_path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {
            "success": True,
            "filepath": str(path),
            "bytes_written": len(content.encode("utf-8")),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def fs_patch(filepath: str, search_block: str, replace_block: str) -> Dict[str, Any]:
    """Substitui cirurgicamente um bloco de código exato em um arquivo (Aider Pattern).

    Evita reescrever arquivos completos, preservando o restante do código sem truncamento.
    Retorna erro se o bloco não for encontrado ou se houver múltiplas ocorrências ambíguas.
    """
    try:
        if replace_block is None:
            replace_block = ""
        if not isinstance(replace_block, str):
            replace_block = str(replace_block)

        path = _resolve_safe_path(filepath)
        if not path.exists() or not search_block or not str(search_block).strip():
            # Criação de novo arquivo ou substituição total quando search_block é vazio
            return fs_write(filepath, replace_block)
        if not path.is_file():
            return {"success": False, "error": f"O caminho não é um arquivo: {filepath}"}

        content = path.read_text(encoding="utf-8", errors="replace")

        # 1. Correspondência exata
        occurrences = content.count(search_block)
        matched_search = search_block

        # 2. Se falhar, normaliza quebras de linha (\r\n vs \n)
        if occurrences == 0:
            norm_content = content.replace("\r\n", "\n")
            norm_search = search_block.replace("\r\n", "\n")
            if norm_content.count(norm_search) > 0:
                content = norm_content
                matched_search = norm_search
                replace_block = replace_block.replace("\r\n", "\n")
                occurrences = content.count(matched_search)

        if occurrences == 0:
            return {
                "success": False,
                "error": "Bloco de busca não encontrado no arquivo. Verifique indentação e linhas de contexto.",
            }

        if occurrences > 1:
            return {
                "success": False,
                "error": (
                    f"O bloco de busca foi encontrado {occurrences} vezes. "
                    "Forneça mais linhas de contexto antes e depois do trecho para garantir alteração única."
                ),
                "occurrences": occurrences,
            }

        new_content = content.replace(matched_search, replace_block, 1)
        path.write_text(new_content, encoding="utf-8")

        search_lines = len(matched_search.splitlines())
        replace_lines = len(replace_block.splitlines())
        return {
            "success": True,
            "filepath": str(path),
            "bytes_written": len(new_content.encode("utf-8")),
            "lines_removed": search_lines,
            "lines_added": replace_lines,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def fs_list(dirpath: str = ".") -> Dict[str, Any]:
    """Lista arquivos e subdiretórios em um caminho."""
    try:
        path = _resolve_safe_path(dirpath)
        if not path.exists():
            return {"success": False, "error": f"Diretório não encontrado: {dirpath}"}
        if not path.is_dir():
            return {"success": False, "error": f"O caminho não é um diretório: {dirpath}"}

        items = []
        for entry in sorted(path.iterdir()):
            items.append({
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size": entry.stat().st_size if entry.is_file() else None,
            })
        return {"success": True, "dirpath": str(path), "items": items}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def terminal_run(command: str, cwd: str = ".", timeout_seconds: int = 45) -> Dict[str, Any]:
    """Executa um comando real no terminal e retorna saída e código de status."""
    try:
        if not command or not isinstance(command, str):
            return {"success": False, "error": "Comando inválido."}

        work_dir = _resolve_safe_path(cwd)
        if not work_dir.exists() or not work_dir.is_dir():
            work_dir = Path.cwd()

        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-10000:] if proc.stdout else "",
            "stderr": proc.stderr[-10000:] if proc.stderr else "",
            "cwd": str(work_dir),
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Comando excedeu o timeout de {timeout_seconds}s"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def save_plan(project_slug: str, markdown_content: str, store: Optional[BrainStore] = None) -> Dict[str, Any]:
    """Salva ou atualiza o PLANO.md do projeto no cérebro persistente."""
    try:
        store = store or BrainStore()
        store.initialize()
        plan_rel_path = f"projetos/{project_slug}/PLANO.md"
        plan_full_path = store.brain_dir / plan_rel_path
        plan_full_path.parent.mkdir(parents=True, exist_ok=True)
        store.write_note(plan_rel_path, markdown_content)
        return {
            "success": True,
            "project": project_slug,
            "plan_path": str(plan_full_path),
            "bytes": len(markdown_content.encode("utf-8")),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def update_core_memory(
    block_key: str,
    content: str,
    mode: str = "replace",
    store: Optional[BrainStore] = None,
) -> Dict[str, Any]:
    """Atualiza ou anexa informações em um bloco da Core Memory (user_profile, active_projects, etc.)."""
    try:
        from src.memory.core_memory import CoreMemoryManager
        mgr = CoreMemoryManager(store=store)
        mgr.set_block(block_key, content, mode=mode)
        return {
            "success": True,
            "block_key": block_key,
            "mode": mode,
            "content": content,
            "message": f"Bloco '{block_key}' da Core Memory atualizado com sucesso.",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def get_study_report(store: Optional[BrainStore] = None) -> Dict[str, Any]:
    """Retorna o resumo da última sessão de estudo, reflexão e auto-diagnóstico realizada pelo Menor."""
    st = store or BrainStore()
    rep_file = st.brain_dir / "relatorios" / "ultimo_estudo.md"
    json_file = st.brain_dir / "relatorios" / "ultimo_estudo.json"
    if not rep_file.exists():
        try:
            from src.agent.study import TopicManager
            completed = [
                t["text"] for t in TopicManager(st).list_topics(uncompleted_only=False) if t.get("completed")
            ]
            if completed:
                summary_md = (
                    "# Acervo de Estudos do Menor\n\n"
                    "### Tópicos Concluídos Recentemente:\n"
                    + "\n".join(f"- [x] {t}" for t in reversed(completed[-10:]))
                )
                return {
                    "success": True,
                    "has_report": True,
                    "report_markdown": summary_md,
                    "timestamp": None,
                    "data": {"completed_topics": completed},
                }
        except Exception:
            pass

        return {
            "success": True,
            "has_report": False,
            "message": (
                "Ainda não há relatório de estudos registrado. O Menor executará o primeiro ciclo "
                "quando ficar 30 minutos inativo ou via 'menor ciclo'."
            ),
        }
    try:
        raw_md = rep_file.read_text(encoding="utf-8")
        data = json.loads(json_file.read_text(encoding="utf-8")) if json_file.exists() else {}
        return {
            "success": True,
            "has_report": True,
            "report_markdown": raw_md,
            "timestamp": data.get("timestamp"),
            "data": data,
        }
    except Exception as exc:
        return {"success": False, "error": f"Falha ao ler relatório: {str(exc)}"}


def schedule_study_topic(
    topic: str,
    category: str = "geral",
    priority: str = "normal",
    user_note: str = "",
    store: Optional[BrainStore] = None,
) -> Dict[str, Any]:
    """Agenda um tópico para estudo e pesquisa autônoma na próxima reflexão/inatividade."""
    try:
        from src.agent.study import TopicManager
        tm = TopicManager(store=store)
        res = tm.save_topic(topic=topic, category=category, priority=priority, user_note=user_note)
        return res
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def web_search(query: str) -> Dict[str, Any]:
    """Pesquisa na web por termos públicos e retorna os resultados mais relevantes com URLs e títulos."""
    try:
        from src.tools.web import search
        res = search(query)
        return {
            "success": True,
            "query": query,
            "results": res.get("results", []),
            "provider": res.get("provider", "web"),
        }
    except Exception as exc:
        return {"success": False, "error": f"Falha na busca web: {str(exc)}"}


def grounded_search(query: str, store: Optional[BrainStore] = None) -> Dict[str, Any]:
    """Pesquisa fatos e incidentes recentes na web com reformulação de query, passagens e citações."""
    try:
        from src.tools.search_router import GroundedSearchEngine
        engine = GroundedSearchEngine(store=store)
        res = engine.search_and_ground(query)
        return {
            "success": res.get("success", False),
            "query": res.get("primary_query", query),
            "citations": res.get("citations", []),
            "environment_risk": res.get("environment_risk", ""),
            "summary": res.get("grounded_context", ""),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def web_read(url: str, query: Optional[str] = None) -> Dict[str, Any]:
    """Lê o conteúdo em texto limpo de uma página web pública (URL)."""
    try:
        from src.tools.web import read
        res = read(url, query=query)
        return {
            "success": True,
            "url": res.get("url", url),
            "content": res.get("text", "")[:8000],
            "truncated": res.get("truncated", False),
        }
    except Exception as exc:
        return {"success": False, "error": f"Falha ao ler página web: {str(exc)}"}


def repo_map(root_dir: str = ".", max_depth: int = 4, max_files: int = 50) -> Dict[str, Any]:
    """Gera um mapa compacto de símbolos do projeto no estilo Aider/Tree-Sitter."""
    try:
        from src.tools.code_intel import repo_map as _rm
        return _rm(root_dir=root_dir, max_depth=max_depth, max_files=max_files)
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def symbol_lookup(
    symbol_name: str,
    file_hint: Optional[str] = None,
    root_dir: str = ".",
) -> Dict[str, Any]:
    """Busca cirúrgica por definições de símbolos (classes, funções, variáveis) via AST e LSP."""
    try:
        from src.tools.code_intel import symbol_lookup as _sl
        return _sl(symbol_name=symbol_name, file_hint=file_hint, root_dir=root_dir)
    except Exception as exc:
        return {"success": False, "error": str(exc)}


DYNAMIC_TOOLS_DIR = Path(__file__).parent / "dynamic"


def create_new_tool(
    name: str,
    code: str,
    test_command: str,
    description: str,
    parameters_schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Cria, valida, testa com terminal_run e registra dinamicamente uma nova ferramenta Python.

    Se os testes passarem com sucesso, a ferramenta torna-se disponível imediatamente
    no assistente para chamadas futuras.
    """
    try:
        import ast
        import importlib.util
        import re

        clean_name = re.sub(r"[^a-zA-Z0-9_]", "", name).strip().lower()
        if not clean_name:
            return {"success": False, "error": "Nome de ferramenta inválido."}

        try:
            ast.parse(code)
        except SyntaxError as syn_err:
            return {
                "success": False,
                "error": f"Erro de sintaxe Python na ferramenta: {syn_err}",
                "phase": "syntax_validation",
            }

        # Validação de simplicidade e anti-bloat Ponytail
        try:
            from src.agent.ponytail import lint_tool_creation
            lint_res = lint_tool_creation(clean_name, code, description)
            if not lint_res.get("passed"):
                return {
                    "success": False,
                    "error": f"Rejeitado pelo linter Ponytail: {lint_res.get('reason')}",
                    "phase": "ponytail_linter",
                    "warnings": lint_res.get("warnings", []),
                }
        except Exception:
            pass

        DYNAMIC_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        init_file = DYNAMIC_TOOLS_DIR / "__init__.py"
        if not init_file.exists():
            init_file.write_text("# Dynamic tools package\n", encoding="utf-8")

        target_file = DYNAMIC_TOOLS_DIR / f"{clean_name}.py"
        target_file.write_text(code, encoding="utf-8")

        test_res = terminal_run(test_command)
        if not test_res.get("success"):
            return {
                "success": False,
                "error": f"Testes falharam: {test_res.get('stderr') or test_res.get('stdout')}",
                "phase": "test_execution",
                "exit_code": test_res.get("exit_code"),
            }

        spec = importlib.util.spec_from_file_location(f"src.tools.dynamic.{clean_name}", str(target_file))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            tool_callable = getattr(mod, clean_name, None)
            if not callable(tool_callable):
                return {
                    "success": False,
                    "error": f"O módulo foi carregado, mas não possui a função chamada '{clean_name}'.",
                }

            TOOL_DISPATCHER[clean_name] = tool_callable
            schema = {
                "type": "function",
                "function": {
                    "name": clean_name,
                    "description": description or f"Ferramenta criada dinamicamente: {clean_name}",
                    "parameters": parameters_schema or {
                        "type": "object",
                        "properties": {},
                    },
                },
            }
            filtered_schemas = [s for s in CORE_TOOLS_SCHEMA if s.get("function", {}).get("name") != clean_name]
            filtered_schemas.append(schema)
            CORE_TOOLS_SCHEMA.clear()
            CORE_TOOLS_SCHEMA.extend(filtered_schemas)

            return {
                "success": True,
                "tool_name": clean_name,
                "filepath": str(target_file),
                "message": f"Ferramenta '{clean_name}' criada, testada e registrada com sucesso!",
            }
        return {"success": False, "error": "Não foi possível carregar o módulo gerado."}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def improve_knowledge(
    domain: str,
    topic: str,
    content: str,
    mode: str = "append",
    store: Optional[BrainStore] = None,
) -> Dict[str, Any]:
    """Aprimora ou expande o conhecimento em uma das 5 bases padrão.

    Domínios: design, programacao, engenharia_software, musica, game_design.
    """
    try:
        st = store or BrainStore()
        st.initialize()
        return st.improve_knowledge(domain=domain, topic=topic, content=content, mode=mode)
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def get_knowledge(
    domain: str,
    store: Optional[BrainStore] = None,
) -> Dict[str, Any]:
    """Recupera notas e preferências consolidadas de um dos 5 domínios padrão do Isaac."""
    try:
        st = store or BrainStore()
        st.initialize()
        notes = st.list_domain_knowledge(domain=domain)
        return {"success": True, "domain": domain, "notes": notes, "total_notes": len(notes)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# Schemas para o Tool Calling oficial do Ollama / OpenAI
CORE_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "fs_read",
            "description": "Lê o conteúdo de um arquivo de texto no disco.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Caminho do arquivo a ser lido."}
                },
                "required": ["filepath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fs_write",
            "description": "Cria ou substitui um arquivo no disco com o conteúdo especificado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Caminho do arquivo a salvar."},
                    "content": {"type": "string", "description": "Conteúdo textual completo do arquivo."},
                },
                "required": ["filepath", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fs_list",
            "description": "Lista arquivos e subpastas de um diretório.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dirpath": {"type": "string", "description": "Caminho do diretório (padrão '.')."}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "terminal_run",
            "description": "Executa comando no terminal (pytest, git, python, npm) e obtém stdout/stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Linha de comando a ser executada."},
                    "cwd": {"type": "string", "description": "Diretório de trabalho onde rodar o comando."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_plan",
            "description": "Salva ou atualiza a especificação e tarefas (PLANO.md) de um projeto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_slug": {"type": "string", "description": "Identificador do projeto (slug)."},
                    "markdown_content": {"type": "string", "description": "Conteúdo em Markdown do plano."},
                },
                "required": ["project_slug", "markdown_content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Pesquisa termos na web e retorna uma lista de links e títulos relevantes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Termo de busca público."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_read",
            "description": "Lê o conteúdo em texto limpo de uma página web pública através de uma URL HTTPS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL HTTPS pública da página web."},
                    "query": {"type": "string", "description": "Trecho opcional de foco na leitura."}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_new_tool",
            "description": "Cria, testa e registra dinamicamente uma nova ferramenta Python quando necessário.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nome da função/ferramenta (ex: 'convert_units')."},
                    "code": {"type": "string", "description": "Código Python completo implementando a função."},
                    "test_command": {"type": "string", "description": "Comando de terminal para testar a ferramenta."},
                    "description": {"type": "string", "description": "Descrição detalhada para a IA."},
                    "parameters_schema": {"type": "object", "description": "Schema JSON dos parâmetros aceitos."},
                },
                "required": ["name", "code", "test_command", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_core_memory",
            "description": "Atualiza ou anexa dados na Core Memory residente (blocos: user_profile, active_projects).",
            "parameters": {
                "type": "object",
                "properties": {
                    "block_key": {
                        "type": "string",
                        "description": "Chave do bloco (ex: 'user_profile', 'active_projects').",
                    },
                    "content": {
                        "type": "string",
                        "description": "Conteúdo a ser salvo no bloco de memória de trabalho.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["replace", "append"],
                        "description": "'replace' para sobrescrever ou 'append' para adicionar mantendo o anterior.",
                    },
                },
                "required": ["block_key", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grounded_search",
            "description": (
                "Pesquisa na web por notícias, vulnerabilidades, CVEs e documentações recentes com citações."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Assunto, nome de biblioteca, tecnologia ou incidente a pesquisar.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_study_topic",
            "description": (
                "Agenda um tópico técnico para estudo ativo e pesquisa web pelo Menor "
                "durante inatividade ou reflexão noturna."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": (
                            "O assunto ou tecnologia para estudar "
                            "(ex: 'Web Audio API', 'Server-Sent Events no FastAPI')."
                        ),
                    },
                    "category": {
                        "type": "string",
                        "enum": ["ia", "software", "javascript", "design", "geral"],
                        "description": "Categoria do tema de estudo.",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["high", "normal"],
                        "description": "'high' para estudar com prioridade máxima ou 'normal'.",
                    },
                    "user_note": {
                        "type": "string",
                        "description": "Observações ou instruções específicas fornecidas pelo usuário.",
                    },
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_study_report",
            "description": (
                "Obtém o relatório consolidado da última sessão de estudo, reflexão e auto-diagnóstico "
                "realizada em segundo plano pelo Menor."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fs_patch",
            "description": (
                "Substitui cirurgicamente um bloco de código exato em um arquivo. "
                "Evita reescrever arquivos inteiros e previne truncamentos de código."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Caminho do arquivo a alterar."},
                    "search_block": {
                        "type": "string",
                        "description": (
                            "Trecho de código original exato que será substituído (com linhas de contexto)."
                        ),
                    },
                    "replace_block": {
                        "type": "string",
                        "description": "Novo trecho de código que substituirá o bloco original.",
                    },
                },
                "required": ["filepath", "search_block", "replace_block"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_map",
            "description": (
                "Gera um mapa compacto da árvore e símbolos do projeto (classes, métodos e funções). "
                "Use para conhecer a estrutura do código gastando poucos tokens."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "root_dir": {"type": "string", "description": "Diretório raiz para mapear (padrão '.')."},
                    "max_depth": {"type": "integer", "description": "Profundidade máxima de pastas (padrão 4)."},
                    "max_files": {"type": "integer", "description": "Quantidade máxima de arquivos (padrão 50)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "symbol_lookup",
            "description": (
                "Busca cirúrgica por definições de símbolos (classes, funções, variáveis) via AST/LSP. "
                "Retorna assinatura, arquivo e linhas exatas sem ler o arquivo inteiro."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol_name": {
                        "type": "string",
                        "description": "Nome da classe, função ou variável a localizar.",
                    },
                    "file_hint": {
                        "type": "string",
                        "description": "Caminho opcional do arquivo para acelerar a busca.",
                    },
                    "root_dir": {"type": "string", "description": "Diretório de busca (padrão '.')."},
                },
                "required": ["symbol_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "improve_knowledge",
            "description": (
                "Aprimora ou expande o conhecimento em uma das 5 bases padrão do Isaac: "
                "design, programacao, engenharia_software, musica, game_design."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "enum": ["design", "programacao", "engenharia_software", "musica", "game_design"],
                        "description": "Domínio da base de conhecimento a ser atualizada.",
                    },
                    "topic": {"type": "string", "description": "Título ou nome do tema específico."},
                    "content": {"type": "string", "description": "Conteúdo, regras ou diretrizes a registrar."},
                    "mode": {
                        "type": "string",
                        "enum": ["append", "overwrite"],
                        "description": "Modo de gravação ('append' para adicionar ou 'overwrite' para recriar).",
                    },
                },
                "required": ["domain", "topic", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_knowledge",
            "description": (
                "Recupera todas as notas e preferências salvas de um domínio padrão "
                "(design, programacao, musica, etc)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "enum": ["design", "programacao", "engenharia_software", "musica", "game_design"],
                        "description": "Domínio a consultar.",
                    },
                },
                "required": ["domain"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "curate_visual_references",
            "description": (
                "Curador visual autônomo: busca referências no Pinterest/Web/galerias, "
                "avalia com modelo multimodal (Qwen 2.5-VL/Llava), ranqueia o TOP 20 "
                "e salva regras estéticas em conhecimentos/design/."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Termo de busca visual (ex: dark UI glassmorphism)."},
                    "domain": {
                        "type": "string",
                        "enum": ["design", "game_design"],
                        "description": "Domínio onde salvar o aprendizado visual (padrão 'design').",
                    },
                    "max_selection": {
                        "type": "integer",
                        "description": "Quantidade máxima de imagens no TOP selecionado (padrão 20).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_codebase",
            "description": (
                "Audita o repositório do Menor via AST: mede arquivos, funções, classes, "
                "cruza com os testes existentes e mapeia gaps para criação de novos testes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "root_dir": {"type": "string", "description": "Diretório raiz a inspecionar (padrão '.')."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trial_code_refactoring",
            "description": (
                "Testa uma refatoração em branch temporária isolada com suíte completa de testes. "
                "Se algum teste quebrar, faz rollback atômico instantâneo. Se passar 100%, gera proposta com diff."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_file": {"type": "string", "description": "Caminho do arquivo de código a refatorar."},
                    "description": {"type": "string", "description": "Descrição clara da refatoração."},
                    "search_block": {"type": "string", "description": "Bloco exato de código a ser substituído."},
                    "replace_block": {"type": "string", "description": "Novo bloco de código otimizado."},
                },
                "required": ["target_file", "description", "search_block", "replace_block"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dispatch_specialized_subagent",
            "description": (
                "Roteia tarefas de alta especialidade para subagentes de nicho "
                "(design, programacao, engenharia_software, musica, game_design) "
                "com injeção cirúrgica de conhecimento das pastas do Isaac."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "enum": ["design", "programacao", "engenharia_software", "musica", "game_design"],
                        "description": "Domínio do subagente especializado.",
                    },
                    "prompt": {"type": "string", "description": "Instrução ou briefing para o subagente resolver."},
                },
                "required": ["domain", "prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_agent_work_status",
            "description": (
                "Consulta o status de sessões, compilações e execuções de agentes de código externos "
                "(Antigravity, Codex, etc.) no banco isolado de trabalhos sem poluir a memória pessoal."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "ID opcional de uma sessão específica a auditar.",
                    },
                },
            },
        },
    },
]


def dispatch_curate_visual_references(**kw):
    from src.agent.visual_curator import curate_visual_references as _c
    return _c(**kw)


def dispatch_inspect_codebase(**kw):
    from src.agent.inspector import inspect_codebase as _i
    return _i(**kw)


def dispatch_trial_code_refactoring(**kw):
    from src.agent.sandbox_refactor import trial_code_refactoring as _t
    return _t(**kw)


def dispatch_subagent_tool(**kw):
    from src.agent.subagents import dispatch_specialized_subagent as _d
    return _d(**kw)


def dispatch_agent_work_status(**kw):
    from src.agent.external_work_store import get_agent_work_status as _g
    return _g(**kw)


TOOL_DISPATCHER = {
    "fs_read": fs_read,
    "fs_write": fs_write,
    "fs_patch": fs_patch,
    "fs_list": fs_list,
    "terminal_run": terminal_run,
    "save_plan": save_plan,
    "web_search": web_search,
    "web_read": web_read,
    "create_new_tool": create_new_tool,
    "update_core_memory": update_core_memory,
    "grounded_search": grounded_search,
    "schedule_study_topic": schedule_study_topic,
    "get_study_report": get_study_report,
    "repo_map": repo_map,
    "symbol_lookup": symbol_lookup,
    "improve_knowledge": improve_knowledge,
    "get_knowledge": get_knowledge,
    "curate_visual_references": dispatch_curate_visual_references,
    "inspect_codebase": dispatch_inspect_codebase,
    "trial_code_refactoring": dispatch_trial_code_refactoring,
    "dispatch_specialized_subagent": dispatch_subagent_tool,
    "get_agent_work_status": dispatch_agent_work_status,
}
