"""Smoke test Phase 4: FireCrawl scrape -> RawPage (markdown + metadata)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.crawl.firecrawl_scrape import scrape_many, scrape_url
from app.discover.firecrawl_map import discover_from_seeds
from app.models import SeedURL
from app.search.perplexity_search import build_seed_urls, normalize_url


def _preview(text: str, max_len: int = 160) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= max_len:
        return one_line
    return one_line[: max_len - 3] + "..."


def main() -> None:
    p = argparse.ArgumentParser(description="Phase 4: FireCrawl scrape -> RawPage")
    p.add_argument("--url", action="append", default=[], help="Chỉ scrape URL này; lặp lại được nhiều lần")
    p.add_argument("--company", default=None)
    p.add_argument("--website", default=None)
    p.add_argument("--manual", action="append", default=[])
    p.add_argument("--no-search", action="store_true", help="Chỉ dùng --website làm seed (bỏ Perplexity)")
    p.add_argument("--map-limit", type=int, default=None, help="FIRECRAWL_MAP_LIMIT override")
    p.add_argument(
        "--scrape-limit",
        type=int,
        default=5,
        help="Số URL scrape tối đa sau bước map (mặc định 5)",
    )
    p.add_argument("--concurrency", type=int, default=None, help="Override FIRECRAWL_SCRAPE_CONCURRENCY")
    p.add_argument("--include-subdomains", action="store_true")
    args = p.parse_args()

    urls: list[str] = [normalize_url(u) for u in (args.url or []) if u and u.strip()]

    if not urls:
        if args.no_search:
            if not args.website:
                print("Cần --website khi --no-search")
                sys.exit(1)
            seeds = [
                SeedURL(url=normalize_url(args.website), source="user_input"),
                *[
                    SeedURL(url=normalize_url(m), source="manual_seed")
                    for m in (args.manual or [])
                    if m.strip()
                ],
            ]
        else:
            seeds = build_seed_urls(
                company=args.company,
                website=args.website,
                manual_seeds=args.manual or None,
            )
            if not seeds:
                print(
                    "Không có seed URL. Thêm --company / --website / --manual, "
                    "hoặc --no-search --website ..., hoặc --url https://..."
                )
                sys.exit(1)

        inc = True if args.include_subdomains else None
        discovered = discover_from_seeds(
            seeds,
            limit=args.map_limit,
            include_subdomains=inc,
        )
        cap = max(1, args.scrape_limit)
        urls = [str(d.url) for d in discovered[:cap]]

    if not urls:
        print("Không có URL để scrape.")
        sys.exit(1)

    if len(urls) == 1 and args.concurrency is None:
        page = scrape_url(urls[0])
        print(f"scrape_count=1 markdown_chars={len(page.markdown)} status={page.status_code}")
        print(f"  title={page.title!r}")
        print(f"  preview={_preview(page.markdown)!r}")
        return

    pages = asyncio.run(scrape_many(urls, concurrency=args.concurrency))
    print(f"attempts={len(urls)} ok={len(pages)}")
    for i, page in enumerate(pages):
        print(
            f"  [{i}] status={page.status_code} chars={len(page.markdown)} "
            f"title={page.title!r}"
        )
        print(f"       preview={_preview(page.markdown)!r}")


if __name__ == "__main__":
    main()
