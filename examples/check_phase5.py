"""Smoke test Phase 5: RawPage → CleanedPage (markdown cleaner)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.clean.markdown_cleaner import (
    clean_markdown_with_stats,
    clean_page_markdown,
)
from app.crawl.firecrawl_scrape import scrape_url
from app.config import get_settings


def _preview(text: str, max_len: int = 280) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= max_len:
        return one_line
    return one_line[: max_len - 3] + "..."


def main() -> None:
    p = argparse.ArgumentParser(description="Phase 5: clean markdown → CleanedPage")
    p.add_argument("--url", default=None, help="Scrape URL rồi clean (cần FIRECRAWL_API_KEY)")
    p.add_argument(
        "--markdown-file",
        default=None,
        help="Đọc markdown từ file (UTF-8), không gọi FireCrawl",
    )
    p.add_argument("--log-level", default="INFO", help="DEBUG|INFO|WARNING")
    args = p.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s %(name)s %(message)s",
    )

    settings = get_settings()

    if args.markdown_file:
        path = Path(args.markdown_file)
        md = path.read_text(encoding="utf-8")
        from datetime import datetime, timezone

        from pydantic import HttpUrl

        from app.models import RawPage

        raw = RawPage(
            url=HttpUrl("https://example.local/file"),
            title="fixture",
            markdown=md,
            crawled_at=datetime.now(timezone.utc),
        )
    elif args.url:
        raw = scrape_url(args.url)
    else:
        print("Cần --url hoặc --markdown-file")
        sys.exit(1)

    text_stats, stats = clean_markdown_with_stats(raw.markdown)
    cleaned = clean_page_markdown(raw)

    print(f"CLEAN_PAGE_MIN_WORDS={settings.CLEAN_PAGE_MIN_WORDS}")
    print(
        f"blocks: strip={stats.blocks_after_strip} "
        f"filter={stats.blocks_after_filter} dedup={stats.blocks_after_dedup}"
    )
    print(
        f"word_count={cleaned.word_count} is_low_quality={cleaned.is_low_quality} "
        f"markdown_in={len(raw.markdown)} text_out={len(cleaned.text)}"
    )
    print(f"preview={_preview(cleaned.text)!r}")


if __name__ == "__main__":
    main()
