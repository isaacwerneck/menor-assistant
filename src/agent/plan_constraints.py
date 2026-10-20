"""Parecer determinístico e conservador sobre restrições de planos.

A saída é apenas um AVISO, não autorização para ferramentas nem selo de qualidade.
"""
import re
import unicodedata

_ACTIONS = {
    "apagar": r"\b(?:apag\w*|exclu\w*|delet\w*|remov\w*)\b",
    "mover": r"\b(?:mov\w*|desloc\w*|transfer\w*)\b",
    "substituir": r"\b(?:substitu\w*|sobrescrev\w*|sobrescrit\w*)\b",
}
_NEGATED = re.compile(r"\b(?:nao|nunca|sem|evitar?|proibido)\b", re.I)


def _fold(text):
    text = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in text if not unicodedata.combining(c))


def warnings(message, steps):
    """Sinaliza risco explícito, sem converter sugestões em ações permitidas."""
    if not isinstance(message, str) or not isinstance(steps, list):
        return []
    lowered = _fold(message)
    if not any(word in lowered for word in ("nao", "sem", "nunca", "proibido")):
        return []
    # Detecta proibições que o usuário escreveu, inclusive verbos separados por vírgula/conjunção.
    clauses = re.findall(r"\b(?:sem|nao|nunca|proibido)\b([^.;\n]{0,90})", lowered)
    forbidden = set()
    for clause in clauses:
        for action, pattern in _ACTIONS.items():
            if re.search(pattern, clause):
                forbidden.add(action)
    notes = []
    for action in sorted(forbidden):
        pattern = _ACTIONS[action]
        for step in steps[:5]:
            if not isinstance(step, str):
                continue
            text = _fold(step)
            for match in re.finditer(pattern, text):
                # Não penaliza etapas explicitamente negativas: "não mover", "sem excluir".
                preceding = text[max(0, match.start() - 28):match.start()]
                if _NEGATED.search(preceding):
                    continue
                notes.append("O plano inclui " + action + ", apesar de restrição explícita do pedido.")
                break
            if notes and notes[-1].startswith("O plano inclui " + action):
                break
    return notes


def required_stage_warnings(message, steps):
    """Só checa 'deploy' explicitamente exigido; cobertura semântica continua revisão humana."""
    if not isinstance(message, str) or not isinstance(steps, list):
        return []
    msg = _fold(message)
    if not re.search(r"\b(?:deploy|publicac\w*|colocar? (?:o )?(?:site|app) no ar)\b", msg):
        return []
    text = _fold(" ".join(x for x in steps if isinstance(x, str)))
    if not re.search(r"\b(?:deploy|public\w*|implant\w*|colocar? (?:o )?(?:site|app) no ar)\b", text):
        return ["O pedido exige deploy/publicação, mas essa etapa não aparece no plano."]
    return []
