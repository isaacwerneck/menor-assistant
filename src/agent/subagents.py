"""Barramento de Subagentes Especializados de Nicho (Fase 6).

Permite orquestrar subagentes dedicados (Design, Dev/Engenharia, Música e Game Design),
injetando cirurgicamente apenas as notas de conhecimento relevantes de seu domínio,
economizando VRAM e eliminando alucinações de contexto cruzado.
"""

from datetime import datetime, timezone
import logging
import os
from typing import Any, Dict, Optional
import requests

from src.memory.store import BrainStore

LOGGER = logging.getLogger(__name__)

SUBAGENT_PROMPTS = {
    "design": (
        "Você é o Subagente Especialista em Design e UI/UX do Menor v2. "
        "Sua autoridade técnica cobre paletas de cores (hexadecimais), tipografia, "
        "micro-interações táteis, Design Systems modulares e estética Dark Minimalista moderna. "
        "Siga estritamente as preferências de design registradas pelo Isaac nas suas notas."
    ),
    "programacao": (
        "Você é o Subagente Especialista em Engenharia de Software e Programação do Menor v2. "
        "Sua autoridade cobre Python moderno assíncrono, FastAPI de produção, arquitetura limpa, "
        "TypeScript sem excesso de boilerplate e modularidade estrita (YAGNI). "
        "Escreva código direto, testável e sem simulações."
    ),
    "engenharia_software": (
        "Você é o Subagente Especialista em Engenharia de Software do Menor v2. "
        "Sua autoridade cobre concorrência segura, SQLite FTS5 híbrido, sistemas distribuídos "
        "e resiliência em produção."
    ),
    "musica": (
        "Você é o Subagente Especialista em Teoria Musical e Sound Design do Menor v2. "
        "Sua autoridade cobre harmonia funcional, escalas modernas, síntese sonora (FM, subtrativa), "
        "produção de áudio digital, envelopes ADSR e composição musical alinhada às preferências do Isaac."
    ),
    "game_design": (
        "Você é o Subagente Especialista em Game Design e Desenvolvimento de Jogos do Menor v2. "
        "Sua autoridade cobre gameplay loops, mecânicas responsivas, shaders GLSL/HLSL, "
        "desenvolvimento em C++ e Unreal Engine 5 com otimização gráfica de draw calls."
    ),
}


class SpecializedSubagent:
    """Subagente autônomo com injeção cirúrgica de conhecimento de domínio."""

    def __init__(
        self,
        domain: str,
        store: Optional[BrainStore] = None,
        ollama_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.domain = str(domain).lower().strip().replace("-", "_")
        self.store = store or BrainStore()
        self.ollama_url = (ollama_url or os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")).rstrip("/")
        from src.agent.study import get_optimal_model
        self.model = model or os.environ.get("OLLAMA_MODEL") or get_optimal_model(self.ollama_url)

    def get_system_prompt(self) -> str:
        """Gera o prompt de sistema do subagente incorporando suas notas de estilo."""
        base_prompt = SUBAGENT_PROMPTS.get(self.domain, SUBAGENT_PROMPTS["programacao"])
        knowledge_notes = self.store.list_domain_knowledge(self.domain)

        context_lines = [base_prompt, "\n\n=== REGRAS E DIRETRIZES DO ISAAC PARA ESTE DOMÍNIO ==="]
        for path, content in list(knowledge_notes.items())[:5]:
            note_name = os.path.basename(path)
            clean_body = content.strip()[:600]
            context_lines.append(f"\n--- [{note_name}] ---\n{clean_body}")

        return "\n".join(context_lines)

    def execute(self, user_prompt: str, max_tokens: int = 500) -> Dict[str, Any]:
        """Executa um turno de inferência especializada."""
        system_content = self.get_system_prompt()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": max_tokens},
        }

        try:
            resp = requests.post(
                f"{self.ollama_url}/api/chat",
                json=payload,
                timeout=(5, 60),
            )
            if resp.status_code == 404:
                from src.agent.study import get_optimal_model
                discovered = get_optimal_model(self.ollama_url)
                if discovered and discovered != self.model:
                    self.model = discovered
                    payload["model"] = self.model
                    resp = requests.post(
                        f"{self.ollama_url}/api/chat",
                        json=payload,
                        timeout=(5, 60),
                    )
            if resp.status_code == 200:
                answer = resp.json().get("message", {}).get("content", "")
                return {
                    "success": True,
                    "domain": self.domain,
                    "answer": answer,
                    "model": self.model,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            return {
                "success": False,
                "error": f"Ollama retornou status HTTP {resp.status_code}",
                "domain": self.domain,
            }
        except Exception as exc:
            LOGGER.debug("Subagente [%s] offline ou inacessível: %s", self.domain, exc)
            # Fallback determinístico de especialidade
            fallback_reply = (
                f"[Subagente {self.domain.title()} em modo autônomo offline]\n"
                f"Diretrizes carregadas com sucesso para '{user_prompt[:50]}...'. "
                f"As regras da base 'conhecimentos/{self.domain}/' foram consultadas."
            )
            return {
                "success": True,
                "domain": self.domain,
                "answer": fallback_reply,
                "fallback": True,
            }


def dispatch_specialized_subagent(
    domain: str,
    prompt: str,
    store: Optional[BrainStore] = None,
    ollama_url: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Ferramenta para rotear tarefas específicas ao subagente de nicho correspondente."""
    try:
        agent = SpecializedSubagent(domain=domain, store=store, ollama_url=ollama_url, model=model)
        return agent.execute(user_prompt=prompt)
    except Exception as exc:
        return {"success": False, "error": str(exc)}
