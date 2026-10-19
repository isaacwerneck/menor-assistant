"""Pesquisa e leitura públicas; conteúdo remoto nunca concede permissões."""
import http.client
import ipaddress
import logging
import os
import socket
import ssl
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote, urljoin, urlsplit
from xml.etree import ElementTree

LOGGER = logging.getLogger(__name__)
MAX_BYTES = 1024 * 1024
MAX_TEXT = 12000


class WebUnavailable(RuntimeError):
    pass


def public_url(url):
    if not isinstance(url, str) or len(url) > 2000 or any(ord(c) <= 32 for c in url):
        raise ValueError("URL inválida.")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in (None, 443)):
        raise ValueError("Somente HTTPS público, sem credenciais e na porta padrão.")
    host = parsed.hostname.encode("idna").decode("ascii")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Endereço local não permitido.")
    return parsed, host


def _address(host):
    addresses = list(dict.fromkeys(
        item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    ))
    if not addresses:
        raise WebUnavailable("O site não possui endereço disponível.")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global or (getattr(ip, "ipv4_mapped", None) and not ip.ipv4_mapped.is_global):
            raise ValueError("Endereços privados ou reservados não são permitidos.")
    return addresses[0]


def _download(url, resource=False):
    for _ in range(4):
        parsed, host = public_url(url)
        address = _address(host)
        connection = http.client.HTTPSConnection(host, timeout=12)
        try:
            # Conecta ao IP validado e mantém hostname no TLS: impede DNS rebinding.
            raw = socket.create_connection((address, 443), timeout=12)
            try:
                connection.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
            except Exception:
                raw.close()
                raise
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            connection.request("GET", path, headers={
                "Host": host, "User-Agent": "MenorResearch/1.0",
                "Accept": "text/html,text/plain,application/xhtml+xml",
                "Accept-Encoding": "identity",
            })
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise WebUnavailable("Redirecionamento sem destino.")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise WebUnavailable(f"O site recusou a leitura (HTTP {response.status}).")
            media = response.getheader("Content-Type", "").split(";", 1)[0].lower()
            allowed = ("text/html", "text/plain", "application/xhtml+xml")
            if resource:
                allowed += ("text/css", "text/javascript", "application/javascript", "application/json",
                            "application/rss+xml", "application/xml", "text/xml")
            if media not in allowed:
                raise WebUnavailable("A página não contém texto ou HTML suportado.")
            if response.getheader("Content-Encoding", "identity") != "identity":
                raise WebUnavailable("Compressão não suportada nesta leitura.")
            chunks, size = [], 0
            deadline = time.monotonic() + 20
            while size <= MAX_BYTES:
                if time.monotonic() >= deadline:
                    raise WebUnavailable("Tempo total de leitura excedido.")
                chunk = response.read1(min(65536, MAX_BYTES + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
            data = b"".join(chunks)
            if len(data) > MAX_BYTES:
                raise WebUnavailable("Página excede o limite de 1 MiB.")
            charset = response.headers.get_content_charset() or "utf-8"
            return url, data.decode(charset, errors="replace"), media
        finally:
            connection.close()
    raise WebUnavailable("Excesso de redirecionamentos.")


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links = [], []
        self.hidden = 0
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self.hidden += 1
        if tag == "a":
            self.anchor = {"url": attrs.get("href") or "", "title": "",
                           "result": "result__a" in (attrs.get("class") or "").split()}
        if tag in ("p", "div", "br", "li", "h1", "h2", "pre"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.hidden:
            self.hidden -= 1
        if tag == "a" and self.anchor is not None:
            self.links.append(self.anchor)
            self.anchor = None

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)
            if self.anchor is not None:
                self.anchor["title"] += data

    def text(self):
        return "\n".join(" ".join(line.split()) for line in "".join(self.parts).splitlines() if line.strip())


def read(url):
    try:
        final, content, media = _download(url)
        parser = PageText()
        parser.feed(content if media != "text/plain" else "")
        text = content if media == "text/plain" else parser.text()
        if not text.strip():
            raise WebUnavailable("A página não forneceu texto legível.")
        return {"url": final, "text": text[:MAX_TEXT], "truncated": len(text) > MAX_TEXT,
                "accessed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    except (OSError, http.client.HTTPException, LookupError) as error:
        raise WebUnavailable("Não consegui acessar a página pública.") from error


def _search_html(query):
    if not isinstance(query, str) or not 3 <= len(query.strip()) <= 280:
        raise ValueError("Pesquisa deve ter entre 3 e 280 caracteres.")
    try:
        _, html, _ = _download("https://html.duckduckgo.com/html/?q=" + quote(query.strip()))
        parser = PageText()
        parser.feed(html)
        results, seen = [], set()
        for link in parser.links:
            if not link["result"]:
                continue
            target = urljoin("https://html.duckduckgo.com", link["url"])
            redirect = parse_qs(urlsplit(target).query).get("uddg")
            target = redirect[0] if redirect else target
            try:
                _, host = public_url(target)
            except ValueError:
                continue
            if host.endswith("duckduckgo.com") or target in seen:
                continue
            seen.add(target)
            results.append({"url": target, "title": " ".join(link["title"].split())[:200]})
            if len(results) == 5:
                break
        if not results:
            raise WebUnavailable("Busca sem resultados legíveis; pode haver bloqueio ou CAPTCHA.")
        return {"query": query, "results": results, "provider": "duckduckgo-html"}
    except (OSError, http.client.HTTPException, LookupError) as error:
        raise WebUnavailable("A busca está indisponível; nenhuma resposta foi confirmada.") from error


def search(query):
    try:
        return _search_html(query)
    except (WebUnavailable, OSError, http.client.HTTPException) as error:
        LOGGER.warning("Busca HTML indisponível: %s; tentando feed público.", type(error).__name__)
    try:
        _, content, _ = _download(
            "https://www.bing.com/search?q=" + quote(query.strip()) + "&format=rss", resource=True,
        )
        if "<!DOCTYPE" in content.upper() or "<!ENTITY" in content.upper():
            raise WebUnavailable("Feed contém declaração XML não permitida.")
        feed = ElementTree.fromstring(content)
        results, seen = [], set()
        for item in feed.findall("./channel/item"):
            target = item.findtext("link", "")
            try:
                public_url(target)
            except ValueError:
                continue
            if target in seen:
                continue
            seen.add(target)
            results.append({"url": target, "title": item.findtext("title", "")[:200]})
            if len(results) == 5:
                break
        if not results:
            raise WebUnavailable("Os buscadores não retornaram resultados públicos legíveis.")
        return {"query": query, "results": results, "provider": "bing-rss"}
    except (OSError, http.client.HTTPException, LookupError, ElementTree.ParseError) as error:
        raise WebUnavailable("Busca indisponível nos provedores públicos.") from error


def browse(url):
    """Navegador opcional sem sessão do dono; toda rede passa pelo leitor público."""
    public_url(url)
    if os.environ.get("MENOR_BROWSER_ENABLED", "0") != "1":
        raise WebUnavailable("Navegador desativado. Instale requirements-browser.txt e ative MENOR_BROWSER_ENABLED=1.")
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError as error:
        raise WebUnavailable("Playwright não está instalado no ambiente do Menor.") from error
    deadline = time.monotonic() + 40
    remaining = [16]
    failures = []

    def intercept(route):
        request = route.request
        if (time.monotonic() >= deadline or remaining[0] <= 0 or request.method != "GET"
                or request.resource_type not in ("document", "script", "stylesheet", "xhr", "fetch")):
            route.abort()
            return
        remaining[0] -= 1
        try:
            _, content, media = _download(request.url, resource=True)
            route.fulfill(status=200, content_type=media, body=content)
        except (ValueError, WebUnavailable, OSError, http.client.HTTPException, LookupError) as error:
            failures.append(type(error).__name__)
            route.abort()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True, chromium_sandbox=True, timeout=15000,
                args=["--force-webrtc-ip-handling-policy=disable_non_proxied_udp"],
                env={key: value for key, value in os.environ.items()
                     if key in ("PATH", "HOME", "SYSTEMROOT", "TEMP", "TMP", "LANG")},
            )
            try:
                context = browser.new_context(accept_downloads=False, service_workers="block")
                context.route("**/*", intercept)
                context.route_web_socket("**/*", lambda websocket: websocket.close())
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                text = page.locator("body").inner_text(timeout=5000)
                if not text.strip():
                    raise WebUnavailable("Navegador não encontrou texto legível.")
                return {"url": page.url, "text": text[:MAX_TEXT], "truncated": len(text) > MAX_TEXT,
                        "accessed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "blocked_requests": len(failures)}
            finally:
                browser.close()
    except Error as error:
        raise WebUnavailable("Navegador indisponível, página bloqueada ou tempo excedido.") from error
