import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from olive.models import Chat, DocumentRef
from olive.services.document_service import DocumentService


class DocumentServiceTests(unittest.TestCase):
    def test_mixed_pdf_retains_actual_page_numbers_and_missing_text_metadata(self):
        from scripts.create_deep_pdf_fixture import create
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'mixed.pdf';create(path)
            # Deliberately unavailable OCR: extraction and PDF decoding are real.
            service=DocumentService(ocr=SimpleNamespace(available=False),cache_dir=Path(tmp)/'cache')
            result=service.extract(path,'fixture-chat')
            self.assertEqual(result.ref.page_count,2)
            self.assertEqual(result.ref.unreadable_pages,[2])
            self.assertEqual({chunk['page_number'] for chunk in result.chunks},{1})
            self.assertIn('12',result.chunks[0]['content'])
            self.assertEqual(DocumentRef.from_dict(result.ref.to_dict()).unreadable_pages,[2])
            self.assertEqual(DocumentRef.from_dict({'id':'legacy','name':'old.pdf'}).unreadable_pages,[])
            from pypdf import PdfReader,PdfWriter
            writer=PdfWriter();writer.add_page(PdfReader(path).pages[1]);scan=Path(tmp)/'scan.pdf';writer.write(scan)
            scanned=service.extract(scan,'fixture-chat')
            self.assertEqual(scanned.ref.unreadable_pages,[1]);self.assertEqual(scanned.chunks,[])
    def test_ingests_supported_text_formats_as_chunks(self):
        service = DocumentService()
        with tempfile.TemporaryDirectory() as tmp:
            for suffix, content in {
                ".txt": "alpha text", ".md": "# heading\n\nbody", ".py": "print('hello')",
                ".json": '{"local": true}', ".csv": "name,value\na,1",
            }.items():
                path = Path(tmp) / f"sample{suffix}"
                path.write_text(content, encoding="utf-8")
                with patch("olive.services.document_service.cache_file", return_value=path):
                    extracted = service.extract(path, "chat-id")
                self.assertTrue(extracted.chunks, suffix)
                self.assertEqual(extracted.chunks[0]["document_name"], path.name)
                self.assertNotIn("content", extracted.ref.to_dict())

    def test_temporary_documents_are_not_serialized_into_chat_history(self):
        chat = Chat(documents=[
            DocumentRef("temporary", "temp.txt", temporary=True),
            DocumentRef("permanent", "manual.pdf"),
        ])
        documents = chat.to_dict()["documents"]
        self.assertEqual([item["id"] for item in documents], ["permanent"])


if __name__ == "__main__":
    unittest.main()
