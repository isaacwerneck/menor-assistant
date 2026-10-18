"""Interpreta respostas curtas a perguntas pendentes, sem chamada extra ao LLM.

Não inventa ação quando a pergunta não tem destino definido.
"""
import re
import unicodedata

CATEGORIES = {
    "tool": {"ferramenta", "ferramentas", "skill", "skills", "habilidade", "habilidades"},
    "project": {"projeto", "projetos"},
    "knowledge": {"conhecimento", "conhecimentos", "aprendizado", "aprendizados", "cerebro"},
    "preference": {"preferencia", "preferencias", "pessoal", "perfil"},
}
YES = {"sim", "simm", "simmm", "ss", "ssim", "isso", "claro", "pode", "pode sim", "bora",
       "com certeza", "confirmo", "confirmado", "exato", "exatamente", "isso mesmo"}
NO = {"nao", "naoo", "nn", "nao precisa", "deixa", "deixa pra la", "cancela",
      "cancele", "esquece", "melhor nao", "nao quero", "nem", "negativo"}


def normalize(text):
    folded = unicodedata.normalize("NFKD", text.lower().strip())
    return " ".join(
        re.sub(r"[^a-z0-9 ]+", " ", "".join(c for c in folded if not unicodedata.combining(c))).split()
    )


def simple_answer(answer, suggested_target="none", question="", project=None):
    """Retorna ação clara ou None; não processa pedidos abertos ou complexos."""
    text = normalize(answer)
    if not text or len(text) > 100:
        return None
    if text in NO:
        return {"decision": "cancel", "target": "none", "note_kind": "none", "question": ""}
    question_folded = normalize(question)
    mentioned = {
        kind for kind, aliases in CATEGORIES.items()
        if any(re.search(r"\b" + re.escape(alias) + r"\b", text) for alias in aliases)
    }
    if len(mentioned) == 1 and len(text.split()) <= 8:
        target = next(iter(mentioned))
        return {"decision": "save", "target": target, "note_kind": "none", "question": ""}
    if text in YES:
        # Sim só basta se a pergunta já especificava um único destino claro.
        hints = {kind for kind, aliases in CATEGORIES.items()
                 if any(re.search(r"\b" + re.escape(alias) + r"\b", question_folded)
                        for alias in aliases)}
        if suggested_target in CATEGORIES and (hints == {suggested_target}):
            return {"decision": "save", "target": suggested_target,
                    "note_kind": "none", "question": ""}
        return {"decision": "ask", "target": suggested_target, "note_kind": "none",
                "question": "Beleza. Em qual pasta devo guardar: conhecimentos, projetos ou ferramentas?"}
    return None
