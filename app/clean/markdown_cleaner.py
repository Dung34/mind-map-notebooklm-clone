"""Stage 4: markdown → plain text (strip, block filter, dedup)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.config import get_settings
from app.models import CleanedPage, RawPage

logger = logging.getLogger(__name__)

# --- strip_markdown ---

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_MD_HEADING_RE = re.compile(r"(?m)^#{1,6}\s+")
_MD_BLOCKQUOTE_RE = re.compile(r"(?m)^>\s?")
_MD_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")
_MD_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_MD_HRULE_RE = re.compile(r"(?m)^[\s*\-_]{3,}\s*$")
_MD_BULLET_RE = re.compile(r"(?m)^[\*\-+]\s+")
_MD_ENUM_RE = re.compile(r"(?m)^\d+\.\s+")
_BARE_URL_RE = re.compile(r"https?://\S+")
_WS_RUN_RE = re.compile(r"[ \t]+")
_NL_RUN_RE = re.compile(r"\n{3,}")


def strip_markdown(raw: str) -> str:
    """Remove markdown/HTML noise; unwrap links; normalize whitespace."""
    if not raw or not raw.strip():
        return ""

    text = raw
    text = _MD_CODE_FENCE_RE.sub(" ", text)
    text = _MD_INLINE_CODE_RE.sub(r"\1", text)
    text = _MD_IMAGE_RE.sub(" ", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = _MD_HEADING_RE.sub("", text)
    text = _MD_BLOCKQUOTE_RE.sub("", text)
    text = _MD_HRULE_RE.sub(" ", text)
    text = _MD_BULLET_RE.sub("", text)
    text = _MD_ENUM_RE.sub("", text)
    text = _BARE_URL_RE.sub(" ", text)
    text = _WS_RUN_RE.sub(" ", text)
    text = _NL_RUN_RE.sub("\n\n", text)
    return text.strip()


# --- filter_blocks ---

_MIN_WORDS_SHORT_LINE = 5
_NAV_LINE_FRACTION = 0.6
_MIN_BLOCK_WORDS = 5
_MAX_BOILERPLATE_BLOCK_WORDS = 35

_BOILERPLATE_RE = re.compile(
    r"\b("
    r"learn more|read more|click here|see more|find out more|"
    r"privacy policy|terms of (use|service)|terms and conditions|"
    r"cookie policy|all rights reserved|"
    r"đăng nhập|đăng ký|đăng kí|"
    r"sign in|log in|sign up|register|subscribe|newsletter|"
    r"follow us|share on|contact us|get in touch"
    r")\b",
    re.IGNORECASE,
)


def _split_blocks(text: str) -> list[str]:
    return [b.strip() for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]


def _block_word_count(block: str) -> int:
    return len(block.split())


def _is_nav_block(block: str) -> bool:
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    if not lines:
        return False
    short = sum(1 for ln in lines if len(ln.split()) < _MIN_WORDS_SHORT_LINE)
    return (short / len(lines)) >= _NAV_LINE_FRACTION


def _is_boilerplate_block(block: str) -> bool:
    if not _BOILERPLATE_RE.search(block):
        return False
    return _block_word_count(block) <= _MAX_BOILERPLATE_BLOCK_WORDS


def filter_blocks(text: str) -> str:
    """Drop nav-like, boilerplate, and very short blocks (blank-line separated)."""
    blocks = _split_blocks(text)
    kept: list[str] = []
    for b in blocks:
        if _is_nav_block(b):
            continue
        if _block_word_count(b) < _MIN_BLOCK_WORDS:
            continue
        if _is_boilerplate_block(b):
            continue
        kept.append(b)
    return "\n\n".join(kept)


# --- dedup_blocks ---


def dedup_blocks(text: str) -> str:
    """Remove consecutive duplicate blocks (normalized: lower + collapsed spaces)."""
    blocks = _split_blocks(text)
    seen: set[str] = set()
    out: list[str] = []
    for b in blocks:
        key = " ".join(b.lower().split())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(b)
    return "\n\n".join(out)


# --- compose + RawPage adapter ---


def clean_markdown(raw_markdown: str) -> str:
    """strip_markdown → filter_blocks → dedup_blocks."""
    t = strip_markdown(raw_markdown)
    t = filter_blocks(t)
    t = dedup_blocks(t)
    return t.strip()


@dataclass(frozen=True)
class CleanMarkdownStats:
    blocks_after_strip: int
    blocks_after_filter: int
    blocks_after_dedup: int


def clean_markdown_with_stats(raw_markdown: str) -> tuple[str, CleanMarkdownStats]:
    s1 = strip_markdown(raw_markdown)
    n0 = len(_split_blocks(s1)) if s1 else 0
    s2 = filter_blocks(s1)
    n1 = len(_split_blocks(s2)) if s2 else 0
    s3 = dedup_blocks(s2)
    n2 = len(_split_blocks(s3)) if s3 else 0
    stats = CleanMarkdownStats(
        blocks_after_strip=n0,
        blocks_after_filter=n1,
        blocks_after_dedup=n2,
    )
    return s3.strip(), stats


def clean_page_markdown(raw_page: RawPage) -> CleanedPage:
    """Build CleanedPage from RawPage; set is_low_quality when word_count below threshold."""
    settings = get_settings()
    text, stats = clean_markdown_with_stats(raw_page.markdown)
    wc = len(text.split())
    low = wc < settings.CLEAN_PAGE_MIN_WORDS
    logger.info(
        "clean_page url=%s blocks strip=%d filter=%d dedup=%d words=%d low_quality=%s",
        raw_page.url,
        stats.blocks_after_strip,
        stats.blocks_after_filter,
        stats.blocks_after_dedup,
        wc,
        low,
    )
    return CleanedPage(
        url=raw_page.url,
        title=raw_page.title,
        text=text,
        word_count=wc,
        language=raw_page.language,
        crawled_at=raw_page.crawled_at,
        is_low_quality=low,
    )
