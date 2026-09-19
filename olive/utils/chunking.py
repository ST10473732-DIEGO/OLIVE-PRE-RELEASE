from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TextPage:
    text: str
    page_number: int | None = None
    origin_type: str = "native_text"
    confidence: float | None = None


@dataclass(slots=True)
class TextChunk:
    text: str
    page_number: int | None
    chunk_index: int
    origin_type: str = "native_text"
    confidence: float | None = None


def chunk_pages(
    pages: list[TextPage],
    target_chars: int = 1800,
    overlap_chars: int = 250,
) -> list[TextChunk]:
    """Chunk page-aware text without cutting every paragraph at arbitrary positions."""
    chunks: list[TextChunk] = []
    chunk_index = 0
    for page in pages:
        paragraphs = [p.strip() for p in page.text.replace("\r\n", "\n").split("\n\n") if p.strip()]
        if not paragraphs and page.text.strip():
            paragraphs = [page.text.strip()]
        current = ""
        for paragraph in paragraphs:
            if len(paragraph) > target_chars * 2:
                if current:
                    chunks.append(TextChunk(current.strip(), page.page_number, chunk_index,
                                            page.origin_type, page.confidence))
                    chunk_index += 1
                    current = ""
                for part in _sliding_windows(paragraph, target_chars, overlap_chars):
                    chunks.append(TextChunk(part.strip(), page.page_number, chunk_index,
                                            page.origin_type, page.confidence))
                    chunk_index += 1
                continue

            proposed = paragraph if not current else f"{current}\n\n{paragraph}"
            if len(proposed) <= target_chars:
                current = proposed
            else:
                if current:
                    chunks.append(TextChunk(current.strip(), page.page_number, chunk_index,
                                            page.origin_type, page.confidence))
                    chunk_index += 1
                    tail = current[-overlap_chars:].strip() if overlap_chars else ""
                    current = f"{tail}\n\n{paragraph}" if tail else paragraph
                else:
                    current = paragraph
        if current.strip():
            chunks.append(TextChunk(current.strip(), page.page_number, chunk_index,
                                    page.origin_type, page.confidence))
            chunk_index += 1
    return chunks


def _sliding_windows(text: str, size: int, overlap: int):
    if size <= 0:
        yield text
        return
    step = max(1, size - max(0, overlap))
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        yield text[start:end]
        if end >= len(text):
            break
        start += step
