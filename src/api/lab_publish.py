"""Publica resumos opcionais e relatórios completos aprovados em branch isolada."""
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
    errors = payload.get("errors", [])
    if isinstance(errors, list):
        message += " " + " ".join(
            item.get("message", "")[:300].casefold()
            for item in errors[:5]
            if isinstance(item, dict) and isinstance(item.get("message"), str)
        )
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
    if "validation failed" in message and reason.startswith("O GitHub rejeitou"):
        reason = "O GitHub rejeitou um campo da requisição de gravação."
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


class GitHubReportConflict(RuntimeError):
    """Um relatório diferente já ocupa o mesmo caminho; nunca sobrescrever."""


def _existing_report(session, path, expected_content):
    """Consulta a branch exata com o mesmo token antes de publicar novamente.

    None indica caminho ausente; relatório idêntico retorna link, e divergência
    falha sem passar SHA ao PUT (nunca sobrescrever dados publicados).
    """
    response = session.get(API + "/contents/" + path, params={"ref": BRANCH}, timeout=15)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    document = response.json()
    if not isinstance(document, dict) or document.get("type") != "file":
        raise GitHubPublishRejected("O caminho do relatório no GitHub não é um arquivo.")
    raw = document.get("content")
    if not isinstance(raw, str) or document.get("encoding") != "base64":
        raise GitHubPublishRejected("O GitHub não forneceu conteúdo verificável do relatório existente.")
    try:
        existing = base64.b64decode(raw)
    except (ValueError, base64.binascii.Error) as error:
        raise GitHubPublishRejected("O GitHub retornou relatório existente com conteúdo inválido.") from error
    if existing != expected_content:
        raise GitHubReportConflict("Já existe um relatório diferente com este ID no GitHub; não foi sobrescrito.")
    return "https://github.com/isaacwerneck/menor-assistant/blob/" + BRANCH + "/" + path


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
    encoded = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    existing = _existing_report(session, path, encoded)
    if existing:
        return existing
    payload = {
        "message": "chore(lab): publish evaluation report " + run_id,
        "content": base64.b64encode(encoded).decode("ascii"),
        "branch": BRANCH,
    }
    response = session.put(API + "/contents/" + path, json=payload, timeout=30)
    if response.status_code in (409, 422):
        # A second request may have created the file while PUT was in flight.
        existing = _existing_report(session, path, encoded)
        if existing:
            return existing
        if response.status_code == 422:
            raise GitHubPublishRejected(describe_github_rejection(response))
    response.raise_for_status()
    return response.json()["content"]["html_url"]
