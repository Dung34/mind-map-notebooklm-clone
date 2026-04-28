from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

# Cho phép chạy: python examples/check_phase1.py (không cần PYTHONPATH)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.config import get_settings
from app.models import Chunk, CleanedPage, DiscoveredURL, PipelineResult, RawPage, SeedURL


def main() -> None:
    settings = get_settings()
    print("Settings loaded successfully.")
    print(f"OUTPUT_DIR={settings.OUTPUT_DIR}")
    print(f"HTTP_TIMEOUT={settings.HTTP_TIMEOUT}")

    seed = SeedURL(url="https://example.com", source="user_input")
    discovered = DiscoveredURL(url="https://example.com/about", domain="example.com")
    raw = RawPage(
        url="https://example.com/about",
        title="About",
        markdown="# About\nExample text",
        crawled_at=datetime.now(timezone.utc),
    )
    cleaned = CleanedPage(
        url=raw.url,
        title=raw.title,
        text="Example text",
        word_count=2,
        language="en",
        crawled_at=raw.crawled_at,
    )
    chunk = Chunk(
        chunk_id="demo123",
        source_url=cleaned.url,
        page_title=cleaned.title,
        section_heading="About",
        text=cleaned.text,
        word_count=cleaned.word_count,
        crawled_at=cleaned.crawled_at,
        chunk_index=0,
    )

    result = PipelineResult(seeds=[seed], urls=[discovered], pages=[cleaned], chunks=[chunk])
    print("Model instantiation successful.")
    print(f"PipelineResult chunks={len(result.chunks)}")


if __name__ == "__main__":
    main()

