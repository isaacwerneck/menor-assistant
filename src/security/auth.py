"""Autenticação local do proprietário para escrita persistente pelo navegador.

Primeira configuração feita na rede privada, por UI. Para Internet, exigir TLS/VPN.
"""
import base64
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import threading
import time
from urllib.parse import urlsplit

from fastapi import HTTPException

from src.memory.store import BrainStore

COOKIE_NAME = "menor_session"
SESSION_SECONDS = 7 * 24 * 3600
_lock = threading.RLock()
_attempts = {}


def _encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _config_path():
    return BrainStore().data_dir / "owner.json"


def _read_config():
    path = _config_path()
    if not path.exists():
        return None
    if path.is_symlink():
        raise RuntimeError("Configuração de proprietário inválida.")
    return json.loads(path.read_text(encoding="utf-8"))


def configured():
    return _read_config() is not None


def _private_network(request):
    try:
        ip = ipaddress.ip_address(request.client.host)
        return ip.is_private or ip.is_loopback
    except (AttributeError, ValueError):
        return False


def public_origin():
    """Origem HTTPS canônica configurada no servidor, nunca em headers recebidos.

    Sem variável, mantém o comportamento local já existente.
    """
    value = os.environ.get("MENOR_PUBLIC_ORIGIN", "").strip()
    if not value:
        return None
    if len(value) > 253 or value != value.lower():
        raise RuntimeError("MENOR_PUBLIC_ORIGIN inválida: use https://subdominio.exemplo.com.")
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    labels = host.split(".")
    if all(label.isdecimal() for label in labels):
        raise RuntimeError("MENOR_PUBLIC_ORIGIN precisa ser um domínio DNS, não IP.")
    if (parsed.scheme != "https" or parsed.netloc != host or
            len(labels) < 2 or any(not label or len(label) > 63 or
            label[0] == "-" or label[-1] == "-" or
            any(not (char.isascii() and (char.isalnum() or char == "-"))
                for char in label) for label in labels) or
            parsed.path or parsed.query or parsed.fragment or parsed.username or
            parsed.password or parsed.port):
        raise RuntimeError("MENOR_PUBLIC_ORIGIN inválida: HTTPS com hostname, sem path/porta.")
    return value


def check_origin(request):
    """Sem confiar em X-Forwarded-Host/Proto, preserva a origem HTTPS pública."""
    canonical = public_origin()
    origin = request.headers.get("origin")
    host = request.headers.get("host", "")
    if canonical:
        expected_host = urlsplit(canonical).hostname
        if host == expected_host:
            # Para host público, exigir prova de origem em qualquer escrita.
            # Cookies SameSite=Strict continuam sendo uma defesa adicional.
            if request.method.upper() not in ("GET", "HEAD", "OPTIONS"):
                if origin != canonical:
                    raise HTTPException(403, "Origem HTTPS pública não autorizada.")
            elif origin and origin != canonical:
                raise HTTPException(403, "Origem HTTPS pública não autorizada.")
            return
        # Só o loopback pode ser usado como hostname alternativo no host.
        # O túnel usa o hostname público; não admitir Host arbitrário do cliente.
        if host not in ("127.0.0.1", "127.0.0.1:8000", "localhost", "localhost:8000"):
            raise HTTPException(403, "Hostname público não autorizado.")
        if not request.client or request.client.host not in ("127.0.0.1", "::1"):
            raise HTTPException(403, "Acesso local indisponível.")
    if origin:
        expected = f"{request.url.scheme}://{host}"
        if origin.rstrip("/") != expected:
            raise HTTPException(403, "Origem não autorizada.")


def create_owner(request, password):
    """Permite a configuração inicial por UI apenas em rede privada (primeiro usuário)."""
    # Nunca deixar Cloudflare publicar /auth/setup: o conector enxerga
    # loopback no servidor, portanto request.client.is_private não basta.
    if public_origin():
        raise HTTPException(403, "Crie a senha localmente antes de ativar o acesso externo.")
    if not _private_network(request):
        raise HTTPException(403, "Configuração inicial disponível apenas em rede privada.")
    check_origin(request)
    if not isinstance(password, str) or not 12 <= len(password) <= 128 or not password.strip():
        raise HTTPException(422, "Use uma senha de 12 a 128 caracteres.")
    with _lock:
        if configured():
            raise HTTPException(409, "Proprietário já configurado.")
        BrainStore().initialize()
        salt = secrets.token_bytes(16)
        key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
        settings = {
            "salt": salt.hex(),
            "password_hash": key.hex(),
            "session_secret": secrets.token_hex(32),
        }
        path = _config_path()
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise HTTPException(409, "Proprietário já configurado.") from None
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(settings, output)
            output.flush()
            os.fsync(output.fileno())
    return settings


def _verify_password(password, config):
    try:
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(config["salt"]), n=2**14, r=8, p=1,
        )
        return hmac.compare_digest(digest, bytes.fromhex(config["password_hash"]))
    except (ValueError, KeyError, TypeError):
        return False


def login(request, password):
    check_origin(request)
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _lock:
        times = [x for x in _attempts.get(key, []) if now - x < 120]
        if len(times) >= 5:
            raise HTTPException(429, "Aguarde dois minutos para tentar novamente.")
        config = _read_config()
        if not config:
            raise HTTPException(409, "Crie uma senha primeiro.")
        if not _verify_password(password, config):
            times.append(now)
            _attempts[key] = times
            raise HTTPException(401, "Senha incorreta.")
        _attempts.pop(key, None)
    return _create_session(config)


def _create_session(config):
    payload = f"{int(time.time()) + SESSION_SECONDS}.{secrets.token_hex(12)}"
    signature = hmac.new(bytes.fromhex(config["session_secret"]), payload.encode(), hashlib.sha256).digest()
    return _encode(payload.encode()) + "." + _encode(signature)


def is_authenticated(request):
    token = request.cookies.get(COOKIE_NAME, "")
    if not token or len(token) > 256:
        return False
    config = _read_config()
    if not config:
        return False
    try:
        encoded, signature = token.split(".", 1)
        payload = _decode(encoded)
        expected = hmac.new(bytes.fromhex(config["session_secret"]), payload, hashlib.sha256).digest()
        expiry = int(payload.decode().split(".", 1)[0])
        return hmac.compare_digest(expected, _decode(signature)) and int(time.time()) < expiry
    except (ValueError, KeyError, TypeError, UnicodeError):
        return False


def require_owner(request):
    if not is_authenticated(request):
        raise HTTPException(401, "Entre com a senha do Menor para continuar.")
    check_origin(request)


def set_session_cookie(response, request, token):
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_SECONDS, httponly=True,
        secure=(request.url.scheme == "https" or
                (public_origin() is not None and
                 request.headers.get("host") == urlsplit(public_origin()).hostname)),
        samesite="strict", path="/",
    )
