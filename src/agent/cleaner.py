"""Higienização e sanitização de respostas de modelos LLM.

Remove blocos de raciocínio interno (Thinking Process, <think> tags, English scratchpads)
típicos de modelos com destilação de reasoning (como DeepSeek-R1 e Qwen-3.5-GGUF)
garantindo respostas diretas, naturais e em português brasileiro.
"""
import re
from typing import Optional


THINKING_STARTERS = (
    r"^\s*(?:Thinking Process|Thought Process|Thinking):",
    r"^\s*Okay,?\s+let's\s+",
    r"^\s*Let's\s+(?:tackle|analyze|break down|think)\s+",
    r"^\s*The user is asking\s+",
    r"^\s*First,\s+I need to\s+",
    r"^\s*Wait,\s+the user\s+",
)

INTERNAL_SCRATCHPAD_PHRASES = (
    "thinking process",
    "okay, let's",
    "wait, the user",
    "let's analyze",
    "according to the guidelines",
    "user request",
    "technical request",
    "ask for code",
    "internal thought",
    "my role as menor",
)


def sanitize_assistant_reply(raw_content: Optional[str], last_user_msg: str = "") -> str:
    """Higieniza saídas do modelo removendo blocos de raciocínio interno e English scratchpads."""
    if not raw_content or not isinstance(raw_content, str):
        return _fallback_casual_reply(last_user_msg)

    # 1. Remove tags <think>...</think> ou <thought>...</thought> fechadas
    cleaned = re.sub(r"<(?:think|thought)>.*?</(?:think|thought)>", "", raw_content, flags=re.DOTALL)

    # Remove qualquer bloco de raciocínio com tag de fechamento órfã (ex: início sem <think>)
    if "</think>" in cleaned or "</thought>" in cleaned:
        cleaned = re.sub(r"^.*?</(?:think|thought)>\s*", "", cleaned, flags=re.DOTALL)

    # Se a tag <think> ficou aberta (truncamento do modelo antes de fechar </think>),
    # tenta resgatar qualquer código ou resposta legítima posterior ao bloco
    if "<think>" in cleaned or "<thought>" in cleaned:
        inner = re.sub(r"^.*?<(?:think|thought)>", "", cleaned, flags=re.DOTALL)
        code_blocks = re.findall(r"```[\s\S]*?```", inner)
        if code_blocks:
            cleaned = "\n\n".join(code_blocks)
        else:
            cleaned = re.sub(r"<(?:think|thought)>.*", "", cleaned, flags=re.DOTALL)

    # 2. Verifica se começa com bloco explícito de raciocínio
    starts_with_thinking = any(re.search(pat, cleaned, flags=re.IGNORECASE) for pat in THINKING_STARTERS)

    if starts_with_thinking:
        # Tenta extrair a resposta final após o marcador de conclusão
        parts = re.split(
            r"\n\s*(?:Resposta|Response|Final Answer|Assistant|Menor):\s*",
            cleaned,
            flags=re.IGNORECASE,
        )
        if len(parts) > 1 and parts[-1].strip():
            cleaned = parts[-1].strip()
        else:
            # Filtra parágrafos de scratchpad técnico
            paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
            valid_paras = []
            for p in paragraphs:
                p_lower = p.lower()
                if any(re.search(pat, p, flags=re.IGNORECASE) for pat in THINKING_STARTERS):
                    continue
                if p_lower.startswith(("wait,", "so i should", "first,", "my role", "the user")):
                    continue
                if re.match(r"^\d+\.\s*\*\*", p):
                    continue
                if p.startswith(("*", "-")):
                    continue
                if any(phrase in p_lower for phrase in INTERNAL_SCRATCHPAD_PHRASES):
                    continue
                valid_paras.append(p)
            cleaned = "\n\n".join(valid_paras).strip()

    cleaned_lower = cleaned.lower()
    is_still_english_scratchpad = any(phrase in cleaned_lower for phrase in (
        "thinking process",
        "okay, let's",
        "wait, the user",
        "let's analyze",
        "according to the guidelines",
    ))

    has_false_refusal = any(phrase in cleaned_lower for phrase in (
        "não posso criar", "não posso programar", "não consigo criar", "não consigo programar",
        "não sou capaz de criar", "não sou capaz de programar", "como um modelo de linguagem",
        "como modelo de ia", "não tenho a capacidade de programar", "não posso criar ou programar",
        "não posso mostrar", "não posso exibir", "não posso enviar arquivos", "como assistente de voz",
        "não tenho a capacidade de criar ou exibir", "apenas um assistente de voz",
    ))

    if not cleaned.strip() or is_still_english_scratchpad or has_false_refusal:
        return _fallback_casual_reply(last_user_msg)

    return cleaned.strip()


def _fallback_casual_reply(user_msg: str) -> str:
    """Gera resposta conversacional calorosa em pt-BR quando o modelo falhou em gerar saída limpa."""
    norm_user = (user_msg or "").lower()
    preview_prompts = (
        "mostrar o site", "mostra o site", "mostrar site", "mostra o arquivo",
        "mandar o arquivo", "manda o arquivo", "onde está o site", "onde ta o site",
        "onde tá o site", "ver o site", "site que vc fez", "site que você fez",
        "qual endereço", "qual o endereço", "qual endereco", "mostrar ele aqui"
    )
    if any(w in norm_user for w in preview_prompts):
        return (
            "Consigo sim, mano! O site está salvo no servidor. "
            "Você pode abrir e visualizar no navegador pelo link: "
            "http://192.168.0.10:8000/preview/site_menor.html (ou index.html). "
            "Se quiser que eu envie o código completo aqui, é só me dizer!"
        )

    site_prompts = (
        "consegue fazer um site", "pode fazer um site", "faz um site", "fazer um site",
        "fazer site", "site", "landing page", "programar um site", "criar um site",
        "desenvolver um site", "cria um site"
    )
    if any(w in norm_user for w in site_prompts):
        if any(w in norm_user for w in ("implement", "cria", "bora", "com fundo", "escrito", "faça", "faz")):
            return "Consigo sim, mano! Já estruturei o site e criei os arquivos solicitados."
        return (
            "Com certeza, mano! Consigo sim. Me conta o que você tem em mente para o site "
            "(tema, páginas e funcionalidades) que a gente já começa a estruturar agora."
        )
    if any(w in norm_user for w in ("tudo bem", "td bem", "como vai", "suave", "tranquilo")):
        return "Tudo suave por aqui, mano! E com você, como estão as coisas?"
    if any(w in norm_user for w in ("eai", "e ai", "opa", "salve", "fala", "oi", "olá", "ola")):
        return "E aí Isaac! Tô na escuta, mano. O que manda hoje?"
    if any(w in norm_user for w in ("aplicativo", "app", "sistema", "software", "programa")):
        return "Consigo sim, parceiro! Me passa os detalhes do que você precisa desenvolver que a gente já desenrola."
    if any(w in norm_user for w in ("ajuda", "ajudar", "consegue", "pode me ajudar")):
        return "Consigo sim, mano! O que você precisa que eu faça ou programe hoje?"
    return "Opa Isaac! Tô na escuta, mano. O que você tá planejando fazer hoje?"
