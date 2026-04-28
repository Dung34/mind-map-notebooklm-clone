"""A5 smoke test: run pipeline twice and compare incremental workload."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.config import get_settings
from app.pipeline import output_dir_slug, run_pipeline


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _pick(stats: dict) -> dict:
    keys = [
        "discovered_count",
        "scrape_target_count",
        "raw_page_count",
        "cleaned_page_count",
        "chunk_count",
        "delta_new_url_count",
        "delta_changed_url_count",
        "delta_unchanged_url_count",
        "delta_removed_url_count",
        "delta_rechunk_url_count",
        "chunk_count_delta",
    ]
    return {k: stats.get(k, 0) for k in keys}


async def _async_main() -> None:
    p = argparse.ArgumentParser(description="Phase 9 A5 smoke test (2 consecutive runs)")
    p.add_argument("--website", required=True, help="Domain to run smoke test on")
    p.add_argument("--limit", type=int, default=5, help="Max discovered URLs per run")
    p.add_argument("--show-manifest", action="store_true", help="Print manifest path and run_id")
    args = p.parse_args()
    if args.limit < 1:
        p.error("--limit must be >= 1")

    settings = get_settings()
    slug = output_dir_slug(None, args.website, None)
    out_dir = Path(settings.OUTPUT_DIR) / slug

    # Run 1
    await run_pipeline(
        website=args.website,
        no_search=True,
        limit=args.limit,
        write_outputs=True,
    )
    stats_1 = _load_json(out_dir / "stats.json")
    manifest_1 = _load_json(out_dir / "manifest.json")

    # Run 2
    await run_pipeline(
        website=args.website,
        no_search=True,
        limit=args.limit,
        write_outputs=True,
    )
    stats_2 = _load_json(out_dir / "stats.json")
    manifest_2 = _load_json(out_dir / "manifest.json")

    run_1 = _pick(stats_1)
    run_2 = _pick(stats_2)
    run_1_delta = run_1["delta_rechunk_url_count"]
    run_2_delta = run_2["delta_rechunk_url_count"]
    strict_reduction = run_2_delta < run_1_delta
    non_increase = run_2_delta <= run_1_delta
    status = "passed" if strict_reduction else ("stable" if non_increase else "failed")
    if run_1_delta == 0 and run_2_delta == 0:
        status = "inconclusive"

    summary = {
        "website": args.website,
        "output_dir": str(out_dir),
        "run_1": run_1,
        "run_2": run_2,
        "a5_assertion": {
            "rule": "run_2.delta_rechunk_url_count <= run_1.delta_rechunk_url_count",
            "strict_reduction": strict_reduction,
            "non_increase": non_increase,
            "status": status,
        },
    }
    if args.show_manifest:
        summary["manifest"] = {
            "run_1_run_id": manifest_1.get("run_id"),
            "run_2_run_id": manifest_2.get("run_id"),
            "path": str(out_dir / "manifest.json"),
        }

    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
