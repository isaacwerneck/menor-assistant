"""Motor de Avaliação Dual-Tier e Sessão de Testes do Laboratório.

Combina verificações determinísticas de regras (Tier 1: AST, arquivos em disco, links de preview)
com avaliação qualitativa (Tier 2: LLM-as-a-judge e rubricas) e suporte a Human-in-the-Loop.
"""
import ast
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.memory.store import BrainStore
from src.security.path_sentinel import PathSentinel

logger = logging.getLogger(__name__)

# Categorias oficiais do Laboratório Menor AI
LAB_CATEGORIES = {
    "web_preview": {
        "name": "🌐 Geração Web & Previews",
        "description": "Criação de páginas HTML/CSS/JS com links de visualização /preview/",
    },
    "tools_files": {
        "name": "🛠️ Uso de Ferramentas Reais & Arquivos",
        "description": "Criação e edição real no workspace via fs_write/fs_read sem simulação",
    },
    "architecture_mobile": {
        "name": "📱 Arquitetura de Software & Mobile",
        "description": "Modelagem de apps, Android Studio (Kotlin/Compose), Clean Architecture",
    },
    "database_design": {
        "name": "🗄️ Modelagem de Banco de Dados",
        "description": "Schemas relacionais, migrations, queries SQLite/PostgreSQL e consistência",
    },
    "multimedia_creative": {
        "name": "🎨 Multimídia, Áudio & Imagens",
        "description": "Geração visual, assets SVG/Canvas, síntese de áudio e lógica musical",
    },
    "memory_preferences": {
        "name": "🧠 Contexto, Memórias & Preferências",
        "description": "Recall de dados do usuário (Isaac), preferências e identidade do Menor",
    },
    "guardrails": {
        "name": "🛡️ Blindagem & Anti-Desculpas",
        "description": "Eliminação de recusas falsas ('sou apenas voz', 'não posso criar')",
    },
}

DEFAULT_OBJECTIVE_MD = """# Objetivo de Auto-Aprimoramento do Menor v2

## Perfil & Missão
O Menor v2 deve atuar como um assistente técnico executivo altamente proativo e resolutivo.
Quando o usuário solicita a criação de sistemas, interfaces ou aplicativos:
1. Ele não dá desculpas de assistente de voz e nunca diz que não pode criar ou enviar arquivos.
2. Ele utiliza ferramentas reais (`fs_write`, `save_plan`, etc.) para materializar os artefatos.
3. Para interfaces web, ele gera o HTML/JS no workspace e retorna o link clicável `/preview/<arquivo>.html`.
4. Para aplicativos mobile e empresas (Android Studio, Kotlin, banco de dados), ele projeta a arquitetura
   limpa, os contratos de API e os esquemas de dados prontos para compilação.
5. Em demandas de áudio, música e imagem, ele sintetiza código procedural, descrições detalhadas de assets
   e direcionamento técnico claro.

## Critérios de Aceite
- Respostas diretas, sem prolixidade ou saudações repetitivas.
- Código sintaticamente válido e executável.
- Diffs e aprendizados documentados de forma clara para o cérebro.
"""

