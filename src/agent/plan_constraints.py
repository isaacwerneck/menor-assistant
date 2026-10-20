"""Conservative review of explicit plan restrictions; never an execution permission.

A warning identifies a possible problem, not a proof that remaining steps are safe.
Review is deterministic and does not call Ollama, change tools, or grant approvals.
"""
import re
import unicodedata


_ACTIONS = {
    "apagar": r"\b(?:apagar|apagu(?:e|em)|apagando|excluir|exclu(?:a|am|ir)|deletar|delet(?:e|em)|remover|remov(?:a|am))\b",
    "mover": r"\b(?:mover|mov(?:a|am|endo)|transferir|transfir(?:a|am)|deslocar|desloqu(?:e|em))\b",
    "substituir": r"\b(?:substituir|substitu(?:a|am|indo)|sobrescrever|sobrescrev(?:a|am))\b",
    "alterar": r"\b(?:alterar|alter(?:e|em|ando)|modificar|modifiqu(?:e|em)|editar|edit(?:e|em|ando))\b",
}
_NEGATIONS = r"\b(?:nao|sem|nunca|evitar|evite|proibido|proibida)\b"
_BREAKS = re.compile(r"[.;!?\n]|\b(?:mas|porem|entretanto)\b")
_ALL_MUTATIONS = re.compile(
    r"\b(?:sem|nao|nunca)\s+(?:mexer|alterar|modificar|editar)\s+"
    r"(?:em\s+)?(?:nada|nenhum(?:a|s)?\s+(?:arquivo|documento|dado)s?)\b"
    r"|\b(?:apenas|somente)\s+(?:leitura|analis[ea]|inventario)\b"
)
_REQUIRED = (
    ("backup", r"\b(?:backup|copias? de seguranca)\b",
     r"\b(?:backup|copias? de seguranca|snapshot)\b"),
    ("testes", r"\b(?:testes?|testar)\b", r"\b(?:testes?|testar|validar)\b"),
    ("rollback", r"\b(?:rollback|reversao|reverter)\b",
     r"\b(?:rollback|reversao|reverter|restaurar)\b"),
    ("autorização", r"\b(?:autorizac\w*|aprovac\w*|consentimento)\b",
     r"\b(?:autorizac\w*|aprovac\w*|aprovar|confirmar\s+com\s+o\s+usuario)\b"),
    ("deploy", r"\b(?:deploy|publicar|publicac\w*|colocar\s+(?:o\s+)?(?:site|app)\s+no\s+ar)\b",
     r"\b(?:deploy|publicar|publicac\w*|implantar|colocar\s+(?:o\s+)?(?:site|app)\s+no\s+ar)\b"),
    ("acessibilidade", r"\bacessibilidade\b",
     r"\b(?:acessibilidade|acessivel|wcag)\b"),
)


def _fold(value):
    folded = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in folded if not unicodedata.combining(char))


def _explicitly_forbidden(message):
    """Extract only clear restrictions; ambiguity remains for human/model review."""
    forbidden = set()
    if _ALL_MUTATIONS.search(message):
        forbidden.update(_ACTIONS)
    for clause in _BREAKS.split(message):
        for negative in re.finditer(_NEGATIONS, clause):
            # A short local window, never a whole document or a later contrasting sentence.
            phrase = clause[negative.end():negative.end() + 100]
            for action, expression in _ACTIONS.items():
                if re.search(expression, phrase):
                    forbidden.add(action)
    return forbidden


def _negative_use_of_verb(text, match):
    """Avoid flagging 'não apagar' as if it were an instruction to delete."""
    before = text[max(0, match.start() - 90):match.start()]
    before = re.split(r"[.;:\n]", before)[-1]
    if re.search(r"\b(?:nem|nao|nunca|sem|evitar|evite|proibido|proibida)\s+$", before):
        return True
    # Preserve negation in short enumerations: 'não apagar, substituir ou mover'.
    for negative in re.finditer(_NEGATIONS, before):
        tail = before[negative.end():]
        for expression in _ACTIONS.values():
            tail = re.sub(expression, " ", tail)
        tail = re.sub(r"\b(?:e|ou|nem|nenhum|nenhuma|nada|arquivo|arquivos)\b", " ", tail)
        if not re.sub(r"[\s,/-]", "", tail):
            return True
    return False


def warnings(message, steps):
    """Warn about forbidden file mutations explicitly described as plan actions."""
    if not isinstance(message, str) or not isinstance(steps, list):
        return []
    forbidden = _explicitly_forbidden(_fold(message))
    if not forbidden:
        return []
    notes = []
    for action in sorted(forbidden):
        for step in steps[:5]:
            if not isinstance(step, str):
                continue
            normalized = _fold(step)
            if any(not _negative_use_of_verb(normalized, match)
                   for match in re.finditer(_ACTIONS[action], normalized)):
                notes.append("O plano inclui " + action + ", apesar de restrição explícita do pedido.")
                break
    return notes


def required_stage_warnings(message, steps):
    """Verify clearly requested stages appear in steps, not only in acceptance text.

    No stage is marked as verified; synonyms and ordering still need semantic review.
    """
    if not isinstance(message, str) or not isinstance(steps, list):
        return []
    message = _fold(message)
    planned = [_fold(step) for step in steps[:5] if isinstance(step, str)]
    missing = []
    for label, requirement, stage in _REQUIRED:
        for mention in re.finditer(requirement, message):
            prefix = message[max(0, mention.start() - 25):mention.start()]
            if re.search(r"\b(?:sem|nao|nunca)\s+(?:(?:\w+)\s+){0,2}$", prefix):
                continue
            if not any(re.search(stage, item) and not _negative_use_of_verb(item, match)
                       for item in planned for match in re.finditer(stage, item)):
                missing.append(label)
            break
    return [
        "O pedido exige " + label + ", mas essa etapa não aparece no plano."
        for label in missing
    ]
