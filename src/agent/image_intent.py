"""Detecta pedidos de uso de imagens, separados da criação de novas skills.

Pergunta somente quando faltar cena, arquivo ou instrução. Não usa LLM
para roteamento trivial; reduz falsos negativos do Qwen Coder 7B.
"""
import re
import unicodedata


def _normalize(text):
    folded = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in folded if not unicodedata.combining(c))


def image_intent(message, has_attachment=False):
    if not isinstance(message, str) or len(message) > 8000:
        return {"decision": "chat"}
    normal = _normalize(message.strip())
    # Criar o SOFTWARE de imagens não é pedir um arquivo de imagem pronto.
    if re.search(r"\b(ferramenta|skill|plugin|aplicativo|sistema)\b", normal) and re.search(
        r"\b(criar|desenvolver|programar|implementar|construir|fazer)\b", normal
    ):
        return {"decision": "chat"}
    if re.search(r"\b(como|tutorial|ensina|aprender|explica)\b", normal[:55]):
        return {"decision": "chat"}
    editing = bool(re.search(
        r"\b(edita|editar|edite|modifica|modificar|transforma|remova?|tira|altera)\b", normal
    ) and re.search(r"\b(imagem|foto|fotografia|figura|arquivo|fundo)\b", normal))
    making = bool(re.search(
        r"\b(cria|crie|criar|faz|faca|fazer|gera|gere|gerar|desenha|desenhe)\b", normal
    ) and re.search(
        r"\b(imagem|imagens|foto|fotografia|arte|capa|ilustracao|desenho|wallpaper)\b", normal
    ))
    if editing:
        if not has_attachment:
            return {"decision": "image_ask", "kind": "edit",
                    "question": "Manda a imagem que quer editar e me diz o que mudar."}
        if len(normal) < 35 or normal in ("edita essa imagem", "edita essa foto", "editar imagem"):
            return {"decision": "image_ask", "kind": "edit",
                    "question": "O que você quer mudar na imagem?"}
        return {"decision": "image_edit", "prompt": message.strip()}
    if making:
        # "cria uma imagem pra mim" não descreve o que criar.
        scene = re.search(
            r"\b(?:imagem|foto|arte|capa|ilustracao|desenho|wallpaper)\s+"
            r"(?:de|do|da|com|mostrando|sobre)\s+(.+)", normal
        )
        if scene and len(scene.group(1).strip()) >= 7:
            return {"decision": "image_generate", "prompt": message.strip()}
        return {"decision": "image_ask", "kind": "generate",
                "question": "Que imagem você quer? Me descreve a cena e o estilo."}
    return {"decision": "chat"}