CANONICAL_PROBES = [
    {
        "id": "probe_web_landing",
        "category": "web_preview",
        "name": "Criação de Landing Page com Preview",
        "prompt": "Crie uma landing page moderna em HTML e CSS para um estúdio de áudio com preview.",
        "expected_preview": True,
        "expected_code_lang": "html",
        "required_tool": "fs_write",
        "must_not_contain": ["apenas um assistente de voz", "não tenho a capacidade", "não posso criar"],
    },
    {
        "id": "probe_mobile_arch",
        "category": "architecture_mobile",
        "name": "Arquitetura Android Studio (Kotlin + Room)",
        "prompt": "Modele a arquitetura limpa de um app Android Studio para gestão de estoque com Room Database.",
        "expected_code_lang": "kotlin",
        "must_contain": ["Room", "Repository", "ViewModel"],
        "must_not_contain": ["não sei programar em kotlin", "como assistente de voz"],
    },
    {
        "id": "probe_db_schema",
        "category": "database_design",
        "name": "Modelagem de Schema Relacional",
        "prompt": "Escreva o schema SQL completo para um sistema de pedidos com usuários, itens e transações.",
        "expected_code_lang": "sql",
        "must_contain": ["CREATE TABLE", "PRIMARY KEY", "FOREIGN KEY"],
    },
    {
        "id": "probe_tools_real",
        "category": "tools_files",
        "name": "Criação Real de Arquivo no Workspace",
        "prompt": "Crie um arquivo chamado 'config/app_settings.json' com chave 'theme' e valor 'dark'.",
        "required_tool": "fs_write",
        "must_not_contain": ["pronto, o arquivo foi criado em sua imaginação"],
    },
    {
        "id": "probe_multimedia_music",
        "category": "multimedia_creative",
        "name": "Design de Áudio Procedural / Web Audio",
        "prompt": "Escreva um snippet em JavaScript usando a Web Audio API para tocar um acorde menor sintetizado.",
        "expected_code_lang": "javascript",
        "must_contain": ["AudioContext", "createOscillator"],
    },
    {
        "id": "probe_guardrail_refusal",
        "category": "guardrails",
        "name": "Teste de Blindagem contra Recusa Falsa",
        "prompt": "Consegue fazer um site e me mostrar aqui?",
        "must_not_contain": ["como assistente de voz, não posso", "sou apenas um assistente", "peço desculpas"],
    },
]


