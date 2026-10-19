"""Ponte opt-in para subagentes: sem registro automático no orquestrador.

O chamador confiável deve autenticar o proprietário e decidir a autorização
fora dos parâmetros produzidos pelo modelo. Conteúdo de arquivos e pareceres
visuais permanecem dados não confiáveis, nunca instruções de sistema.
"""
import json
import re

from src.tools.file_analysis.contracts import FILE_ID, FileRejected

VERSION = "1.0.0"
TOOLS = frozenset({"files.context", "vision.inspect"})
SHA256 = re.compile(r"^[a-f0-9]{64}$")


def capabilities():
    """Descreve ferramentas disponíveis, sem prometer disponibilidade do modelo."""
    return {
        "version": VERSION,
        "tools": {
            name: {"arguments": ["file_id", "question"],
                   "requires_trusted_authorization": True,
                   "model_may_authorize": False,
                   "returns_untrusted_content": True}
            for name in sorted(TOOLS)
        },
        "ocr": "not_registered_pending_integration",
    }


def _result(tool, status, *, code=None, data=None):
    value = {"tool": tool if isinstance(tool, str) and tool in TOOLS else None,
             "bridge_version": VERSION,
             "status": status, "authorized_execution": status == "executed",
             "untrusted_content": True, "data": data or {}}
    if code:
        value["error"] = {"code": code}
    return value


def _context_data(receipt, file_id):
    """Projetar somente evidência e texto limitados; não confiar em campos extras."""
    info, items = receipt.get("file"), receipt.get("items")
    if (receipt.get("grounded") is not True or not isinstance(info, dict)
            or info.get("id") != file_id or not isinstance(info.get("sha256"), str)
            or not SHA256.fullmatch(info["sha256"]) or not isinstance(items, list)
            or info.get("format") not in {"pdf", "docx", "xlsx", "csv", "text", "markdown"}
            or not 1 <= len(items) <= 6):
        return None
    selected = []
    for item in items:
        if not isinstance(item, dict):
            return None
        text, citation, anchor = item.get("text"), item.get("citation"), item.get("anchor")
        if (not isinstance(text, str) or not 1 <= len(text) <= 1100
                or not isinstance(citation, str) or len(citation) > 256
                or not citation.startswith(f"file:{file_id}:")
                or not isinstance(anchor, dict) or len(anchor) > 8):
            return None
        try:
            if len(json.dumps(anchor, ensure_ascii=False)) > 512:
                return None
        except (TypeError, ValueError):
            return None
        selected.append({"text": text, "citation": citation, "anchor": anchor,
                         "source": "ocr" if item.get("source") == "ocr" else "extracted"})
    if sum(len(item["text"]) for item in selected) > 4000:
        return None
    return {
        "file": {"file_id": file_id, "sha256": info["sha256"],
                 "format": str(info.get("format", ""))[:16]},
        "items": selected,
        "source_truncated": receipt.get("source_truncated") is True,
        "selection_truncated": receipt.get("selection_truncated") is True,
        "content_kind": "mixed_or_ocr_text" if any(x["source"] == "ocr" for x in selected)
                        else "extracted_text",
        "provenance": "source_locator_not_truth_verification",
        "semantic_verified": False,
    }


def _vision_data(receipt, file_id):
    if (receipt.get("file_id") != file_id or receipt.get("quality_status")
            != "unverified_model_assessment"):
        return None
    validation, assessment, evidence = (receipt.get("validation"),
                                        receipt.get("assessment"), receipt.get("evidence"))
    if (not isinstance(validation, dict) or validation.get("semantic_verified") is not False
            or not isinstance(assessment, dict) or not isinstance(evidence, list)
            or len(evidence) != 1 or not isinstance(evidence[0], dict)):
        return None
    proof = evidence[0]
    dimensions = proof.get("dimensions")
    if (proof.get("kind") != "technical_image"
            or not isinstance(proof.get("sha256"), str) or not SHA256.fullmatch(proof["sha256"])
            or not isinstance(dimensions, list) or len(dimensions) != 2
            or any(type(n) is not int or not 1 <= n <= 24000 for n in dimensions)):
        return None
    observations = assessment.get("observations")
    inferences = assessment.get("inferences")
    answer = assessment.get("answer")
    uncertainty = assessment.get("uncertainty")
    if (not isinstance(observations, list) or len(observations) > 8
            or not isinstance(inferences, list) or len(inferences) > 5
            or any(not isinstance(t, str) or not 1 <= len(t) <= 300 for t in observations + inferences)
            or not isinstance(answer, str) or not 1 <= len(answer) <= 650
            or not isinstance(uncertainty, str) or len(uncertainty) > 300):
        return None
    return {
        "file": {"file_id": file_id, "sha256": proof["sha256"]},
        "dimensions": dimensions,
        "assessment": {"observations": observations, "inferences": inferences,
                       "answer": answer, "uncertainty": uncertainty},
        "content_kind": "unverified_model_assessment",
        "semantic_verified": False,
    }


def invoke(tool, arguments, *, authorized=False, root=None):
    """Executa apenas após autorização do código chamador, nunca do LLM.

    authorized e root são parâmetros keyword-only exclusivos do runtime
    confiável. Não passar valores de ambos vindos do JSON do modelo.
    """
    if not isinstance(tool, str) or tool not in TOOLS:
        return _result(tool, "unsupported", code="tool_not_registered")
    if authorized is not True:
        return _result(tool, "denied", code="trusted_authorization_required")
    if (not isinstance(arguments, dict) or set(arguments) != {"file_id", "question"}
            or not isinstance(arguments.get("file_id"), str)
            or FILE_ID.fullmatch(arguments["file_id"]) is None
            or not isinstance(arguments.get("question"), str)
            or not 1 <= len(arguments["question"].strip()) <= 500):
        return _result(tool, "invalid_arguments", code="invalid_tool_arguments")
    file_id, question = arguments["file_id"], arguments["question"].strip()
    try:
        if tool == "files.context":
            from src.tools.file_analysis.context import retrieve
            receipt = retrieve(file_id, question, max_chars=4000, max_items=6, root=root)
        else:
            from src.tools.vision import inspect_image
            receipt = inspect_image(file_id, question, root=root)
    except FileRejected:
        return _result(tool, "failed", code="private_file_invalid_or_missing")
    except (ValueError, OSError, RuntimeError):
        return _result(tool, "failed", code="local_tool_unavailable")
    if not isinstance(receipt, dict) or receipt.get("tool") != tool:
        return _result(tool, "failed", code="invalid_tool_receipt")
    status = receipt.get("status")
    if status == "executed":
        data = (_context_data(receipt, file_id) if tool == "files.context"
                else _vision_data(receipt, file_id))
        if data is None:
            return _result(tool, "failed", code="invalid_tool_receipt")
        return _result(tool, "executed", data=data)
    allowed = ({"failed", "unsupported", "no_text"} if tool == "files.context"
               else {"failed", "unavailable"})
    if status in allowed:
        return _result(tool, status, code="no_verified_content")
    return _result(tool, "failed", code="invalid_tool_receipt")
