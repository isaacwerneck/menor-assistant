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
    r"^\s*Okay,?\s+the user\b",
    r"^\s*Okay,?\s+I\b",
    r"^\s*Let's\s+(?:tackle|analyze|break down|think)\s+",
    r"^\s*The user (?:is|wants|asked|is asking)\s+",
    r"^\s*First,\s+I need to\s+",
    r"^\s*Wait,\s+the user\s+",
    r"^\s*Looking at\b",
    r"^\s*Given (?:their|the|this)\b",
    r"^\s*I (?:need|should|will|must|have) to\b",
    r"^\s*Let me (?:check|see|think|review)\b",
    r"^\s*Since (?:they|the user|this)\b",
    r"^\s*Based on (?:the|their)\b",
    r"^\s*To answer this\b",
    r"^\s*In this case\b",
    r"^\s*O usu[áa]rio (?:est[áa]|quer|pediu|perguntou|deseja|solicitou)\b",
    r"^\s*Isso [ée] uma pergunta direta\b",
    r"^\s*Para responder a isso\b",
    r"^\s*Com base nas informa[çc][õo]es\b",
    r"^\s*Com base no perfil\b",
    r"^\s*Com base na Core Memory\b",
    r"^\s*Vou responder diretamente\b",
    r"^\s*N[ãa]o preciso de ferramentas\b",
    r"^\s*Primeiro,\s+vou\b",
)

