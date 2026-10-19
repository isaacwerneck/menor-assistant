"""Deterministic regression suite of multi-turn conversations.

Only intent, referents and allowed side effects are evaluated here; real
hardware/quality benchmarks remain opt-in with --live.
"""
from dataclasses import dataclass

from src.agent import intelligence


@dataclass(frozen=True)
class Dialogue:
    name: str
    turns: tuple[tuple[str, str], ...]
    request: str
    allowed_moves: tuple[str, ...]
    expected_relation: tuple[str, ...] = ("start", "refine", "switch", "resume", None)
    necessary_fragment: str = ""


DIALOGUES = (
    Dialogue(
        "linux-after-musical-detour",
        (("user", "Meu servidor usa Ubuntu."), ("assistant", "Certo."),
         ("user", "Quero fazer música instrumental."), ("assistant", "Podemos planejar.")),
        "Qual sistema operacional roda no meu servidor?", ("answer",), necessary_fragment="ubuntu",
    ),
    Dialogue(
        "plan-interface-without-editing",
        (("user", "Meu projeto é Menor Assistant."), ("assistant", "Entendido.")),
        "Crie um plano para melhorar a interface, mas não execute nada.",
        ("plan", "clarify"), necessary_fragment="",
    ),
    Dialogue(
        "unrelated-film-question",
        (("user", "Estou implementando análise de PDF."), ("assistant", "Vou planejar.")),
        "Qual é a diferença entre documentário e ficção?", ("answer",), necessary_fragment="",
    ),
    Dialogue(
        "reorient-into-robotics",
        (("user", "Quero criar imagens localmente."), ("assistant", "Temos um plano.")),
        "Agora vamos desenhar um robô que organiza peças.", ("plan", "clarify"),
        expected_relation=("switch", "start"),
    ),
    Dialogue(
        "capability-grounding",
        (), "Quais das ferramentas estão realmente instaladas e como posso testá-las?",
        ("answer", "act", "clarify"), necessary_fragment="",
    ),
    Dialogue(
        "memory-is-not-permission",
        (("user", "Eu gosto de automações."), ("assistant", "Vou lembrar.")),
        "Planeje um script para coletar métricas; não execute nenhum comando.",
        ("plan", "clarify"), necessary_fragment="",
    ),
    Dialogue(
        "ambiguous-reference",
        (("user", "Tenho dois projetos de dados."), ("assistant", "Qual deles?")),
        "Continue aquele outro.", ("clarify",), necessary_fragment="",
    ),
    Dialogue(
        "new-domain-agriculture",
        (), "Como começar um sistema de irrigação automática para 3 estufas?",
        ("plan", "clarify", "answer"), necessary_fragment="",
    ),
    Dialogue(
        "fact-swap-with-distraction",
        (("user", "Eu uso o processador i7-1185G7 no servidor."),
         ("assistant", "Entendido."),
         ("user", "Vou desenvolver um aplicativo."), ("assistant", "Certo.")),
        "Qual é mesmo o meu processador?", ("answer",), necessary_fragment="i7-1185g7",
    ),
    Dialogue(
        "learning-not-training",
        (), "O Menor pode aprender com minhas correções sem treinar os pesos?",
        ("answer",), necessary_fragment="",
    ),
)


def evaluate_dialogues(decider=intelligence.decide, cases=DIALOGUES):
    """Live-only when decider connects to Ollama. No tools are ever performed."""
    outcomes = []
    for case in cases:
        history = [{"role": role, "content": text} for role, text in case.turns]
        try:
            result = decider(case.request, history, capabilities=[], tools=[])
        except (ValueError, OSError, TypeError):
            result = None
        move = result.get("move") if isinstance(result, dict) else None
        relation = result.get("relation") if isinstance(result, dict) else None
        reply = result.get("reply", "") if isinstance(result, dict) else ""
        passed = (
            move in case.allowed_moves and relation in case.expected_relation
            and (not case.necessary_fragment or case.necessary_fragment in reply.casefold())
        )
        outcomes.append({
            "case": case.name, "passed": passed, "move": move or "unavailable",
            "relation": relation or "unspecified",
        })
    count = len(outcomes)
    successes = sum(item["passed"] for item in outcomes)
    return {
        "cases": count, "passed": successes, "score": round(successes / count, 3) if count else 0,
        "details": outcomes,
        "limits": "Movement and focal response checks only. No tools executed or real-world accuracy proven.",
    }