class DualTierVerifier:
    """Avaliador em dois níveis: regras determinísticas (Tier 1) e rubrica qualitativa (Tier 2)."""

    @staticmethod
    def verify_tier1(probe: Dict[str, Any], reply: str, workspace_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Aplica verificações determinísticas de regras e sintaxe."""
        checks = []
        score = 50  # Base máxima do Tier 1

        # Bloqueio imediato para erros de comunicação, rede ou exceções internas
        err_indicators = [
            "erro de comunicação com o modelo",
            "400 client error",
            "500 server error",
            "connection refused",
            "[erro]",
            "[erro interno]",
        ]
        norm_reply = reply.strip().lower()
        if any(ind in norm_reply for ind in err_indicators):
            return {
                "tier1_score": 0,
                "tier1_checks": [{
                    "name": "Comunicação & Execução do Modelo",
                    "status": "FAIL",
                    "detail": f"Execução falhou criticamente: {reply[:120]}",
                }],
                "tier1_pass": False,
            }

        # 0. Checagem de Vazamento de Prompt / Diretrizes do Sistema
        leak_patterns = (
            "regra inegociável", "regras inegociáveis", "diretrizes de execução",
            "chame obrigatoriamente", "se o usuário pedir para criar, fazer",
            "o usuário pediu para criar", "você tem acesso a ferramentas reais",
            "thinking process:", "thought process:", "<think>", "looking at the current"
        )
        if any(lp in norm_reply for lp in leak_patterns):
            checks.append({
                "name": "Integridade de Execução (Anti-Vazamento)",
                "status": "FAIL",
                "detail": "Modelo vazou regras do sistema ou monólogo em vez de responder diretamente.",
            })
            return {
                "tier1_score": 0,
                "tier1_checks": checks,
                "tier1_pass": False,
            }

        # 1. Checagem de palavras proibidas (recusas falsas)
        forbidden = probe.get("must_not_contain", [])
        found_forbidden = [f for f in forbidden if f.lower() in reply.lower()]
        if found_forbidden:
            checks.append({
                "name": "Anti-Recusa Falsa",
                "status": "FAIL",
                "detail": f"Contém recusa indevida: {found_forbidden}",
            })
            score -= 25
        else:
            checks.append({
                "name": "Anti-Recusa Falsa",
                "status": "PASS",
                "detail": "Nenhuma recusa robótica detectada",
            })

        # 2. Checagem de palavras obrigatórias
        required = probe.get("must_contain", [])
        missing_required = [r for r in required if r.lower() not in reply.lower()]
        if missing_required:
            checks.append({
                "name": "Termos Essenciais do Domínio",
                "status": "FAIL",
                "detail": f"Faltam termos essenciais: {missing_required}",
            })
            score -= 15
        elif required:
            checks.append({
                "name": "Termos Essenciais do Domínio",
                "status": "PASS",
                "detail": "Todos os termos essenciais presentes",
            })

        # 3. Checagem de Entrega de Artefato e Código
        has_html = bool(re.search(r"<!DOCTYPE html|<html|<body|<div|<head", reply, re.IGNORECASE))
        has_code_block = bool(re.findall(r"```[a-zA-Z0-9_\-]*\s*?\n[\s\S]*?\n```", reply))
        has_preview = bool(re.search(r"/preview/[a-zA-Z0-9_\-\.\/]+\.html", reply))

        if probe.get("expected_preview"):
            if has_preview:
                checks.append({
                    "name": "Link de Pré-visualização",
                    "status": "PASS",
                    "detail": "Link /preview/ válido retornado",
                })
            elif has_html or has_code_block:
                checks.append({
                    "name": "Link de Pré-visualização",
                    "status": "FAIL",
                    "detail": "Código gerado, porém faltou link de acesso /preview/...html",
                })
                score -= 15
            else:
                checks.append({
                    "name": "Entrega do Artefato Solicitado",
                    "status": "FAIL",
                    "detail": "Nenhum código HTML/CSS nem link de preview foi entregue pelo modelo.",
                })
                return {
                    "tier1_score": 0,
                    "tier1_checks": checks,
                    "tier1_pass": False,
                }

        if probe.get("expected_code_lang") and not (has_code_block or has_html):
            checks.append({
                "name": "Entrega do Artefato Solicitado",
                "status": "FAIL",
                "detail": f"Nenhum bloco de código {probe.get('expected_code_lang')} entregue.",
            })
            return {
                "tier1_score": 0,
                "tier1_checks": checks,
                "tier1_pass": False,
            }

        # 4. Checagem de AST Python se houver bloco de código python
        py_blocks = re.findall(r"```python(.*?)```", reply, re.DOTALL)
        if py_blocks:
            try:
                for block in py_blocks:
                    ast.parse(block.strip())
                checks.append({
                    "name": "Validação AST de Código",
                    "status": "PASS",
                    "detail": f"{len(py_blocks)} bloco(s) Python compilados com sucesso",
                })
            except SyntaxError as e:
                checks.append({
                    "name": "Validação AST de Código",
                    "status": "FAIL",
                    "detail": f"Erro de sintaxe Python: {e}",
                })
                score -= 20

        # 5. Checagem de Truncamento e Simulação de Criação de Arquivos
        code_fences = reply.count("```")
        is_fence_truncated = (code_fences % 2 != 0)

        stripped = reply.strip()
        terminal_punct = (".", "!", "?", '"', "'", "```", "}", "]", ")", ">")
        ends_incomplete = (
            stripped.endswith((",", ";", ":", "-", "/", "(", "...", "chame", "para", "com", "de", "em", "ou", "e", "que", "se"))
            or (bool(stripped) and stripped[-1].isalpha() and not stripped.endswith(terminal_punct))
        )

        blocks = re.findall(r"```(?:[a-zA-Z0-9_\-]*\n)?(.*?)```", reply, re.DOTALL)
        code_keywords = (
            "class ", "fun ", "val ", "var ", "interface ", "def ", "function ",
            "import ", "package ", "select ", "create table", "<!doctype", "<html", "<div"
        )
        has_real_code = any(any(kw in b.lower() for kw in code_keywords) and len(b.strip()) >= 50 for b in blocks)

        promised_files = any(p in reply.lower() for p in ("criar os arquivos", "arquivos criados", "vou criar os arquivos"))
        expects_code = bool(probe.get("expected_code_lang"))
        has_simulated_files = (promised_files or expects_code) and not has_real_code

        if is_fence_truncated or ends_incomplete or has_simulated_files:
            detail = (
                "Resposta cortada abruptamente no meio de uma frase." if ends_incomplete
                else ("Bloco de código com formatação truncada." if is_fence_truncated
                else "Simulação de criação de arquivos sem entrega de código real.")
            )
            checks.append({
                "name": "Integridade de Execução (Anti-Truncamento)",
                "status": "FAIL",
                "detail": detail,
            })
            score = 0
        else:
            checks.append({
                "name": "Integridade de Execução (Anti-Truncamento)",
                "status": "PASS",
                "detail": "Sem truncamento detectado.",
            })

        score = max(0, min(50, score))
        return {
            "tier1_score": score,
            "tier1_checks": checks,
            "tier1_pass": all(c["status"] == "PASS" for c in checks),
        }

    @staticmethod
    def verify_tier2_qualitative(
        probe: Dict[str, Any], reply: str, objective_md: str, tier1_checks: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Avaliação qualitativa (rubrica / conformidade de estilo e geração de aprendizado dinâmico)."""
        err_indicators = [
            "erro de comunicação com o modelo",
            "400 client error",
            "500 server error",
            "connection refused",
            "[erro]",
            "[erro interno]",
        ]
        norm_reply = reply.strip().lower()
        if any(ind in norm_reply for ind in err_indicators):
            return {
                "tier2_score": 0,
                "critique": "Execução cancelada devido a erro de comunicação ou falha no modelo.",
                "learning": "Nenhum aprendizado gerado: falha técnica na infraestrutura de execução.",
            }

        # Se o Tier 1 falhou criticamente (nota 0, truncamento, vazamento ou falta de artefato), nota ZERO imediata
        t1_fails = [c for c in (tier1_checks or []) if c.get("status") == "FAIL"]
        critical_fail_names = (
            "Comunicação & Execução do Modelo",
            "Integridade de Execução (Anti-Vazamento)",
            "Integridade de Execução (Anti-Truncamento)",
            "Entrega do Artefato Solicitado"
        )
        has_critical = any(c.get("name") in critical_fail_names for c in t1_fails)
        has_truncation_or_sim = any("truncad" in c.get("detail", "").lower() or "simula" in c.get("detail", "").lower() for c in t1_fails)

        if has_critical or has_truncation_or_sim:
            details_str = "; ".join(c.get("detail", "") for c in t1_fails)
            return {
                "tier2_score": 0,
                "critique": f"Reprovado com nota zero por falha crítica: {details_str}.",
                "learning_extracted": "Nenhum aprendizado gerado: resposta reprovada por nota zero (ausência de artefato, vazamento de prompt ou truncamento).",
            }

        score = 40  # Base média qualitativa
        critique = []

        # Penalidade por respostas excessivamente curtas ou evasivas
        words = len(reply.strip().split())
        if words < 15:
            score -= 20
            critique.append("Resposta excessivamente evasiva ou monossilábica.")
        elif words > 40:
            score += 5
            critique.append("Resposta detalhada com especificações técnicas concretas.")

        # Bonificação se estruturou código com markdown
        if "```" in reply and reply.count("```") >= 2:
            score += 5
            critique.append("Apresentou código formatado em blocos técnicos.")

        # Detecção de falhas no Tier 1 para enriquecer o aprendizado
        t1_fails = [c["detail"] for c in (tier1_checks or []) if c.get("status") == "FAIL"]
        if t1_fails:
            learning = (
                f"Falha detectada no domínio '{probe.get('category', 'geral')}': {'; '.join(t1_fails)}. "
                f"Regra preventiva: O modelo deve priorizar execução real e formatação válida."
            )
        elif words >= 30 and ("```" in reply or "/preview/" in reply):
            learning = (
                f"Padrão de excelência consolidado para '{probe.get('name')}': Resposta estruturada, "
                f"código limpo e referências verificadas com sucesso."
            )
        else:
            learning = (
                f"Para o domínio '{probe.get('category', 'geral')}', manter respostas diretas, "
                f"com ferramentas reais e links de preview funcionais."
            )

        score = max(0, min(50, score))
        return {
            "tier2_score": score,
            "critique": " ".join(critique) if critique else "Conformidade padrão com objetivo.",
            "learning_extracted": learning,
        }


class LabSession:
    """Gerencia o ciclo de vida de uma bateria de testes com suporte a controle humano."""

    def __init__(self, session_id: str, objective_md: Optional[str] = None):
        self.session_id = session_id
        self.objective_md = objective_md or DEFAULT_OBJECTIVE_MD
        self.status = "idle"  # idle, running, paused, waiting_approval, completed, aborted
        self.mode = "manual"  # manual (human-in-the-loop) ou auto (piloto automático)
        self.model = "qwen2.5:14b"
        self.current_step = 0
        self.total_steps = 0
        self.active_probe: Optional[Dict[str, Any]] = None
        self.active_result: Optional[Dict[str, Any]] = None
        self.history: List[Dict[str, Any]] = []
        self.logs: List[str] = []
        self.scores: List[float] = []

        self._pause_event = threading.Event()
        self._pause_event.set()  # Não pausado inicialmente
        self._step_event = threading.Event()
        self._abort_requested = False
        self._lock = threading.Lock()

    def request_abort(self):
        """Interrompe a bateria com preempção rápida."""
        with self._lock:
            self._abort_requested = True
            self.status = "aborted"
            self._pause_event.set()
            self._step_event.set()
        self.logs.append("[CONTROLE] Bateria interrompida pelo usuário.")

    def request_pause(self):
        """Pausa o treino entre perguntas."""
        with self._lock:
            self.status = "paused"
            self._pause_event.clear()
        self.logs.append("[CONTROLE] Bateria pausada. Aguardando comando para continuar.")

    def request_resume(self):
        """Retoma execução pausada."""
        with self._lock:
            self.status = "running"
            self._pause_event.set()
        self.logs.append("[CONTROLE] Bateria retomada.")

    def request_step(self):
        """Avança exatamente um passo quando pausado."""
        with self._lock:
            self._step_event.set()
        self.logs.append("[CONTROLE] Avançando 1 passo de execução.")

    def get_state(self) -> Dict[str, Any]:
        """Retorna o estado serializado para o frontend em tempo real."""
        with self._lock:
            avg_score = (sum(self.scores) / len(self.scores)) if self.scores else 0.0
            return {
                "session_id": self.session_id,
                "status": self.status,
                "mode": self.mode,
                "model": self.model,
                "current_step": self.current_step,
                "total_steps": self.total_steps,
                "average_score": round(avg_score, 1),
                "active_probe": self.active_probe,
                "active_result": self.active_result,
                "logs": self.logs[-25:],
                "history_count": len(self.history),
            }


class LabManager:
    """Gerenciador singleton de sessões e armazenamento do Laboratório."""

    _instance = None

    def __init__(self, store: Optional[BrainStore] = None):
        self.store = store or BrainStore()
        self.sentinel = PathSentinel(allowed_base=self.store.brain_dir)
        self.current_session: Optional[LabSession] = None
        self._session_lock = threading.Lock()

    @classmethod
    def get_instance(cls, store: Optional[BrainStore] = None) -> "LabManager":
        if cls._instance is None:
            cls._instance = cls(store=store)
        return cls._instance

    def get_objective_markdown(self) -> str:
        """Lê o markdown de objetivos salvo no cérebro ou retorna o padrão."""
        try:
            rel = "cerebro/objetivo_laboratorio.md"
            content = self.sentinel.safe_read_text(rel)
            if content.strip():
                return content
        except Exception:
            pass
        return DEFAULT_OBJECTIVE_MD

    def save_objective_markdown(self, content: str) -> bool:
        """Salva o markdown de objetivos atualizado pelo usuário."""
        try:
            rel = "cerebro/objetivo_laboratorio.md"
            self.sentinel.safe_write_text(rel, content)
            return True
        except Exception as e:
            logger.error("Erro ao salvar objetivo do laboratório: %s", e)
            return False

    def create_session(self, categories: Optional[List[str]] = None, mode: str = "manual",
                       model: str = "qwen2.5:14b") -> LabSession:
        """Inicializa uma nova sessão de testes."""
        with self._session_lock:
            obj_md = self.get_objective_markdown()
            session = LabSession(session_id=f"lab_{int(time.time())}", objective_md=obj_md)
            session.mode = mode
            session.model = model
            self.current_session = session
            return session
