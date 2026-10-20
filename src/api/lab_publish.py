"""Publica apenas resumos anônimos em branch isolada (nunca respostas completas)."""
import base64
import json
import os
import requests

API = "https://api.github.com/repos/isaacwerneck/menor-assistant"
BRANCH = "lab-reports"


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
