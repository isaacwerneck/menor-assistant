"""Laboratório local: cenários inéditos, avaliação e métricas reproduzíveis.

Não treina nem altera o modelo; mede comportamento para saber se ficou melhor.
"""
import argparse
import json
from dataclasses import dataclass

from src.agent.intelligence import decide


@dataclass(frozen=True)
class Case:
    name: str
    prompt: str
    acceptable: tuple[str, ...]
    previous_goal: str = ""


CASES = (
    Case("musica", "Quero um sistema local que componha música instrumental.", ("plan", "clarify")),
    Case("robo", "Vamos construir um robô que organize peças da bancada.", ("plan", "clarify")),
    Case("jogo", "Tenho uma ideia de jogo multiplayer, como começamos?", ("plan", "clarify", "answer")),
    Case("programa", "Crie um conversor de CSV para JSON com testes.", ("act", "plan", "clarify")),
    Case("ambiguidade", "Quero resolver aquele negócio, entendeu?", ("clarify",)),
    Case("duvida", "Qual a diferença entre JSON e CSV?", ("answer",)),
    Case("arte", "Quero criar capas para meus álbuns com um modelo local.", ("plan", "clarify")),
    Case("casa", "Me ajuda a planejar uma horta automatizada.", ("plan", "clarify")),
    Case("continuidade", "Preciso que funcione sem internet.", ("continue", "plan", "clarify"),
         "Construir um sistema local para criar música"),
    Case("revisao", "A solução anterior deu erro. Como podemos investigar?", ("plan", "clarify", "answer")),
    Case("segredos", "Pesquise minha senha do servidor na internet.", ("answer", "clarify")),
    Case("explicacao", "Como funciona um motor de busca semântico?", ("answer",)),
)


def evaluate(decider=decide, cases=CASES):
    """Confere o próximo movimento e retorna apenas métricas, sem textos privados."""
    results = []
    for case in cases:
        pending = {"goal": case.previous_goal, "steps": ["Estudar opções"], "question": "Qual método?"} \
            if case.previous_goal else None
        try:
            answer = decider(case.prompt, [], pending=pending, capabilities=[])
        except (ValueError, TypeError, OSError):
            answer = None
        move = answer.get("move") if isinstance(answer, dict) else None
        results.append({
            "case": case.name, "passed": move in case.acceptable, "move": move or "unavailable",
        })
    total = len(results)
    passed = sum(item["passed"] for item in results)
    return {
        "cases": total, "passed": passed,
        "score": round(passed / total, 3) if total else 0,
        "details": results,
        "limits": "Heuristic intent evaluation; no tool execution or factual correctness measured.",
    }


@dataclass(frozen=True)
class ContinuityCase:
    name: str
    prompt: str
    active_goal: str
    expected_move: tuple[str, ...]
    expected_relation: str
    paused_goal: str = ""


CONTINUITY_CASES = (
    ContinuityCase(
        "trocar-documentos-musica", "Agora quero começar um projeto de música",
        "Ler e analisar PDFs", ("plan", "continue", "clarify"), "switch",
    ),
    ContinuityCase(
        "refinar-mesmo-projeto", "Também preciso que as músicas sejam instrumentais",
        "Criar músicas locais", ("continue", "plan", "clarify"), "refine",
    ),
    ContinuityCase(
        "retomar-documentos", "Voltemos ao projeto de leitura de PDFs",
        "Criar músicas locais", ("continue", "plan", "clarify"), "resume",
        "Ler e analisar PDFs",
    ),
    ContinuityCase(
        "novo-assunto-robos", "Quero planejar um robô de limpeza doméstica",
        "Criar música", ("plan", "clarify"), "switch",
    ),
)


def evaluate_continuity(decider=decide, cases=CONTINUITY_CASES):
    """Mede também relação entre mensagens, não apenas classificação de intenção."""
    checks = []
    for case in cases:
        paused = ([{"id": "a" * 32, "goal": case.paused_goal, "status": "paused"}]
                  if case.paused_goal else [])
        try:
            result = decider(
                case.prompt, [], pending={
                    "id": "b" * 32, "goal": case.active_goal,
                    "steps": ["Planejar etapas"], "acceptance": ["Entregar prova verificável"],
                    "question": "",
                }, paused_goals=paused, capabilities=[],
            )
        except (ValueError, TypeError, OSError):
            result = None
        move = result.get("move") if isinstance(result, dict) else None
        relation = result.get("relation") if isinstance(result, dict) else None
        reference_ok = (
            not case.paused_goal or
            result is not None and result.get("resume_goal_id") == "a" * 32
        )
        passed = (move in case.expected_move and relation == case.expected_relation
                  and (reference_ok if case.expected_relation == "resume" else True))
        checks.append({"case": case.name, "passed": passed,
                       "move": move or "unavailable", "relation": relation or "unspecified"})
    count = len(checks)
    return {
        "cases": count, "passed": sum(x["passed"] for x in checks),
        "score": round(sum(x["passed"] for x in checks) / count, 3) if count else 0,
        "details": checks,
        "limits": "Heuristic evaluation of topic relation, not actual tool success.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Avaliar decisões do Menor no Ollama local")
    parser.add_argument("--live", action="store_true", help="Executa modelo local contra cenários")
    parser.add_argument("--continuity", action="store_true",
                        help="Avalia troca, refinamento e retomada de objetivos")
    parser.add_argument("--dialogues", action="store_true",
                        help="Avalia diálogos multidomínio e respostas factuais focais")
    args = parser.parse_args(argv)
    if not args.live:
        print("Passe --live para avaliar o modelo local; nada foi executado.")
        return 0
    if args.dialogues:
        from src.agent.dialogue_bench import evaluate_dialogues
        result = evaluate_dialogues()
    else:
        result = evaluate_continuity() if args.continuity else evaluate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["score"] >= 0.6 else 1


if __name__ == "__main__":
    raise SystemExit(main())
