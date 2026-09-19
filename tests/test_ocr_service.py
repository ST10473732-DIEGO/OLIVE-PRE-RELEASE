import unittest
from pathlib import Path
from unittest.mock import patch

from olive.services.ocr_service import OCRResult, OCRService, clean_ocr_text, is_ocr_candidate, parse_tesseract_tsv
from olive.services.document_service import DocumentService, _remove_repeated_page_margins
from olive.utils.chunking import TextPage


class OCRServiceTests(unittest.TestCase):
    def test_scanned_page_detection_requires_image_and_little_text(self):
        self.assertTrue(is_ocr_candidate("Page 1", 1))
        self.assertFalse(is_ocr_candidate("A" * 100, 1))
        self.assertFalse(is_ocr_candidate("", 0))

    def test_unavailable_ocr_has_manual_install_guidance(self):
        service = OCRService(executable="")
        service.executable = None
        self.assertFalse(service.available)
        self.assertIn("Tesseract", service.installation_hint)

    def test_cleanup_is_conservative(self):
        self.assertEqual(clean_ocr_text("  Alpha   beta\n\n\n Gamma "), "Alpha beta\n\nGamma")

    def test_tsv_preserves_lines_and_computes_confidence(self):
        value = "page_num\tblock_num\tpar_num\tline_num\tconf\ttext\n1\t1\t1\t1\t90\tHello\n1\t1\t1\t1\t80\tworld\n"
        text, confidence = parse_tesseract_tsv(value)
        self.assertEqual(text, "Hello world")
        self.assertEqual(confidence, 85.0)

    def test_pdf_page_uses_ocr_with_correct_page_provenance(self):
        class OCR:
            available = True
            def recognize(self, path): return OCRResult("recognized page", 0.88)
        class Image:
            def save(self, *args, **kwargs): pass
        class Page:
            images = [object()]
            def extract_text(self): return ""
            def extract_tables(self): return []
            def to_image(self, resolution): return Image()
        class PDF:
            pages = [Page()]
            def __enter__(self): return self
            def __exit__(self, *args): pass
        with patch("olive.services.document_service.pdfplumber.open", return_value=PDF()):
            pages = DocumentService(OCR())._extract_pdf(Path("scan.pdf"))
        self.assertEqual(pages[0].text, "recognized page")
        self.assertEqual(pages[0].page_number, 1)
        self.assertEqual(pages[0].origin_type, "ocr")
        self.assertEqual(pages[0].confidence, 0.88)

    def test_exact_repeated_headers_and_footers_are_removed_conservatively(self):
        pages = [TextPage(f"Company Manual\nUnique body {i}\nConfidential", i) for i in range(1, 4)]
        cleaned = _remove_repeated_page_margins(pages)
        self.assertEqual(cleaned[0].text, "Unique body 1")
        self.assertEqual(cleaned[0].page_number, 1)


if __name__ == "__main__": unittest.main()
