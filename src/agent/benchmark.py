"""Benchmark isolado de interpretação e custo do revisor local.

Executa SOMENTE inferência do planejador/revisor; nenhuma ferramenta do catálogo.
Resultados agregados não incluem mensagens, respostas, contexto ou críticas.
"""
import argparse
import json
import os
from dataclasses import dataclass
from statistics import median
from time import perf_counter

from src.agent.intelligence import decide
from src.agent.plan_review import review


ACTIVE_ID = "b" * 32
PAUSED_ID = "a" * 32


@dataclass(frozen=True)
class Scenario:
    name: str
    message: str
    moves: tuple[str, ...]
    relation: str = ""
    active: str = ""
    paused: str = ""
    question: bool = False


# Frases de avaliação fixas; não usá-las como exemplos no prompt de produção.
SCENARIOS = (
    Scenario("pergunta-coloquial", "Qual é a diferença entre CSV e JSON, mano?", ("answer",)),
    Scenario("referencia-vaga", "Dá um jeito naquele negócio de ontem.", ("clarify",), question=True),
    Scenario("documentos", "Quero comparar números de várias planilhas e citar cada aba.",
             ("plan", "clarify")),
    Scenario("inspecao-visual", "Preciso de uma forma de descrever fotos recebidas no chat.",
             ("plan", "clarify")),
    Scenario("musica", "Quero um sistema local que monte trilhas instrumentais.",
             ("plan", "clarify")),
    Scenario("codigo", "Desenvolva um validador de arquivos TOML com testes de regressão.",
             ("plan", "clarify", "act")),
    Scenario("sem-comprovante", "Você já publicou o código em produção?",
             ("answer", "clarify")),
    Scenario("interrupcao", "O processo caiu depois de executar a cobrança; refaça já.",
             ("clarify", "plan", "answer")),
    Scenario("mudanca-de-dominio", "Agora quero planejar um álbum de música eletrônica.",
             ("plan", "continue", "clarify"), relation="switch",
             active="Extrair cláusulas de contratos PDF"),
    Scenario("mesmo-objetivo", "As faixas também têm que funcionar sem internet.",
             ("plan", "continue", "clarify"), relation="refine",
             active="Produzir trilhas musicais locais"),
    Scenario("retomar-objetivo", "Volta pro nosso plano de análise de notas fiscais.",
             ("plan", "continue", "clarify"), relation="resume",
             active="Criar música local", paused="Analisar notas fiscais digitalizadas"),
    Scenario("duvida-incidental", "Rapidinho, o que é uma API REST?",
             ("answer",), active="Criar sintetizador de música local"),
)


def _context(case):
    pending = ({"id": ACTIVE_ID, "goal": case.active, "steps": ["Validar requisitos"],
                "acceptance": ["Demonstrar resultado verificável"], "question": ""}
               if case.active else None)
    paused = ([{"id": PAUSED_ID, "goal": case.paused, "status": "paused"}]
              if case.paused else [])
    return pending, paused


def _grade(case, result):
    if not isinstance(result, dict):
        return {"move": "unavailable", "relation": "unspecified", "passed": False,
                "available": False}
    move = result.get("move", "unavailable")
    relation = result.get("relation", "unspecified")
    reference_ok = (case.relation != "resume" or result.get("resume_goal_id") == PAUSED_ID)
    question_ok = not case.question or bool(str(result.get("question", "")).strip())
    # Nenhuma ferramenta foi anunciada pelo benchmark; nomes são inválidos aqui.
    tool_ok = not result.get("tool") and not result.get("arguments")
    return {"move": move, "relation": relation or "unspecified",
            "passed": (move in case.moves and (not case.relation or relation == case.relation)
                       and reference_ok and question_ok and tool_ok), "available": True}


def _invoke(decider, case, pending, paused, review_issues=None):
    kwargs = {"pending": pending, "paused_goals": paused, "capabilities": [], "tools": []}
    if review_issues is not None:
        kwargs["review_issues"] = review_issues
    try:
        return decider(case.message, [], **kwargs)
    except (ValueError, TypeError, OSError):
        return None


def _percent(numerator, denominator):
    return round(numerator / denominator, 3) if denominator else None


