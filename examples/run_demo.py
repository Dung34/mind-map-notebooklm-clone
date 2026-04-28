"""Chạy pipeline end-to-end (Phase 7): demo CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.config import get_settings
from app.pipeline import output_dir_slug, run_pipeline


async def _async_main() -> None:
    p = argparse.ArgumentParser(
        description="Run pipeline: Perplexity seeds (optional) -> map -> scrape -> clean -> chunk",
    )
    p.add_argument("--company", default=None)
    p.add_argument("--website", default=None)
    p.add_argument("--manual", action="append", default=[], help="Repeat to provide multiple URLs")
    p.add_argument("--limit", type=int, default=10, help="Max URLs to scrape")
    p.add_argument(
        "--no-search",
        action="store_true",
        help="Skip Perplexity; seed only from --website (+ --manual)",
    )
    p.add_argument("--include-subdomains", action="store_true")
    p.add_argument("--map-limit", type=int, default=None, help="Override FIRECRAWL_MAP_LIMIT")
    p.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write out/<slug>/ (memory only)",
    )
    p.add_argument("--log-level", default="INFO", help="DEBUG|INFO|WARNING|ERROR")
    args = p.parse_args()
    if args.limit < 1:
        p.error("--limit must be >= 1")

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s %(name)s %(message)s",
    )

    if args.no_search and not (args.website and args.website.strip()):
        print("With --no-search, --website is required")
        sys.exit(1)
    if not args.no_search:
        if not (
            (args.company and args.company.strip())
            or (args.website and args.website.strip())
            or any(m.strip() for m in args.manual)
        ):
            print("Provide at least one of: --company, --website, --manual (or --no-search --website)")
            sys.exit(1)

    settings = get_settings()
    result = await run_pipeline(
        company=args.company,
        website=args.website,
        manual_seeds=args.manual if args.manual else None,
        limit=args.limit,
        no_search=args.no_search,
        include_subdomains=True if args.include_subdomains else None,
        map_limit=args.map_limit,
        write_outputs=not args.no_write,
    )

    slug = output_dir_slug(args.company, args.website, args.manual if args.manual else None)
    summary = {
        "slug": slug,
        "output_dir": str(Path(settings.OUTPUT_DIR) / slug) if not args.no_write else None,
        "stats": {
            "seed_urls": len(result.seeds),
            "discovered_urls": len(result.urls),
            "cleaned_pages": len(result.pages),
            "chunks": len(result.chunks),
        },
        "chunks_path": str(Path(settings.OUTPUT_DIR) / slug / "chunks.jsonl")
        if not args.no_write
        else None,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
