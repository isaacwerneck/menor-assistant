"""Build the public Netlify launcher. The real chat remains on Cloudflare Tunnel.

This is a build-only static page with no secrets or client-side API proxy.
"""
import os
from pathlib import Path
from urllib.parse import urlsplit

from ops.remote_access import hostname

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "__MENOR_PRIVATE_URL__"


def build(origin, *, template=None, output_dir=None):
    if not isinstance(origin, str) or not origin.startswith("https://"):
        raise ValueError("MENOR_PUBLIC_ORIGIN deve começar com https://.")
    parsed = urlsplit(origin)
    host = hostname(parsed.netloc)
    if origin != "https://" + host:
        raise ValueError("MENOR_PUBLIC_ORIGIN deve ser exatamente https://<subdomínio>.")
    input_file = template or ROOT / "deploy" / "netlify" / "landing.html"
    target = output_dir or ROOT / "dist"
    source = Path(input_file).read_text(encoding="utf-8")
    if source.count(TOKEN) != 1:
        raise ValueError("Template Netlify sem placeholder único.")
    Path(target).mkdir(parents=True, exist_ok=True)
    index = Path(target) / "index.html"
    index.write_text(source.replace(TOKEN, origin + "/"), encoding="utf-8")
    return index


def main():
    origin = os.environ.get("MENOR_PUBLIC_ORIGIN", "")
    try:
        output = build(origin)
    except (ValueError, OSError) as error:
        raise SystemExit("Build cancelado: " + str(error)) from error
    print("Página estática preparada em " + str(output.relative_to(ROOT)))


if __name__ == "__main__":
    main()
