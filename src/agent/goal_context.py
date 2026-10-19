"""Memória de trabalho para vários objetivos dentro da mesma conversa.

Não usa palavras-chave de assunto. O modelo propõe se a mensagem refina,
troca ou retoma um objetivo; este módulo valida a transição e a referência.
Não executa ferramentas e não concede autorizações.
"""
import uuid

RELATIONS = {"start", "refine", "switch", "resume"}
MAX_PAUSED = 6
MAX_DECISIONS = 12


class GoalReferenceError(ValueError):
    """O LLM indicou um objetivo que não está armazenado nesta conversa."""


def _snapshot(state, status="paused"):
    return {
        "id": state["goal_id"],
        "goal": state["goal"][:220],
        "steps": list(state.get("steps", []))[:5],
        "acceptance": list(state.get("acceptance", []))[:4],
        "question": state.get("question", "")[:220],
        "status": status,
    }


def _archived(state):
    entries = state.get("paused_goals", [])
    if not isinstance(entries, list):
        return []
    return [
        entry for entry in entries[-MAX_PAUSED:]
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        and isinstance(entry.get("goal"), str)
        and entry.get("status") in ("paused", "abandoned")
    ]


def _decisions(state, kind, goal, identifier):
    history = state.get("goal_decisions", [])
    if not isinstance(history, list):
        history = []
    return (history + [{
        "kind": kind, "goal_id": identifier, "summary": goal[:220],
    }])[-MAX_DECISIONS:]


def pending_context(state):
    """Extrai somente campos seguros e limitados para a decisão do LLM."""
    if state.get("phase") != "goal":
        return None
    return {
        "id": state.get("goal_id"),
        "goal": state.get("goal", ""),
        "steps": state.get("steps", [])[:5],
        "acceptance": state.get("acceptance", [])[:4],
        "question": state.get("question", ""),
    }


def paused_context(state):
    return [{"id": x["id"], "goal": x["goal"], "status": x["status"]}
            for x in _archived(state)]


def apply_plan(state, decision):
    """Cria/continua/troca/retoma; não aceita IDs inventados pelo modelo."""
    relation = decision.get("relation")
    if relation not in RELATIONS:
        relation = "refine" if state.get("phase") == "goal" else "start"
    paused = _archived(state)
    active = state.get("phase") == "goal" and isinstance(state.get("goal_id"), str)
    if relation == "resume":
        reference = decision.get("resume_goal_id")
        matches = [entry for entry in paused if entry["id"] == reference
                   and entry["status"] == "paused"]
        if not matches:
            raise GoalReferenceError("Não encontrei esse objetivo anterior nesta conversa.")
        selected = matches[0]
        paused = [entry for entry in paused if entry["id"] != reference]
        if active:
            paused.append(_snapshot(state))
        identifier = selected["id"]
        goal = selected["goal"]
        steps = decision["steps"] or selected["steps"]
        acceptance = decision["acceptance"] or selected["acceptance"]
        question = decision["question"] or selected["question"]
    elif active and relation == "refine":
        identifier = state["goal_id"]
        goal = decision["goal"]
        steps = decision["steps"] or state.get("steps", [])
        acceptance = decision["acceptance"] or state.get("acceptance", [])
        question = decision["question"]
    else:
        if active:
            paused.append(_snapshot(state))
        identifier = uuid.uuid4().hex
        goal, steps = decision["goal"], decision["steps"]
        acceptance, question = decision["acceptance"], decision["question"]
        relation = "switch" if active else "start"
    return {
        "phase": "goal", "goal_id": identifier,
        "goal": goal, "steps": steps[:5], "acceptance": acceptance[:4],
        "question": question,
        "paused_goals": paused[-MAX_PAUSED:],
        "goal_decisions": _decisions(state, relation, goal, identifier),
    }


def abandon_active(state):
    """Cancelar não apaga histórico nem permite que um plano volte sozinho."""
    if state.get("phase") != "goal" or not state.get("goal_id"):
        return {"phase": "idle", "paused_goals": _archived(state),
                "goal_decisions": state.get("goal_decisions", [])[-MAX_DECISIONS:]}
    archived = (_archived(state) + [_snapshot(state, "abandoned")])[-MAX_PAUSED:]
    return {
        "phase": "idle", "paused_goals": archived,
        "goal_decisions": _decisions(state, "abandon", state["goal"], state["goal_id"]),
    }
