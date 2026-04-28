"""Stage 5: rule-based chunking (headings + sentence overlap) → Chunk models."""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Optional

from app.config import get_settings
from app.models import Chunk, CleanedPage

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


def _is_heading_line(line: str) -> bool:
    """
    Heuristic: 2–15 từ, không kết thúc bằng . , ; : ! ?, từ đầu viết hoa,
    không chứa dấu chấm/phẩy trong dòng.
    """
    line = line.strip()
    if not line:
        return False
    if any(ch in line for ch in ".,;"):
        return False
    if line[-1] in ".?!:;":
        return False
    words = line.split()
    n = len(words)
    if n < 2 or n > 15:
        return False
    first = words[0]
    if not first or not first[0].isupper():
        return False
    return True


def _lines_to_sections(text: str) -> list[tuple[Optional[str], str]]:
    """(section_heading, body) — body gồm các dòng nội dung ghép bằng \\n."""
    sections: list[tuple[Optional[str], str]] = []
    heading: Optional[str] = None
    body_lines: list[str] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _is_heading_line(line):
            if body_lines:
                body = "\n".join(body_lines).strip()
                if body:
                    sections.append((heading, body))
                body_lines = []
            heading = line
        else:
            body_lines.append(line)

    if body_lines:
        body = "\n".join(body_lines).strip()
        if body:
            sections.append((heading, body))
    return sections


def _split_into_sentences(paragraph: str) -> list[str]:
    paragraph = re.sub(r"\s+", " ", paragraph.strip())
    if not paragraph:
        return []
    parts = _SENTENCE_SPLIT_RE.split(paragraph)
    return [p.strip() for p in parts if p.strip()]


def _split_oversized_sentence(sentence: str, max_words: int) -> list[str]:
    words = sentence.split()
    if not words:
        return []
    if len(words) <= max_words:
        return [sentence]
    return [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]


def _expand_sentences(body: str, max_words: int) -> list[str]:
    out: list[str] = []
    for para in body.split("\n"):
        para = para.strip()
        if not para:
            continue
        for s in _split_into_sentences(para):
            out.extend(_split_oversized_sentence(s, max_words))
    return out


def _chunk_body_to_pieces(
    body: str,
    *,
    max_words: int,
    min_words: int,
    overlap_sentences: int,
) -> list[str]:
    sentences = _expand_sentences(body, max_words)
    if not sentences:
        return []

    chunks: list[str] = []
    current: list[str] = []
    word_count = 0

    for s in sentences:
        sw = len(s.split())
        if word_count + sw > max_words and current:
            chunks.append(" ".join(current).strip())
            if overlap_sentences > 0 and len(current) >= overlap_sentences:
                ov = current[-overlap_sentences:]
            elif overlap_sentences > 0:
                ov = current[:]
            else:
                ov = []
            current = ov + [s]
            word_count = sum(len(x.split()) for x in current)
        else:
            current.append(s)
            word_count += sw

    if current:
        chunks.append(" ".join(current).strip())

    return _merge_short_chunks(chunks, min_words)


def _merge_short_chunks(chunks: list[str], min_words: int) -> list[str]:
    if not chunks:
        return []
    out: list[str] = []
    for c in chunks:
        wc = len(c.split())
        if wc < min_words:
            if out:
                out[-1] = (out[-1] + " " + c).strip()
        else:
            out.append(c)
    return out


def _chunk_id(url: str, index: int, text: str) -> str:
    h = hashlib.sha256(f"{url}\0{index}\0{text}".encode("utf-8")).hexdigest()
    return h[:12]


def chunk_text(clean_text: str) -> list[str]:
    """Chỉ trả các đoạn text (gộp mọi section); tham số size lấy từ Settings."""
    settings = get_settings()
    sections = _lines_to_sections(clean_text)
    out: list[str] = []
    for _heading, body in sections:
        if not body.strip():
            continue
        out.extend(
            _chunk_body_to_pieces(
                body,
                max_words=settings.CHUNK_MAX_WORDS,
                min_words=settings.CHUNK_MIN_WORDS,
                overlap_sentences=settings.CHUNK_OVERLAP_SENTENCES,
            )
        )
    return out


def enrich_chunks(
    cleaned: CleanedPage,
    section_text_pairs: list[tuple[Optional[str], str]],
) -> list[Chunk]:
    """Gán metadata cố định + chunk_id + chunk_index theo schema Chunk."""
    non_empty = [(sh, t.strip()) for sh, t in section_text_pairs if t.strip()]
    chunks: list[Chunk] = []
    for i, (section_heading, text) in enumerate(non_empty):
        chunks.append(
            Chunk(
                chunk_id=_chunk_id(str(cleaned.url), i, text),
                source_url=cleaned.url,
                page_title=cleaned.title,
                section_heading=section_heading,
                text=text,
                word_count=len(text.split()),
                crawled_at=cleaned.crawled_at,
                chunk_index=i,
            )
        )
    return chunks


def chunk_cleaned_page(cleaned: CleanedPage) -> list[Chunk]:
    """Từ CleanedPage → list[Chunk] (section theo heading + chunk theo từ + overlap câu)."""
    settings = get_settings()
    sections = _lines_to_sections(cleaned.text)
    pairs: list[tuple[Optional[str], str]] = []
    for heading, body in sections:
        if not body.strip():
            continue
        for piece in _chunk_body_to_pieces(
            body,
            max_words=settings.CHUNK_MAX_WORDS,
            min_words=settings.CHUNK_MIN_WORDS,
            overlap_sentences=settings.CHUNK_OVERLAP_SENTENCES,
        ):
            pairs.append((heading, piece))
    chunks = enrich_chunks(cleaned, pairs)
    logger.info(
        "chunk_cleaned_page url=%s sections=%d chunks=%d",
        cleaned.url,
        len(sections),
        len(chunks),
    )
    return chunks
