"""Simulações multiturmo do Lab: respostas reais do Ollama, sem executar ferramentas.

Cada resposta seguinte recebe o histórico produzido pelo próprio modelo.
Os testes automáticos medem APENAS decisões estruturadas. Qualidade de
conversa e execução real exigem avaliação humana / fluxo end-to-end separado.
"""
import time

from src.agent import conversation, intelligence
from src.tools.registry import list_tools

ENGINES = frozenset(("chat", "semantic"))
MOVES = frozenset(("answer", "clarify", "plan", "continue", "act", "research",
                   "delegate", "reject", "defer"))
# Nomes extras são aceitos apenas quando constarem do contrato real do roteador.
SAFE_MOVES = frozenset(intelligence.MOVES)


def validate_case(case):
    if case.get("mode") != "dialogue" or case.get("engine") not in ENGINES:
        raise ValueError("Cenário de diálogo inválido.")
    turns = case.get("turns")
    if not isinstance(turns, list) or not 2 <= len(turns) <= 8:
        raise ValueError("Cenário precisa de 2 a 8 mensagens.")
    total = 0
    for turn in turns:
        if not isinstance(turn, dict):
            raise ValueError("Turno de diálogo inválido.")
        message = turn.get("message")
        criterion = turn.get("review_criteria")
        if not isinstance(message, str) or not 3 <= len(message.strip()) <= 800:
            raise ValueError("Mensagem de diálogo inválida.")
        if not isinstance(criterion, str) or not 5 <= len(criterion) <= 500:
            raise ValueError("Critério humano obrigatório em cada turno.")
        total += len(message)
        checks = turn.get("checks", {})
        if not isinstance(checks, dict) or set(checks) - {
                "forbid_act", "allowed_moves", "forbidden_tools", "required_tool"}:
            raise ValueError("Verificações de diálogo inválidas.")
        if checks and case["engine"] != "semantic":
            raise ValueError("Verificações automáticas só no roteador estruturado.")
        if "forbid_act" in checks and type(checks["forbid_act"]) is not bool:
            raise ValueError("forbid_act deve ser booleano.")
        allowed = checks.get("allowed_moves")
        moves_valid = isinstance(allowed, list) and all(
            isinstance(x, str) and x in SAFE_MOVES for x in (allowed or []))
        if allowed is not None and (
                not moves_valid or not allowed or len(allowed) > 6
                or len(allowed) != len(set(allowed))):
            raise ValueError("Movimentos esperados inválidos.")
        forbidden = checks.get("forbidden_tools", [])
        if (not isinstance(forbidden, list) or len(forbidden) > 8
                or any(not isinstance(x, str) or not 2 <= len(x) <= 80 for x in forbidden)):
            raise ValueError("Ferramentas proibidas inválidas.")
        required = checks.get("required_tool")
        if required is not None and (
                not isinstance(required, str) or not 2 <= len(required) <= 80):
            raise ValueError("Ferramenta obrigatória inválida.")
        if checks.get("forbid_act") and required:
            raise ValueError("Verificações contraditórias.")
    if total > 4200:
        raise ValueError("Conversa excede 4200 caracteres.")
    if case.get("model") is not None:
        from ops.model_latency import model_identifier
        model_identifier(case["model"])
    if case.get("history") or case.get("expected_exact") or case.get("expected_contains"):
        raise ValueError("Conversa usa histórico real, não histórico ou gabarito artificial.")
    return case


def check_turn(checks, output):
    """Falha de inferência é falha; sem regra verificável = revisão humana."""
    if output.get("status") not in ("answered", "decision_validated"):
        return False
    if not checks:
        return None
    move, tool = output.get("move"), output.get("tool")
    checks_pass = (
        not (checks.get("forbid_act") is True and move == "act")
        and ("allowed_moves" not in checks or move in checks["allowed_moves"])
        and tool not in checks.get("forbidden_tools", [])
        and ("required_tool" not in checks or
             (move == "act" and tool == checks["required_tool"]))
    )
    return bool(checks_pass)


def run_turn(engine, message, history, model, pending):
    """Uma inferência real, zero operações de escrita/leitura por ferramentas."""
    diagnostics = {}
    if engine == "chat":
        reply = conversation.reply(message, history, diagnostics=diagnostics,
                                   **({"model": model} if model else {}))
        return ({"status": "answered" if reply is not None else "no_answer",
                 "reply": reply or "", "move": None, "tool": None,
                 "model": model, "performance": diagnostics.get("chat_ollama", {}),
                 "diagnostics": diagnostics}, pending)
    tools = list_tools(agent_scope="personal")
    decision = intelligence.decide(
        message, history, pending=pending, tools=tools,
        capabilities=[], knowledge="", feedback_examples=[], preferences="",
        paused_goals=[], last_result=None, diagnostics=diagnostics,
        **({"model": model} if model else {}),
    )
    if decision is None:
        return ({"status": "no_valid_decision", "reply": "", "move": None,
                 "tool": None, "model": model,
                 "performance": diagnostics.get("performance", {}),
                 "diagnostics": diagnostics}, pending)
    move = decision["move"]
    updated = pending
    if decision.get("relation") == "switch":
        updated = None
    elif move in ("clarify", "plan", "continue"):
        updated = {"id": "scenario", "goal": decision["goal"],
                   "question": decision.get("question", ""),
                   "steps": decision.get("steps", [])}
    return ({"status": "decision_validated", "reply": decision["reply"],
             "question": decision.get("question", ""), "move": move,
             "tool": decision.get("tool") or None, "relation": decision.get("relation"),
             "model": model, "performance": diagnostics.get("performance", {}),
             "diagnostics": diagnostics,
             "tools_executed": 0}, updated)


def execute(case, model=None, on_turn=None):
    """Yield um registro por mensagem; para ao falhar sem inventar respostas."""
    history, pending = [], None
    failed = False
    engine = case["engine"]
    for index, turn in enumerate(case["turns"], 1):
        start = time.monotonic()
        if failed:
            output = {"status": "skipped_after_failure", "reply": "", "model": model,
                      "tool": None, "move": None, "tools_executed": 0}
        else:
            try:
                output, pending = run_turn(engine, turn["message"], history, model, pending)
            except Exception as error:
                # Evita texto de exceções (caminhos/tokens) nos relatórios.
                output = {"status": "inference_failed", "reply": "", "model": model,
                          "move": None, "tool": None, "tools_executed": 0,
                          "error_type": type(error).__name__}
            if output["status"] not in ("answered", "decision_validated"):
                failed = True
        score = check_turn(turn.get("checks", {}), output)
        item = {"id": case["id"] + "-t" + str(index).zfill(2),
                "conversation_id": case["id"], "turn_index": index,
                "category": case.get("category", "dialogue"),
                "split": case.get("split", "development"),
                "mode": "dialogue", "engine": engine,
                "profile": "assistant", "grader": "dialogue_checks",
                "requested_model": model, "question": turn["message"],
                "history": list(history[-8:]), "review_criteria": turn["review_criteria"],
                "checks": turn.get("checks", {}), "result": output,
                "elapsed_seconds": round(time.monotonic() - start, 3),
                "automatic_pass": score, "format_compliant": None}
        yield item
        if on_turn:
            on_turn(index)
        if not failed:
            history.extend(({"role": "user", "content": turn["message"]},
                            {"role": "assistant", "content": (
                                output["reply"] +
                                (" " + output.get("question", "") if output.get("question") else "")
                            )[:1800]}))
            history = history[-8:]
