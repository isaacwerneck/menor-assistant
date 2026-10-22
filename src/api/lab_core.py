"""Catálogo fixo das capacidades do Menor e rotação reproduzível de paráfrases.

As baterias são virtuais: não proliferam arquivos por rodada. Rodadas com
modelos diferentes recebem exatamente as mesmas versões dos enunciados.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[2] / "lab" / "core" / "capabilities.json"
CATALOG_VERSION = "core-v1"
CORE_DOMAINS = (
    "conversa", "intencao", "memoria", "planejamento", "projetos",
    "documentos", "programacao", "ferramentas", "seguranca", "pesquisa",
    "multimodal", "delegacao", "autoaperfeicoamento", "desempenho",
)
CORE_IDS = tuple("core-" + domain for domain in CORE_DOMAINS)
ROTATION_SIZE = 3


@lru_cache(maxsize=1)
def catalog():
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    capabilities = raw.get("capabilities")
    if (raw.get("version") != CATALOG_VERSION
            or raw.get("count") != len(CORE_IDS)
            or not isinstance(capabilities, list)
            or tuple(entry.get("id") for entry in capabilities) != CORE_IDS):
        raise ValueError("Catálogo principal das capacidades inconsistente.")
    for entry in capabilities:
        scenarios = entry.get("scenarios")
        if (entry.get("engine") not in ("chat", "semantic")
                or not isinstance(scenarios, list) or len(scenarios) != 2
                or not isinstance(entry.get("phase"), str)
                or entry.get("evidence") != "model_only"):
            raise ValueError("Bateria de capacidade malformada.")
        for scenario in scenarios:
            turns = scenario.get("turns")
            if not isinstance(turns, list) or len(turns) != 4:
                raise ValueError("Conversa de referência malformada.")
            alternatives = scenario.get("paraphrases", [])
            if (not isinstance(alternatives, list)
                    or len(alternatives) not in (0, ROTATION_SIZE - 1)):
                raise ValueError("Variações devem ser fixas ou ter duas paráfrases.")
            for variant in alternatives:
                if (not isinstance(variant, list) or len(variant) != len(turns)
                        or any(not isinstance(text, str) or not 3 <= len(text) <= 800
                               for text in variant)):
                    raise ValueError("Paráfrase malformada.")
    return raw


def is_core_id(suite_id):
    return suite_id in CORE_IDS


def suite(suite_id, cycle=0):
    """Prepara bateria sem alterar a fonte; cycle igual entre modelos em uma fila."""
    if suite_id not in CORE_IDS:
        raise FileNotFoundError(suite_id)
    if type(cycle) is not int or cycle < 0:
        raise ValueError("Rodada de avaliação inválida.")
    entry = catalog()["capabilities"][CORE_IDS.index(suite_id)]
    scenarios = deepcopy(entry["scenarios"])
    for case in scenarios:
        alternatives = case.pop("paraphrases", [])
        index = cycle % (len(alternatives) + 1) if alternatives else 0
        if index:
            for turn, message in zip(case["turns"], alternatives[index - 1]):
                turn["message"] = message
        case["scenario_variant"] = index
        case.pop("anchor", None)
    return {
        "id": entry["id"], "title": entry["title"], "description": entry["description"],
        "capability": entry["domain"], "phase": entry["phase"],
        "evidence_level": "model_only", "core_catalog_version": CATALOG_VERSION,
        "core_cycle": cycle, "comparison_group": "core-capabilities-v1",
        "methodology_version": "core-stable-domains-v1", "cases": scenarios,
    }


def next_cycle(data_dir):
    """Sequência global baseada em resumos válidos, sem consultar modelos."""
    folder = Path(data_dir)
    previous = -1
    for path in folder.glob("*.summary.json") if folder.is_dir() else ():
        if path.is_symlink() or path.stat().st_size > 100000:
            continue
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            if (is_core_id(item.get("suite_id"))
                    and type(item.get("core_cycle")) is int
                    and 0 <= item["core_cycle"] < 1000000):
                previous = max(previous, item["core_cycle"])
        except (ValueError, OSError, TypeError):
            continue
    return previous + 1
