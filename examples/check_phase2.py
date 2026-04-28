"""Smoke test Phase 2: Perplexity Search + normalize + optional HTTP verify -> SeedURL list."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.search.perplexity_search import build_seed_urls


def main() -> None:
    p = argparse.ArgumentParser(description="Phase 2: build seed URLs via Perplexity Search API")
    p.add_argument("--company", default=None, help="Tên công ty")
    p.add_argument("--website", default=None, help="Website (domain hoặc URL)")
    p.add_argument("--manual", action="append", default=[], help="Thêm seed URL thủ công (lặp --manual)")
    p.add_argument("--no-verify", action="store_true", help="Bỏ kiểm tra HTTP (nhanh hơn, kém an toàn)")
    p.add_argument("--no-domain-filter", action="store_true", help="Không lọc kết quả search theo domain website")
    p.add_argument("--max-results", type=int, default=None, help="Perplexity max_results (1-20)")
    args = p.parse_args()

    seeds = build_seed_urls(
        company=args.company,
        website=args.website,
        manual_seeds=args.manual or None,
        max_results=args.max_results,
        verify_http=False if args.no_verify else None,
        filter_to_website_domain=not args.no_domain_filter,
    )

    print(f"seed_count={len(seeds)}")
    for i, s in enumerate(seeds):
        print(f"  [{i}] {s.source} {s.url}")


if __name__ == "__main__":
    main()
