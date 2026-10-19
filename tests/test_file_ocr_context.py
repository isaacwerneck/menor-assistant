"""OCR contextual explicitamente solicitado, com proveniência por página."""
import unittest
from unittest.mock import patch

from src.tools.file_analysis.context import retrieve

ID = "a" * 32
HASH = "b" * 64


def document(text=""):
    return {"status": "executed", "file": {"file_id": ID, "filename": "scan.pdf",
            "sha256": HASH, "format": "pdf"},
            "content": [{"type": "page", "page": 1, "text": text}]}


def ocr_result(text="Prazo de entrega sexta-feira"):
    return {"status": "executed", "file": {"file_id": ID, "sha256": HASH},
            "page": 1, "language": "por", "text": text,
            "validation": {"file_verified": True, "ocr_quality_verified": False}}


class OcrContextTests(unittest.TestCase):
    @patch("src.tools.file_analysis.context.service.inspect")
    @patch("src.tools.file_analysis.ocr.ocr_page")
    def test_ocr_only_when_requested(self, ocr, inspect):
        inspect.return_value = document()
        ocr.return_value = ocr_result()
        self.assertEqual(retrieve(ID, "Prazo")["status"], "no_text")
        ocr.assert_not_called()
        result = retrieve(ID, "Prazo", ocr_page=1)
        self.assertEqual(result["status"], "executed")
        self.assertTrue(result["ocr_used"])
        self.assertEqual(result["file"]["sha256"], HASH)
        self.assertEqual(result["items"][0]["source"], "ocr")
        self.assertEqual(result["items"][0]["citation"], f"file:{ID}:ocr:page:1:0")
        self.assertFalse(result["items"][0]["anchor"]["ocr_quality_verified"])

    @patch("src.tools.file_analysis.context.service.inspect")
    @patch("src.tools.file_analysis.ocr.ocr_page")
    def test_mixed_sources_never_conflate(self, ocr, inspect):
        inspect.return_value = document("Contrato assinado.")
        ocr.return_value = ocr_result("Valor total 400.")
        result = retrieve(ID, "Contrato valor", ocr_page=1)
        self.assertEqual({x["source"] for x in result["items"]}, {"ocr", "extracted"})
        self.assertEqual(len({x["citation"] for x in result["items"]}), 2)

    @patch("src.tools.file_analysis.context.service.inspect")
    @patch("src.tools.file_analysis.ocr.ocr_page")
    def test_invalid_ocr_hash_is_not_cited(self, ocr, inspect):
        inspect.return_value = document()
        ocr.return_value = ocr_result()
        ocr.return_value["file"]["sha256"] = "0" * 64
        result = retrieve(ID, "Prazo", ocr_page=1)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["grounded"])

    @patch("src.tools.file_analysis.context.service.inspect")
    @patch("src.tools.file_analysis.ocr.ocr_page")
    def test_ocr_failure_does_not_claim_grounding(self, ocr, inspect):
        inspect.return_value = document()
        ocr.return_value = {"status": "unavailable"}
        result = retrieve(ID, "Prazo", ocr_page=1)
        self.assertEqual(result["status"], "ocr_unavailable")
        self.assertFalse(result["grounded"])

    @patch("src.tools.file_analysis.context.service.inspect")
    def test_reject_invalid_page_before_parsing(self, inspect):
        for page in (0, 41, True, "1"):
            with self.assertRaises(ValueError):
                retrieve(ID, "Prazo", ocr_page=page)
        inspect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
