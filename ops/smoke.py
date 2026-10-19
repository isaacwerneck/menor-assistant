"""Smoke tests de leitura: contrato da API e isolamento de rotas privadas.

Executa somente GET no loopback, sem cookies, uploads, ações ou credenciais.
Não substitui um teste autenticado das funcionalidades.
"""

import argparse
import http.client
import json

from ops.doctor import Check, _port, _timeout

_MAX_BYTES = 8192

# Somente rotas GET estáveis e sem efeito de escrita. Manter em sincronia com
# os testes ASGI; jamais incluir aqui endpoints de execução ou upload.
PRIVATE_GET = (
    ("tools_private", "/tools"),
    ("agent_feedback_private", "/agent/feedback/stats"),
    ("agent_runs_private", "/agent/runs/menor-smoke-test"),
    ("agent_missions_private", "/agent/missions"),
    ("image_status_private", "/images/status"),
    ("files_private", "/files/capabilities"),
    ("file_view_private", "/files/view"),
    ("memory_private", "/memory/knowledge"),
)


def _get(path, port, timeout, read_body=False):
    """Sem redirects, sem cookies e com resposta limitada para o único GET público."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("GET", path, headers={"Accept": "application/json"})
        response = connection.getresponse()
        status = response.status
        if not read_body:
            return status, None
        content = response.read(_MAX_BYTES + 1)
        if len(content) > _MAX_BYTES:
            raise ValueError("resposta acima do limite")
        return status, content
    finally:
        connection.close()


def _health_contract(payload):
    """Valida os campos consumidos pelos clientes, aceitando campos adicionais."""
    if not isinstance(payload, dict):
        return False
    version = payload.get("api_contract")
    model = payload.get("default_model")
    software = payload.get("version")
    return (
        payload.get("status") == "online"
        and payload.get("service") == "Menor API"
        and type(version) is int and version >= 1
        and isinstance(model, str) and bool(model.strip()) and len(model) <= 200
        and isinstance(software, str) and bool(software.strip()) and len(software) <= 80
        and payload.get("ollama_status") in ("online", "offline", "degraded")
    )


def run_smoke(port=8000, timeout=2.0):
    """Retorna verificações sem informações privadas e sem lançar erros de rede."""
    try:
        status, content = _get("/health", port, timeout, read_body=True)
        valid = status == 200 and _health_contract(json.loads(content))
    except (OSError, http.client.HTTPException, ValueError, UnicodeError, TypeError):
        valid = False

    checks = []
    if not valid:
        checks.append(Check("api_contract", "critical", "API inacessível ou contrato /health inválido."))
        checks.extend(
            Check(name, "skipped", "Verificação suspensa porque o contrato da API falhou.")
            for name, _ in PRIVATE_GET
        )
    else:
        checks.append(Check("api_contract", "ok", "Campos públicos essenciais de /health válidos."))
        for name, path in PRIVATE_GET:
            try:
                code, _ = _get(path, port, timeout)
                if code in (401, 403):
                    checks.append(Check(name, "ok", "Acesso sem sessão negado."))
                else:
                    checks.append(Check(name, "critical", "Rota privada não recusou acesso como esperado."))
            except (OSError, http.client.HTTPException, ValueError):
                checks.append(Check(name, "critical", "Não foi possível verificar proteção da rota."))

    overall = "critical" if any(check.status == "critical" for check in checks) else "ok"
    return {
        "status": overall,
        "read_only": True,
        "authenticated": False,
        "checks": [vars(item) for item in checks],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Smoke test local e sem autenticação do Menor")
    parser.add_argument("--port", type=_port, default=8000)
    parser.add_argument("--timeout", type=_timeout, default=2.0)
    parser.add_argument("--json", action="store_true", help="Saída JSON sem corpos de respostas")
    args = parser.parse_args(argv)
    report = run_smoke(port=args.port, timeout=args.timeout)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        for check in report["checks"]:
            print(f"[{check['status'].upper()}] {check['name']}: {check['detail']}")
        print("Resultado:", report["status"].upper())
    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
