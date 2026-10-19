"""Interpreta aprovação explícita com contexto de ação já planejada.

Somente utilizado quando o servidor tem uma ação específica aguardando
consentimento. Dúvidas, hipóteses e frases ambíguas nunca concedem permissão.
"""
import re
import unicodedata


def _normal(text):
    text = unicodedata.normalize("NFKD", text.casefold().strip())
    return re.sub(r"\s+", " ", "".join(c for c in text if not unicodedata.combining(c)))


YES = re.compile(
    r"^(?:sim+|simm+|eu aprovo|aprovado|aprovo|confirmo|eu confirmo|"
    r"pode|pode sim|pode comecar|pode instalar|pode executar|"
    r"bora|bora la|vamos|vamos la|claro|isso|fechou|"
    r"autorizo|eu autorizo|esta autorizado|ta autorizado|"
    r"vai em frente|manda ver|mete marcha)$"
)
NO = re.compile(
    r"^(?:nao|nao pode|nao autorizo|nao aprovo|reprovo|"
    r"deixa|deixa pra la|cancela|cancelar|nao precisa|para|pare)$"
)
# Uma ordem explícita para iniciar a instalação é autorização somente se
# a missão estiver esperando esse passo exato e um plano já foi apresentado.
START = re.compile(
    r"\b(?:instal[ae]|instalar|baixa(?:r)?|baixe|faz o download|"
    r"pode prosseguir|pode seguir|pode fazer|executa|execute|"
    r"comeca|comece|inicia|inicie)\b"
)
SUBJECT = re.compile(
    r"\b(?:modelo|subagente|ferramenta|instalacao|implementacao|"
    r"plano|download|etapas|projeto)\b"
)
DIRECTIVE = re.compile(r"^(?:mete marcha|pode |eu autorizo|autorizo|vai em frente|manda ver)")


def decision(message):
    """Retorna 'approve', 'reject' ou 'question'; nunca decide por LLM."""
    if not isinstance(message, str) or not 1 <= len(message.strip()) <= 1200:
        return "question"
    text = _normal(message)
    cleaned = text.strip(" \t.,!…")
    # Interrogações não são uma autorização.
    if "?" in text or re.search(r"\b(?:se|talvez|sera que|acho que|quando|como)\b", text[:35]):
        return "question"
    if NO.fullmatch(cleaned):
        return "reject"
    if YES.fullmatch(cleaned):
        return "approve"
    if DIRECTIVE.match(cleaned) and START.search(cleaned) and SUBJECT.search(cleaned):
        return "approve"
    return "question"
