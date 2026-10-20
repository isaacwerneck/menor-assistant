"""Publica apenas resumos anônimos em branch isolada (nunca respostas completas)."""
import base64
import json
import os
import requests

API = "https://api.github.com/repos/isaacwerneck/menor-assistant"
BRANCH = "lab-reports"


class GitHubPublishRejected(RuntimeError):
    """Erro do GitHub apresentado sem incluir token, corpo do relatório ou resposta arbitrária."""


def describe_github_rejection(response):
    """Classifica erros por indicadores controlados; nunca retorna mensagens externas livres."""
    try:
        payload = response.json()
    except (ValueError, TypeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    message = payload.get("message", "")
    message = message.casefold() if isinstance(message, str) else ""
    if "sha" in message and ("supplied" in message or "required" in message):
        reason = "O GitHub exige o SHA do arquivo existente; confirme se o relatório já está publicado."
    elif "protected branch" in message or "protected" in message and "branch" in message:
        reason = "A branch de relatórios possui restrições que impediram a gravação."
    elif "secret scanning" in message or "push protection" in message:
        reason = "A proteção de segredos do GitHub bloqueou o conteúdo enviado."
    elif "already exists" in message:
        reason = "O caminho do relatório já existe no GitHub."
    elif "large" in message or "size" in message and "limit" in message:
        reason = "O relatório excedeu um limite de tamanho do GitHub."
    elif "spam" in message or "too quickly" in message:
        reason = "O GitHub limitou publicações rápidas."
    else:
        reason = "O GitHub rejeitou a gravação; a causa não foi identificada automaticamente."
    request_id = response.headers.get("X-GitHub-Request-Id", "")
    if not isinstance(request_id, str) or not request_id or not all(
            char.isascii() and (char.isalnum() or char in ":-") for char in request_id[:65]
    ) or len(request_id) > 64:
        request_id = "indisponível"
    return f"{reason} (GitHub HTTP {response.status_code}; referência: {request_id})."


def publish_summary(summary):
    token = os.environ.get("MENOR_LAB_GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("MENOR_LAB_GITHUB_TOKEN ausente.")
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    session = requests.Session()
    session.headers.update(headers)
    ref = session.get(API + "/git/ref/heads/" + BRANCH, timeout=15)
    if ref.status_code == 404:
        main = session.get(API + "/git/ref/heads/main", timeout=15)
        main.raise_for_status()
        created = session.post(API + "/git/refs", json={
            "ref": "refs/heads/" + BRANCH, "sha": main.json()["object"]["sha"]}, timeout=15)
        if created.status_code not in (201, 422):
            created.raise_for_status()
    else:
        ref.raise_for_status()
    path = "lab/reports/" + summary["run_id"] + ".json"
    payload = {"message": "chore(lab): publish anonymous evaluation metrics " + summary["run_id"],
               "content": base64.b64encode(json.dumps(summary, indent=2).encode()).decode(),
               "branch": BRANCH}
    response = session.put(API + "/contents/" + path, json=payload, timeout=20)
    response.raise_for_status()
    return response.json()["content"]["html_url"]


def publish_report(report):
    """Publica relatório completo apenas por ação explícita do proprietário.

    Exige MENOR_LAB_REPORTS_ALLOW_FULL_PUSH=1, além de token GitHub.
    Não publica automaticamente após executar a bateria.
    """
    if os.environ.get("MENOR_LAB_REPORTS_ALLOW_FULL_PUSH") != "1":
        raise RuntimeError("Publicação completa desabilitada no servidor.")
    token = os.environ.get("MENOR_LAB_GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("MENOR_LAB_GITHUB_TOKEN ausente.")
    headers = {"Authorization": "Bearer " + token,
               "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    session = requests.Session()
    session.headers.update(headers)
    ref = session.get(API + "/git/ref/heads/" + BRANCH, timeout=15)
    if ref.status_code == 404:
        main = session.get(API + "/git/ref/heads/main", timeout=15)
        main.raise_for_status()
        created = session.post(API + "/git/refs", json={
            "ref": "refs/heads/" + BRANCH,
            "sha": main.json()["object"]["sha"]}, timeout=15)
        if created.status_code not in (201, 422):
            created.raise_for_status()
    else:
        ref.raise_for_status()
    run_id = report["run_id"]
    path = "lab/reports/full/" + run_id + ".json"
    payload = {
        "message": "chore(lab): publish evaluation report " + run_id,
        "content": base64.b64encode(json.dumps(
            report, ensure_ascii=False, indent=2).encode("utf-8")).decode("ascii"),
        "branch": BRANCH,
    }
    response = session.put(API + "/contents/" + path, json=payload, timeout=30)
    if response.status_code == 422:
        raise GitHubPublishRejected(describe_github_rejection(response))
    response.raise_for_status()
    return response.json()["content"]["html_url"]
