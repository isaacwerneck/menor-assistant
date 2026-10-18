"""Resolve uma pergunta de memória por conversa, sem depender de botões.

Toda resposta é interpretada por modelo e validada no backend.
Uma resposta incerta não grava dados.
"""
import json
import logging
import os

import requests

from src.agent.short_replies import simple_answer

LOGGER = logging.getLogger(__name__)
MODEL = os.environ.get("OLLAMA_ROUTER_MODEL", os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")

PROMPT = """Você resolve uma pergunta que o assistente já fez sobre guardar uma informação.
A resposta atual do usuário é a resposta para essa pergunta, NÃO um comando novo.
Use a proposta, a pergunta, e a resposta para entender se o usuário aceitou, recusou,
escolheu a pasta ou mudou de assunto. Nunca invente consentimento.
Retorne APENAS JSON no formato:
{"decision":"save|ask|cancel|chat","target":"preference|knowledge|project|tool|none",
 "note_kind":"none|decision|task|log","confidence":0.0,"question":"..."}
- save: o usuário confirmou claramente guardar aquela informação e escolheu categoria;
  "sim" só autoriza usar a categoria sugerida se ela for inequívoca na pergunta.
- ask: usuário quer salvar mas ainda não decidiu onde, ou a resposta é ambígua.
- cancel: recusou salvar, como "não, deixa".
- chat: mudou de assunto; não grave nada.
- target preference é preferência de atendimento; knowledge é aprendizado; project
  é ideia de projeto; tool é proposta de ferramenta.
- Com projeto ativo, se o usuário quiser especificamente registrar nele, selecione
  target project e note_kind decision, task ou log. Se faltar tipo, pergunte.
- Sem projeto ativo, note_kind deve ser none.
- Não escolha save para dúvidas, segredos/senhas ou instruções para contornar segurança.
- Nunca diga que criou ferramenta ou executou código. A única ação é salvar Markdown.
- Confiança >=0.95 apenas quando confirmação e destino são muito claros.
"""


def resolve(original, answer, suggested_target="none", project=None, question="", history=None):
    """Classifica resposta à pergunta anterior. Sem LLM, nunca executa uma gravação."""
    fallback = {"decision": "ask", "target": "none", "note_kind": "none",
                "question": "Quer que eu guarde isso? Em conhecimentos, preferências, projetos ou ferramentas?"}
    if not original or not answer or len(original) > 280 or len(answer) > 8000:
        return fallback
    if suggested_target not in ("none", "preference", "knowledge", "project", "tool"):
        return fallback
    # Confirmações curtas devem funcionar sem aguardar outra inferência do Qwen.
    direct = simple_answer(answer, suggested_target, question, project)
    if direct is not None:
        return direct

    conversation = [
        {"role": m["role"], "content": m["content"][:1000]}
        for m in (history or [])[-4:]
        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
        and isinstance(m.get("content"), str)
    ]
    context = {
        "original": original,
        "question": question[:180],
        "suggested_target": suggested_target,
        "project": project or None,
        "answer": answer,
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": PROMPT},
            *conversation,
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0, "num_predict": 180},
    }
    try:
        with requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=(4, 45)) as response:
            response.raise_for_status()
            result = json.loads(response.json()["message"]["content"])
    except (requests.RequestException, TypeError, KeyError, ValueError) as error:
        LOGGER.warning("Resolução de intenção indisponível: %s", type(error).__name__)
        return fallback
    if not isinstance(result, dict):
        return fallback
    decision = result.get("decision")
    target = result.get("target")
    kind = result.get("note_kind", "none")
    confidence = result.get("confidence", 0)
    question_text = result.get("question", "")
    if (decision not in ("save", "ask", "cancel", "chat")
            or target not in ("none", "preference", "knowledge", "project", "tool")
            or kind not in ("none", "decision", "task", "log")
            or isinstance(confidence, bool)
            or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1
            or not isinstance(question_text, str)):
        return fallback
    if decision in ("cancel", "chat"):
        return {"decision": decision, "target": "none", "note_kind": "none", "question": ""}
    if (decision != "save" or confidence < 0.95 or target == "none"
            or (kind != "none" and (target != "project" or not project))):
        return {
            "decision": "ask", "target": target, "note_kind": "none",
            "question": question_text[:180] or fallback["question"],
        }
    return {"decision": "save", "target": target, "note_kind": kind, "question": ""}
