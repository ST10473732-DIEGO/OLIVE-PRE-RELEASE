import unittest

from olive.utils.chunking import TextPage, chunk_pages


class ChunkingTests(unittest.TestCase):
    def test_keeps_page_number(self):
        chunks = chunk_pages([TextPage("Alpha paragraph.\n\nBeta paragraph.", 7)], target_chars=20, overlap_chars=5)
        self.assertTrue(chunks)
        self.assertTrue(all(c.page_number == 7 for c in chunks))

    def test_long_text_splits(self):
        text = "word " * 1000
        chunks = chunk_pages([TextPage(text, 1)], target_chars=300, overlap_chars=50)
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(c.text for c in chunks))

    def test_preserves_ocr_page_provenance(self):
        chunks = chunk_pages([TextPage("Recognized page text", 12, "ocr", 0.91)])
        self.assertEqual(chunks[0].page_number, 12)
        self.assertEqual(chunks[0].origin_type, "ocr")
        self.assertEqual(chunks[0].confidence, 0.91)


if __name__ == "__main__":
    unittest.main()
