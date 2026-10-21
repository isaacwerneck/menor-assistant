"""Benchmark voluntário e local da latência do Ollama, sem prompts privados.

Não roda por padrão, não altera estado, não instala modelos e não aceita URLs
remotas para evitar transmitir conversas do dono a serviços externos.
"""
import argparse
import json
import os
import statistics
import sys
import time
from urllib.parse import urlsplit

import requests


PUBLIC_PROBES = (
    "Explique em uma frase curta o que é um algoritmo.",
    "Qual a diferença entre uma lista e um dicionário em Python? Responda brevemente.",
    "Planeje em duas etapas um sistema de backup local, sem executar comandos.",
)


def local_endpoint(url):
    if not isinstance(url, str) or len(url) > 128:
        raise ValueError("Endereço do Ollama inválido.")
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("Porta do Ollama inválida.") from error
    if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
            or parsed.username or parsed.password or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment or not port or not 1 <= port <= 65535):
        raise ValueError("Benchmark exige Ollama HTTP na interface loopback.")
    return url.rstrip("/") + "/api/chat"


def model_identifier(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 90
            or any(not (character.isascii() and (character.isalnum()
                                                 or character in "._:-")) for character in value)):
        raise ValueError("Modelo inválido.")
    return value


def numeric_summary(response):
    result = {}
    for key in ("total_duration", "load_duration", "prompt_eval_duration",
                "eval_duration", "prompt_eval_count", "prompt_eval_cached_count",
                "eval_count"):
        value = response.get(key)
        if type(value) is int and 0 <= value <= 10 ** 15:
            result[key] = value
    for field, source in (
        ("ollama_total_ms", "total_duration"),
        ("model_load_ms", "load_duration"),
        ("prompt_processing_ms", "prompt_eval_duration"),
        ("token_generation_ms", "eval_duration"),
    ):
        if source in result:
            result[field] = round(result[source] / 1e6, 2)
    if result.get("eval_duration", 0) > 0 and "eval_count" in result:
        result["generation_tokens_per_second"] = round(
            result["eval_count"] * 1e9 / result["eval_duration"], 2)
    if result.get("prompt_eval_duration", 0) > 0 and "prompt_eval_count" in result:
        result["prompt_tokens_per_second"] = round(
            result["prompt_eval_count"] * 1e9 / result["prompt_eval_duration"], 2)
    components = ("load_duration", "prompt_eval_duration", "eval_duration")
    if "total_duration" in result and all(key in result for key in components):
        known = sum(result[key] for key in components)
        if known <= result["total_duration"]:
            result["other_model_ms"] = round((result["total_duration"] - known) / 1e6, 2)
    return result


def measure_one(post, endpoint, model, prompt):
    start = time.monotonic()
    with post(endpoint, json={
        "model": model,
        "messages": [
            {"role": "system", "content": "Responda em português de modo conciso."},
            {"role": "user", "content": prompt},
        ],
        "stream": False, "options": {"temperature": 0.1, "num_predict": 80},
    }, timeout=(3, 70)) as response:
        response.raise_for_status()
        payload = response.json()
    elapsed = max(0, time.monotonic() - start)
    message = payload.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise ValueError("Resposta do modelo inválida.")
    return {"elapsed_seconds": round(elapsed, 3), "metrics": numeric_summary(payload)}


def benchmark(*, samples=2, post=None, url=None, model=None):
    if type(samples) is not int or not 1 <= samples <= 3:
        raise ValueError("Samples deve estar entre 1 e 3.")
    endpoint = local_endpoint(url or os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"))
    model = model_identifier(model or os.environ.get("MENOR_REASONING_MODEL")
                             or os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b"))
    caller = post if post is not None else requests.post
    results = [measure_one(caller, endpoint, model, PUBLIC_PROBES[i])
               for i in range(samples)]
    timings = [record["elapsed_seconds"] for record in results]
    speeds = [record["metrics"]["generation_tokens_per_second"] for record in results
              if "generation_tokens_per_second" in record["metrics"]]
    return {
        "model": model, "probes": samples, "status": "measured",
        "median_seconds": round(statistics.median(timings), 3),
        "max_seconds": max(timings),
        "median_tokens_per_second": round(statistics.median(speeds), 2) if speeds else None,
        "details": results,
        "privacy": "fixed_public_prompts_only",
        "limits": "Mede requests não streaming, não tempo até primeiro token nem desempenho geral.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Benchmark local e voluntário do Ollama")
    parser.add_argument("--live", action="store_true",
                        help="Autoriza uma a três inferências de prompts públicos no Ollama local.")
    parser.add_argument("--samples", type=int, default=2, help="Número de inferências (1 a 3).")
    args = parser.parse_args(argv)
    if not args.live:
        print("Somente com --live: nada foi executado no modelo.")
        return 0
    try:
        result = benchmark(samples=args.samples)
    except (ValueError, requests.RequestException, OSError) as error:
        print("Benchmark indisponível: " + type(error).__name__, file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
