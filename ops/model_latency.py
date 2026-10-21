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


def configured_num_thread():
    """Override de CPU opt-in; inválido não altera silenciosamente a inferência."""
    raw = os.environ.get("MENOR_OLLAMA_NUM_THREAD", "").strip()
    if not raw:
        return None
    if not raw.isascii() or not raw.isdecimal() or int(raw) not in (1, 2, 4, 6, 8):
        raise ValueError("MENOR_OLLAMA_NUM_THREAD exige 1, 2, 4, 6 ou 8.")
    return int(raw)


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
    total_prompt = result.get("prompt_eval_count")
    cached = result.get("prompt_eval_cached_count")
    if total_prompt is not None and cached is not None and cached <= total_prompt:
        result["estimated_uncached_prompt_tokens"] = total_prompt - cached
        result["prompt_cached_fraction"] = round(cached / total_prompt, 3) if total_prompt else None
        if result.get("prompt_eval_duration", 0) > 0:
            result["estimated_uncached_prompt_tokens_per_second"] = round(
                (total_prompt - cached) * 1e9 / result["prompt_eval_duration"], 2)
    components = ("load_duration", "prompt_eval_duration", "eval_duration")
    if "total_duration" in result and all(key in result for key in components):
        known = sum(result[key] for key in components)
        if known <= result["total_duration"]:
            result["other_model_ms"] = round((result["total_duration"] - known) / 1e6, 2)
    return result


def measure_one(post, endpoint, model, prompt, *, num_thread=None, num_predict=80):
    start = time.monotonic()
    if type(num_predict) is not int or num_predict not in (16, 80, 96):
        raise ValueError("Orçamento de saída inválido.")
    options = {"temperature": 0.1, "num_predict": num_predict}
    if num_thread is not None:
        if type(num_thread) is not int or num_thread not in (1, 2, 4, 6, 8):
            raise ValueError("Número de threads fora do experimento aprovado.")
        options["num_thread"] = num_thread
    with post(endpoint, json={
        "model": model,
        "messages": [
            {"role": "system", "content": "Responda em português de modo conciso."},
            {"role": "user", "content": prompt},
        ],
        "stream": False, "options": options,
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


def thread_sweep(*, samples=2, post=None, url=None, model=None):
    """Experimento voluntário: mesma pergunta e modelo, diferentes threads.

    Cada rodada alterna a ordem para reduzir efeito de cache e aquecimento.
    Não altera serviços, variáveis de ambiente nem modelo padrão.
    """
    if type(samples) is not int or not 1 <= samples <= 3:
        raise ValueError("Samples deve estar entre 1 e 3.")
    endpoint = local_endpoint(url or os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"))
    selected = model_identifier(model or os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b"))
    caller = post if post is not None else requests.post
    observations = {thread: [] for thread in (1, 2, 4, 6, 8)}
    for index in range(samples):
        order = (1, 2, 4, 6, 8) if index % 2 == 0 else (8, 6, 4, 2, 1)
        for threads in order:
            outcome = measure_one(caller, endpoint, selected, PUBLIC_PROBES[0],
                                  num_thread=threads)
            observations[threads].append(outcome)
    data = []
    for threads, rows in observations.items():
        speeds = [row["metrics"]["generation_tokens_per_second"] for row in rows
                  if "generation_tokens_per_second" in row["metrics"]]
        prefills = [row["metrics"]["prompt_processing_ms"] for row in rows
                    if "prompt_processing_ms" in row["metrics"]]
        data.append({"threads": threads, "samples": len(rows),
                     "median_seconds": round(statistics.median(
                         row["elapsed_seconds"] for row in rows), 3),
                     "median_generation_tokens_per_second": round(statistics.median(speeds), 2)
                     if speeds else None,
                     "median_prompt_ms": round(statistics.median(prefills), 2)
                     if prefills else None,
                     "details": rows})
    return {"model": selected, "status": "measured", "variants": data,
            "privacy": "fixed_public_prompts_only",
            "limits": "Não mede workloads longos, interferência térmica, GPU nem efeito de concorrência."}


def diagnostic_matrix(*, samples=2, post=None, url=None, model=None):
    """Diagnóstico opt-in de prefill/cache versus geração com dados públicos fixos.

    Repete quatro combinações de prompt e orçamento, alternando a ordem;
    não modifica cache, contextos persistentes, drivers ou configuração global.
    """
    if type(samples) is not int or not 1 <= samples <= 3:
        raise ValueError("Samples deve estar entre 1 e 3.")
    endpoint = local_endpoint(url or os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"))
    selected = model_identifier(model or os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b"))
    caller = post if post is not None else requests.post
    context = ("O cenário público de teste tem três serviços independentes. "
               "O serviço A recebe registros; o serviço B valida dados; "
               "o serviço C salva relatórios sem alterar originais. ") * 12
    combinations = (("short", 16), ("short", 96), ("long", 16), ("long", 96))
    results = {name + "-" + str(limit): [] for name, limit in combinations}
    for attempt in range(samples):
        order = combinations if attempt % 2 == 0 else tuple(reversed(combinations))
        for kind, cap in order:
            prompt = PUBLIC_PROBES[0] if kind == "short" else (
                context + " Resuma os três serviços e seus cuidados em tópicos.")
            row = measure_one(caller, endpoint, selected, prompt, num_predict=cap)
            results[kind + "-" + str(cap)].append(row)
    data = []
    for (kind, cap), key in zip(combinations, results):
        observations = results[key]
        item = {"prompt": kind, "output_limit": cap,
                "samples": len(observations), "timings": observations}
        for field, label in (("prompt_processing_ms", "median_prompt_ms"),
                             ("token_generation_ms", "median_generation_ms"),
                             ("generation_tokens_per_second", "median_generation_tps"),
                             ("prompt_cached_fraction", "median_cached_fraction"),
                             ("eval_count", "median_generated_tokens")):
            values = [row["metrics"][field] for row in observations
                      if isinstance(row["metrics"].get(field), (int, float))]
            item[label] = round(statistics.median(values), 3) if values else None
        data.append(item)
    return {"model": selected, "status": "measured", "samples": samples,
            "probes": data, "privacy": "fixed_public_prompts_only",
            "limits": "Warm-only: não descarrega modelos. Comparar tokens reais, cache, carga e temperatura; "
                      "orçamento não equivale a quantidade gerada."}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Benchmark local e voluntário do Ollama")
    parser.add_argument("--live", action="store_true",
                        help="Autoriza uma a três inferências de prompts públicos no Ollama local.")
    parser.add_argument("--samples", type=int, default=2, help="Número de inferências (1 a 3).")
    parser.add_argument("--model", default=None, help="Modelo já instalado para a medição.")
    parser.add_argument("--diagnose", action="store_true",
                        help="Com --live, compara prompts curtos/longos e geração; 4 a 12 inferências.")
    parser.add_argument("--thread-sweep", action="store_true",
                        help="Com --live, testa 1/2/4/6/8 threads em sequência; gera mais carga.")
    args = parser.parse_args(argv)
    if not args.live:
        print("Somente com --live: nada foi executado no modelo.")
        return 0
    if args.diagnose and args.thread_sweep:
        parser.error("Escolha somente --diagnose ou --thread-sweep.")
    try:
        result = (diagnostic_matrix(samples=args.samples, model=args.model)
                  if args.diagnose else thread_sweep(samples=args.samples, model=args.model)
                  if args.thread_sweep else benchmark(samples=args.samples, model=args.model))
    except (ValueError, requests.RequestException, OSError) as error:
        print("Benchmark indisponível: " + type(error).__name__, file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