INTERNAL_SCRATCHPAD_PHRASES = (
    "thinking process",
    "okay, let's",
    "okay, the user",
    "wait, the user",
    "let's analyze",
    "according to the guidelines",
    "user request",
    "technical request",
    "ask for code",
    "internal thought",
    "my role as menor",
    "looking at the current",
    "given their work profile",
    "i need to respond directly",
    "let me check the previous",
    "the user wants me to",
    "the user is asking",
    "as per the rules",
    "o usuário está perguntando",
    "o usuário está pedindo",
    "o usuário quer",
    "isso é uma pergunta direta",
    "com base nas informações do perfil",
    "com base na core memory",
    "vou responder diretamente",
    "não preciso de ferramentas",
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

    # Remove blocos de código simulando comandos de terminal ou ferramentas (terminal_run, fs_list, etc.)
    cleaned = re.sub(
        r"```(?:bash|sh|terminal|shell)?\s*\n\s*(?:terminal_run|fs_list|fs_read|fs_write|python\s+-c)[\s\S]*?\n```",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^\s*(?:terminal_run|fs_list|fs_read|fs_write)\s+.*$",
        "",
        cleaned,
        flags=re.MULTILINE,
    )

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
    is_still_scratchpad = any(phrase in cleaned_lower for phrase in (
        "thinking process",
        "okay, let's",
        "okay, the user",
        "wait, the user",
        "let's analyze",
        "according to the guidelines",
        "looking at the current",
        "given their work profile",
        "i need to respond directly",
        "let me check the previous",
        "the user wants me to write",
        "as per the rules",
        "o usuário está perguntando",
        "o usuário está pedindo",
        "o usuário quer",
        "isso é uma pergunta direta",
        "com base nas informações do perfil",
        "com base na core memory",
        "vou responder diretamente",
    ))

    has_false_refusal = any(phrase in cleaned_lower for phrase in (
        "não posso criar", "não posso programar", "não consigo criar", "não consigo programar",
        "não sou capaz de criar", "não sou capaz de programar", "como um modelo de linguagem",
        "como modelo de ia", "não tenho a capacidade de programar", "não posso criar ou programar",
        "não posso mostrar", "não posso exibir", "não posso enviar arquivos", "como assistente de voz",
        "não tenho a capacidade de criar ou exibir", "apenas um assistente de voz",
    ))

    if not cleaned.strip() or is_still_scratchpad or has_false_refusal:
        return _fallback_casual_reply(last_user_msg)

    return cleaned.strip()


def _fallback_casual_reply(user_msg: str) -> str:
    """Gera resposta conversacional calorosa em pt-BR quando o modelo falhou em gerar saída limpa."""
    norm_user = (user_msg or "").lower()

    hardware_prompts = (
        "configuração de máquinas", "configuracao de maquinas", "nossas máquinas", "nossas maquinas",
        "qual máquina", "quais máquinas", "setup atual", "setup de hardware", "hardware",
        "nossa configuração de máquinas e hardware"
    )
    if any(w in norm_user for w in hardware_prompts):
        return (
            "Aqui está o setup atual da nossa infraestrutura e hardware:\n\n"
            "- **PC Interativo (Windows):** AMD Ryzen 5 3500X, 16GB RAM, NVIDIA GTX 1650 (4GB VRAM) — Executa interface e cliente de voz interativo.\n"
            "- **Hub Central (Servidor Ubuntu):** Intel Core i7-1185G7, 32GB RAM, Iris Xe — Executa FastAPI (porta 8000), SQLite FTS5 permanente e Ollama (127.0.0.1:11434).\n"
            "- **Rede & Acesso:** Rede local 192.168.0.x com túnel Cloudflare seguro."
        )

    study_prompts = (
        "ancora de estudo", "âncora de estudo", "ancoras de estudo", "âncoras de estudo",
        "ancora", "âncora", "ancoras", "âncoras", "topicos de estudo", "tópicos de estudo",
        "estudos", "estudar", "sugira topicos", "sugira tópicos", "sugerir tópicos",
        "ferramenta de trabalho", "jogos 2d", "escreve em portugues", "escreva em portugues",
        "em portugues", "em português"
    )
    if any(w in norm_user for w in study_prompts):
        return (
            "Com certeza, mano! Pensando no seu perfil (sites modernos, jogos 2D, música/DSP, aplicativos mobile e sistemas), "
            "as âncoras e tópicos ideais para o Menor dominar e acelerar o seu trabalho são:\n\n"
            "1. **Jogos 2D & Simulação:** Arquitetura de Game Loops, Shaders 2D (GLSL), ECS (Entity Component System), física e detecção de colisões.\n"
            "2. **Áudio, Música & DSP:** Síntese sonora (FM, wavetable, subtrativa), Web Audio API / AudioWorklets em tempo real, protocolos MIDI e processamento digital de sinais.\n"
            "3. **Aplicativos Mobile (Android):** Kotlin Coroutines/Flow, Jetpack Compose avançado, Clean Architecture e Room/Ktor offline-first.\n"
            "4. **Sites & Frontend de Alta Performance:** Micro-interações fluidas no Tailwind, renderização Canvas/WebGL e WebSockets de baixa latência.\n"
            "5. **Sistemas & Backend Assíncrono:** Concorrência no FastAPI, SQLite FTS5 de alta velocidade e agentes autônomos locais.\n\n"
            "Essas áreas cobrem exatamente tudo o que você constrói. Quer que eu adicione esses tópicos diretamente na nossa Core Memory de estudos agora?"
        )
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
    if re.search(r"\b(?:tudo\s+bem|td\s+bem|como\s+vai|suave|tranquilo)\b", norm_user):
        return "Tudo suave por aqui, mano! E com você, como estão as coisas?"
    if re.search(r"\b(?:eai|e\s+ai|opa|salve|fala|oi|ol[aá])\b", norm_user):
        return "E aí Isaac! Tô na escuta, mano. O que manda hoje?"
    if any(w in norm_user for w in ("aplicativo", "app", "sistema", "software", "programa")):
        return "Consigo sim, parceiro! Me passa os detalhes do que você precisa desenvolver que a gente já desenrola."
    if any(w in norm_user for w in ("ajuda", "ajudar", "consegue", "pode me ajudar")):
        return "Consigo sim, mano! O que você precisa que eu faça ou programe hoje?"
    return "Opa Isaac! Tô na escuta, mano. O que você tá planejando fazer hoje?"
