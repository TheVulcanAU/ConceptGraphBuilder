"""
Splits source text into overlapping chunks that respect paragraph boundaries.

Strategy:
- Split on double-newlines (paragraph breaks) first.
- Accumulate paragraphs until a soft token limit is reached.
- Carry the last paragraph of each chunk into the next (overlap) so extraction
  has context for relationships that straddle a boundary.
"""

import re
from dataclasses import dataclass

# Rough chars-per-token estimate; conservative so chunks stay within LLM limits.
CHARS_PER_TOKEN = 4
SOFT_TOKEN_LIMIT = 1800   # target chunk size in tokens
OVERLAP_PARAGRAPHS = 1    # paragraphs to repeat at the start of the next chunk


@dataclass
class Chunk:
    index: int
    text: str
    char_start: int  # approximate position in original text


def _split_paragraphs(text: str) -> list[str]:
    """Split on blank lines; strip empty strings and whitespace-only entries."""
    paragraphs = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paragraphs if p.strip()]


def chunk_text(text: str) -> list[Chunk]:
    """
    Returns a list of Chunk objects. Each chunk is a window of consecutive
    paragraphs sized to stay under SOFT_TOKEN_LIMIT, with one paragraph of
    overlap between adjacent chunks.
    """
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return []

    chunks: list[Chunk] = []
    current: list[str] = []
    current_tokens = 0
    char_cursor = 0
    chunk_index = 0

    for para in paragraphs:
        para_tokens = len(para) // CHARS_PER_TOKEN

        if current and current_tokens + para_tokens > SOFT_TOKEN_LIMIT:
            chunk_text_str = "\n\n".join(current)
            chunks.append(Chunk(index=chunk_index, text=chunk_text_str, char_start=char_cursor))
            chunk_index += 1
            # carry overlap: keep last N paragraphs
            overlap = current[-OVERLAP_PARAGRAPHS:]
            overlap_tokens = sum(len(p) // CHARS_PER_TOKEN for p in overlap)
            current = overlap
            current_tokens = overlap_tokens

        current.append(para)
        current_tokens += para_tokens

    if current:
        chunk_text_str = "\n\n".join(current)
        chunks.append(Chunk(index=chunk_index, text=chunk_text_str, char_start=char_cursor))

    return chunks


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract plain text from PDF bytes using PyMuPDF."""
    import fitz  # PyMuPDF
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for page in doc:
        pages.append(page.get_text())
    return "\n\n".join(pages)
