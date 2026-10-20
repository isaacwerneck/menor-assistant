"""Budget de saída proporcional ao formato *explícito*, nunca à permissão.

O budget não substitui o raciocinador ou o executor. Não analisa comandos em
texto recuperado: somente o pedido atual, e é opt-in nos perfis novos do Lab.
"""
import re
import unicodedata


def _plain(text):
    value = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


def output_budget(message, *, chat=False):
    """Limita tokens para evitar 256 tokens em resposta declaradamente curta.

    Preserva espaço para pedidos longos, código, tabelas e tarefas detalhadas.
    A diferença de output budget deve ser registrada em comparações A/B.
    """
    if not isinstance(message, str):
        return 256 if not chat else 384
    text = _plain(message)
    explicit_short = (
        r"\b(?:so|somente|apenas)\s+(?:(?:o|a|um|uma)\s+)?"
        r"(?:sim\s+ou\s+nao|sim\/nao|numero|inteiro|comando|palavra|"
        r"nome\s+d[oa]\s+campo|resposta\s+curta)\b"
        r"|\bresponda\s+s[oó]\s+(?:sim|nao|com|o|a)\b"
        r"|\b(?:responda\s+)?(?:sim|nao)\s+ou\s+(?:nao|sim)\b"
    )
    if re.search(explicit_short, text):
        return 56
    if re.search(r"\b(?:em|ate|no\s+maximo)\s+(?:uma|duas|tres|1|2|3)"
                 r"\s+(?:frases?|linhas?)\b", text):
        return 96
    detailed = r"\b(?:detalhad[oa]s?|profund[oa]|passo\s+a\s+passo|exaustiv[oa]|completo|" \
               r"codigo\s+completo|todas?\s+as\s+etapas|roteiro|plano\s+completo)\b"
    if re.search(detailed, text):
        return 512 if chat else 256
    # Chat cotidiano precisa ser direto, mas nunca cortar tarefa profunda a 56 tokens.
    return 256 if chat else 176