def _summary(rows, column):
    eligible = [row[column] for row in rows if row[column]["available"]]
    return {"cases": len(rows), "available": len(eligible),
            "unavailable": len(rows) - len(eligible),
            "passed": sum(row["passed"] for row in eligible),
            "score": _percent(sum(row["passed"] for row in eligible), len(eligible)),
            "coverage": _percent(len(eligible), len(rows))}


def benchmark(decider=decide, reviewer=review, cases=SCENARIOS,
              compare_review=False, clock=perf_counter):
    """Compara o mesmo rascunho antes/depois de uma crítica, sem efeitos externos.

    Não mede qualidade semântica nem runtime real do agente; pontuação é heurística.
    """
    rows = []
    for case in cases:
        pending, paused = _context(case)
        started = clock()
        initial = _invoke(decider, case, pending, paused)
        baseline_ms = max(0.0, (clock() - started) * 1000)
        base = _grade(case, initial)
        revised = initial
        verdict = "skipped"
        review_ms = 0.0
        if compare_review and isinstance(initial, dict) and initial.get("move") in ("plan", "continue"):
            started = clock()
            try:
                opinion = reviewer(case.message, initial, pending=pending)
            except (ValueError, TypeError, OSError):
                opinion = None
            verdict = opinion.get("verdict", "unavailable") if isinstance(opinion, dict) else "unavailable"
            if verdict == "clarify" and isinstance(opinion.get("question"), str) and opinion["question"].strip():
                revised = {**initial, "move": "clarify", "question": opinion["question"]}
            elif verdict == "revise" and isinstance(opinion.get("issues"), list) and opinion["issues"]:
                candidate = _invoke(decider, case, pending, paused, opinion["issues"])
                if isinstance(candidate, dict) and candidate.get("move") in ("plan", "continue", "clarify"):
                    # Igual ao runner: crítico não troca objetivo nem permissão.
                    revised = {**candidate, "relation": initial.get("relation"),
                               "resume_goal_id": initial.get("resume_goal_id", "")}
                    verdict = "revised_unverified"
            review_ms = max(0.0, (clock() - started) * 1000)
        rows.append({"case": case.name, "baseline": base,
                     "reviewed": _grade(case, revised) if compare_review else None,
                     "baseline_ms": round(baseline_ms, 2),
                     "review_extra_ms": round(review_ms, 2), "review_status": verdict})
    result = {
        "mode": "ollama_inference" if decider is decide else "injected_decider",
        "compare_review": compare_review,
        "models": {"planner": os.environ.get("MENOR_REASONING_MODEL")
                   or os.environ.get("OLLAMA_ROUTER_MODEL")
                   or os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b"),
                   "reviewer": (os.environ.get("MENOR_PLAN_REVIEW_MODEL")
                                or os.environ.get("MENOR_REASONING_MODEL")
                                or os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b"))
                   if compare_review else None},
        "baseline": _summary(rows, "baseline"),
        "reviewed": _summary(rows, "reviewed") if compare_review else None,
        "latency_ms": {"baseline_total": round(sum(r["baseline_ms"] for r in rows), 2),
                       "baseline_p50": round(median([r["baseline_ms"] for r in rows]), 2) if rows else None,
                       "review_extra_total": round(sum(r["review_extra_ms"] for r in rows), 2),
                       "review_extra_p50": round(median([r["review_extra_ms"] for r in rows]), 2)
                       if compare_review and rows else None},
        "details": rows,
        "limits": ("Heuristic intent/relation checks only; no task execution, tool authorization, "
                   "semantic truth, RAM profiling, or real-hardware proof from mocks."),
    }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Benchmark isolado do Qwen; nunca executa tools")
    parser.add_argument("--live", action="store_true", help="Executa inferência no Ollama local")
    parser.add_argument("--compare-review", action="store_true",
                        help="Mede revisão e no máximo uma reformulação por cenário")
    args = parser.parse_args(argv)
    if not args.live:
        print("Sem --live: nenhuma inferência executada. Use unittest para testar mocks.")
        return 0
    result = benchmark(compare_review=args.compare_review)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["baseline"]["available"] == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
