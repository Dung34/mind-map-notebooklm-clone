"""Smoke test Phase 6: CleanedPage → list[Chunk] (rule-based chunker)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.chunk.rule_based_chunker import chunk_cleaned_page, chunk_text
from app.clean.markdown_cleaner import clean_page_markdown
from app.crawl.firecrawl_scrape import scrape_url
from app.config import get_settings


def main() -> None:
    p = argparse.ArgumentParser(description="Phase 6: chunk CleanedPage → Chunk")
    p.add_argument("--url", default=None, help="Scrape → clean → chunk (cần FIRECRAWL_API_KEY)")
    p.add_argument(
        "--markdown-file",
        default=None,
        help="Markdown file → xử lý như RawPage giả lập → clean → chunk",
    )
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s %(name)s %(message)s",
    )

    settings = get_settings()
    print(
        f"CHUNK_MAX_WORDS={settings.CHUNK_MAX_WORDS} "
        f"CHUNK_MIN_WORDS={settings.CHUNK_MIN_WORDS} "
        f"OVERLAP={settings.CHUNK_OVERLAP_SENTENCES}"
    )

    if args.markdown_file:
        from datetime import datetime, timezone

        from pydantic import HttpUrl

        from app.models import RawPage

        md = Path(args.markdown_file).read_text(encoding="utf-8")
        raw = RawPage(
            url=HttpUrl("https://example.local/fixture"),
            title="fixture",
            markdown=md,
            crawled_at=datetime.now(timezone.utc),
        )
    elif args.url:
        raw = scrape_url(args.url)
    else:
        print("Cần --url hoặc --markdown-file")
        sys.exit(1)

    cleaned = clean_page_markdown(raw)
    flat = chunk_text(cleaned.text)
    chunks = chunk_cleaned_page(cleaned)

    print(f"clean_word_count={cleaned.word_count} flat_piece_count={len(flat)} chunk_models={len(chunks)}")
    for i, ch in enumerate(chunks[:12]):
        head = ch.section_heading or "—"
        print(
            f"  [{ch.chunk_index}] id={ch.chunk_id} words={ch.word_count} "
            f"section={head[:50]!r}"
        )
        prev = ch.text[:120] + ("..." if len(ch.text) > 120 else "")
        print(f"       text={prev!r}")
    if len(chunks) > 12:
        print(f"  ... và {len(chunks) - 12} chunk nữa")


if __name__ == "__main__":
    main()
