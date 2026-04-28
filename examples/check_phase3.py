"""Smoke test Phase 3: FireCrawl map -> DiscoveredURL list."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.discover.firecrawl_map import discover_from_seeds
from app.models import SeedURL
from app.search.perplexity_search import build_seed_urls, normalize_url


def main() -> None:
    p = argparse.ArgumentParser(description="Phase 3: FireCrawl map from seeds")
    p.add_argument("--company", default=None)
    p.add_argument("--website", default=None)
    p.add_argument("--manual", action="append", default=[])
    p.add_argument("--limit", type=int, default=None, help="FIRECRAWL_MAP_LIMIT override")
    p.add_argument("--no-search", action="store_true", help="Chỉ dùng --website làm seed (bỏ Perplexity)")
    p.add_argument("--include-subdomains", action="store_true")
    args = p.parse_args()

    if args.no_search:
        if not args.website:
            print("Cần --website khi dùng --no-search")
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
                "Không có seed URL. Thêm --company / --website / --manual hoặc "
                "dùng --no-search --website ..."
            )
            sys.exit(1)

    inc = True if args.include_subdomains else None

    discovered = discover_from_seeds(
        seeds,
        limit=args.limit,
        include_subdomains=inc,
    )

    print(f"seed_count={len(seeds)} discovered_count={len(discovered)}")
    for i, d in enumerate(discovered):
        print(f"  [{i}] score={d.score} {d.url}")


if __name__ == "__main__":
    main()
