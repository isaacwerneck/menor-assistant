"""Prepare Cloudflare Tunnel config locally without provisioning or credentials.

No external network calls; never writes to a user config file implicitly.
"""
import argparse
import ipaddress
import json
import os
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit


def hostname(value):
    if not isinstance(value, str) or not value or len(value) > 253:
        raise ValueError("Informe um subdomínio HTTPS válido.")
    parsed = urlsplit("https://" + value)
    if (value != value.lower() or parsed.hostname != value
            or parsed.netloc != value or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment):
        raise ValueError("Hostname deve ser apenas menor.seudominio.com.")
    labels = value.split(".")
    if len(labels) < 3:
        raise ValueError("Use um subdomínio, como menor.seudominio.com.")
    if any(not segment or len(segment) > 63 or
           segment.startswith("-") or segment.endswith("-") or
           any(not (char.isascii() and (char.isalnum() or char == "-"))
               for char in segment) for segment in labels):
        raise ValueError("Hostname contém caracteres inválidos.")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise ValueError("Use hostname DNS, não IP.")


def tunnel_uuid(value):
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError("Informe o UUID do túnel criado no Cloudflare.") from error
    if str(parsed) != value:
        raise ValueError("Informe o UUID canônico em letras minúsculas.")
    return str(parsed)


def render_config(*, host, tunnel_id, home=None):
    safe_host = hostname(host)
    ident = tunnel_uuid(tunnel_id)
    folder = Path(home) if home is not None else Path.home()
    credential = folder / ".cloudflared" / (ident + ".json")
    # O arquivo de credenciais não é copiado nem impresso; somente seu path.
    return (
        "tunnel: " + ident + "\n"
        + "credentials-file: " + json.dumps(str(credential)) + "\n"
        + "ingress:\n"
        + "  - hostname: " + safe_host + "\n"
        + "    service: http://127.0.0.1:8000\n"
        + "  - service: http_status:404\n"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Gerar, sem instalar, configuração segura do Cloudflare Tunnel.")
    parser.add_argument("--hostname", required=True,
                        help="Subdomínio com DNS na Cloudflare, sem https://")
    parser.add_argument("--tunnel-id", required=True, help="UUID do túnel do proprietário.")
    args = parser.parse_args(argv)
    try:
        print(render_config(host=args.hostname, tunnel_id=args.tunnel_id), end="")
    except ValueError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
