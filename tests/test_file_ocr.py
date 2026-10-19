"""OCR opcional: isolamento, limites, regressões de API e amostra real escaneada."""
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image, ImageDraw, ImageFont
try:
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen.canvas import Canvas
except ImportError:
    ImageReader = None
    Canvas = None

from src.tools.file_analysis import ocr, ocr_worker, service
from src.tools.file_analysis.contracts import FileRejected
from test_file_api import request
from test_auth_memory import call
from src.security import auth


def scanned_pdf(label="MENOR 42"):
    if Canvas is None:
        raise unittest.SkipTest("ReportLab opcional não instalado para fixtures OCR.")
    image = Image.new("RGB", (1050, 300), "white")
    draw = ImageDraw.Draw(image)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if os.path.isfile(font_path):
        font = ImageFont.truetype(font_path, 90)
    else:
        font = ImageFont.load_default()
    draw.text((40, 60), label, font=font, fill="black")
    output = io.BytesIO()
    canvas = Canvas(output, pagesize=(600, 400))
    canvas.drawImage(ImageReader(image), 50, 100, width=500, height=150)
    canvas.showPage()
    canvas.save()
    return output.getvalue()


def get_receipt(pdf=None):
    folder = tempfile.TemporaryDirectory()
    root = Path(folder.name) / "data"
    stored = service.ingest(pdf or scanned_pdf(), "scan.pdf", root=root)
    return folder, root, stored["file"]["file_id"]


class OCRContractsTests(unittest.TestCase):
    def test_detects_missing_executables_without_installing(self):
        with patch("src.tools.file_analysis.ocr.shutil.which", return_value=None):
            s = ocr.status()
        self.assertEqual(s["status"], "missing_dependency")
        self.assertFalse(s["installed"])
        self.assertFalse(s["quality_validated"])

    @patch("src.tools.file_analysis.ocr.subprocess.run")
    @patch("src.tools.file_analysis.ocr.shutil.which", return_value="/usr/bin/tesseract")
    def test_language_requirements_not_faked(self, _which, run):
        run.return_value = MagicMock(returncode=0, stdout=b"List of available languages\neng\n", stderr=b"")
        s = ocr.status("por")
        self.assertEqual(s["status"], "missing_language")
        self.assertEqual(ocr.status("eng")["status"], "dependencies_detected")
        self.assertFalse(ocr.status("eng")["operational"])

    def test_no_arbitrary_paths_page_numbers_or_languages(self):
        for file_id, page, language in [
            ("../../etc/passwd", 1, "eng"), ("a" * 32, 0, "eng"),
            ("a" * 32, 41, "eng"), ("a" * 32, True, "eng"),
            ("a" * 32, 1, "eng;rm -rf"), ("a" * 32, 1, "auto"),
        ]:
            with self.subTest(file_id=file_id, page=page, language=language):
                with self.assertRaises((ValueError, FileRejected)):
                    ocr.ocr_page(file_id, page, language)

    def test_missing_dependencies_return_unavailable_and_no_ocr(self):
        folder, root, token = get_receipt()
        self.addCleanup(folder.cleanup)
        with patch("src.tools.file_analysis.ocr.status",
                   return_value={"status": "missing_dependency", "installed": False}):
            with patch("src.tools.file_analysis.ocr.subprocess.run") as run:
                result = ocr.ocr_page(token, language="eng", root=root)
                run.assert_not_called()
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["validation"]["ocr_quality_verified"])

    def test_pdf_wrong_format_rejected_before_model_or_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            text_id = service.ingest(b"not a PDF", "note.txt", root=root)["file"]["file_id"]
            with self.assertRaises(FileRejected):
                ocr.ocr_page(text_id, root=root)

    def test_worker_never_uses_external_path_or_untrusted_language(self):
        with self.assertRaises(ValueError):
            ocr_worker.run(1, "eng; echo x", b"%PDF-1.4")
        with self.assertRaises(ValueError):
            ocr_worker.run(0, "eng", b"%PDF-1.4")
        with self.assertRaises(ValueError):
            ocr_worker.run(1, "eng", b"not pdf")

    def test_ocr_worker_receipt_and_timeouts_fail_closed(self):
        folder, root, token = get_receipt()
        self.addCleanup(folder.cleanup)
        with patch("src.tools.file_analysis.ocr.status",
                   return_value={"installed": True, "status": "dependencies_detected"}):
            with patch("src.tools.file_analysis.ocr.service.inspect", return_value={
                "status": "executed", "metadata": {"pages_total": 1},
            }):
                import subprocess
                with patch("src.tools.file_analysis.ocr.subprocess.run",
                           side_effect=subprocess.TimeoutExpired("worker", 1)):
                    result = ocr.ocr_page(token, root=root)
                    self.assertEqual(result["status"], "failed")
                    self.assertEqual(result["error"]["code"], "timeout")
                    self.assertEqual(result["evidence"], [])
                with patch("src.tools.file_analysis.ocr.subprocess.run") as run:
                    run.return_value = MagicMock(returncode=0, stdout=json.dumps({
                        "status": "executed", "page": 1, "text": "Texto OCR incerto",
                    }).encode(), stderr=b"")
                    result = ocr.ocr_page(token, root=root)
                    self.assertEqual(result["status"], "executed")
                    self.assertEqual(result["text"], "Texto OCR incerto")
                    self.assertEqual(result["evidence"][0]["page"], 1)
                    self.assertFalse(result["validation"]["ocr_quality_verified"])
                    self.assertNotIn("HOME", run.call_args.kwargs["env"])
                    self.assertTrue(run.call_args.kwargs["input"].startswith(b"%PDF-"))


class OCRRouteTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.env = patch.dict(os.environ, {"MENOR_DATA_DIR": tmp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        auth._attempts.clear()
        status, _, headers = call("/auth/setup", {"password": "senha-segura-para-OCR"})
        self.assertEqual(status, 200)
        self.cookie = headers[b"set-cookie"].decode().split(";", 1)[0]

    def test_ocr_status_auth_and_fail_closed(self):
        self.assertEqual(request("GET", "/files/ocr/status")[0], 401)
        with patch("src.tools.file_analysis.api.ocr.status",
                   return_value={"status": "missing_dependency", "installed": False}):
            code, state = request("GET", "/files/ocr/status", cookie=self.cookie)
        self.assertEqual(code, 200)
        self.assertFalse(state["installed"])

    def test_ocr_route_auth_origin_page_and_pending_dependency(self):
        item = service.ingest(scanned_pdf(), "sample.pdf")
        token = item["file"]["file_id"]
        url = f"/files/{token}/ocr"
        payload = b'{"page":1,"language":"eng"}'
        self.assertEqual(request("POST", url, payload, content_type="application/json")[0], 401)
        self.assertEqual(request("POST", url, payload, cookie=self.cookie,
                                 content_type="application/json",
                                 origin="https://evil.example")[0], 403)
        self.assertEqual(request("POST", url, b'{"page":41,"language":"eng"}',
                                 cookie=self.cookie, content_type="application/json")[0], 422)
        with patch("src.tools.file_analysis.api.ocr.ocr_page",
                   return_value={"status": "unavailable", "reason": "not_installed"}):
            code, output = request("POST", url, payload, cookie=self.cookie,
                                   content_type="application/json")
        self.assertEqual(code, 503)
        self.assertEqual(output["status"], "unavailable")

    def test_ocr_api_receipt_and_wrong_file_type(self):
        token = service.ingest(b"hello", "hello.txt")["file"]["file_id"]
        url = f"/files/{token}/ocr"
        with patch("src.tools.file_analysis.api.ocr.ocr_page",
                   side_effect=FileRejected("only PDF")):
            code, _ = request("POST", url, b'{"page":1}', cookie=self.cookie,
                              content_type="application/json")
        self.assertEqual(code, 404)


@unittest.skipUnless(os.environ.get("MENOR_OCR_E2E") == "1",
                     "OCR real somente em CI com Poppler + Tesseract instalados")
class RealOCRTests(unittest.TestCase):
    def test_one_scanned_pdf_page_with_known_reference(self):
        if not shutil.which("pdftoppm") or not shutil.which("tesseract"):
            self.skipTest("OCR binaries absent")
        folder, root, token = get_receipt()
        self.addCleanup(folder.cleanup)
        result = ocr.ocr_page(token, page=1, language="eng", root=root)
        self.assertEqual(result["status"], "executed", result)
        self.assertIn("MENOR", result["text"].upper())
        self.assertEqual(result["page"], 1)
        self.assertFalse(result["validation"]["ocr_quality_verified"])
        self.assertEqual(result["evidence"][0]["kind"], "ocr_pdf_page")


if __name__ == "__main__":
    unittest.main()
