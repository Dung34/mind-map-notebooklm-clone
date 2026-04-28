"""Orchestrator: seeds → map → scrape → clean → chunk; optional ghi artifact."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from pydantic import HttpUrl

from app.chunk.rule_based_chunker import chunk_cleaned_page
from app.clean.markdown_cleaner import clean_page_markdown
from app.config import get_settings
from app.crawl.firecrawl_scrape import scrape_many
from app.discover.firecrawl_map import discover_from_seeds
from app.models import CleanedPage, Chunk, DiscoveredURL, PipelineResult, RawPage, SeedURL
from app.search.perplexity_search import build_seed_urls, normalize_url

logger = logging.getLogger(__name__)


def output_dir_slug(
    company: str | None,
    website: str | None,
    manual_seeds: list[str] | None = None,
) -> str:
    """Thư mục con dưới OUTPUT_DIR (vd: fpt-software, fptsoftware-com)."""
    if company and company.strip():
        s = re.sub(r"[^a-z0-9]+", "-", company.strip().lower()).strip("-")
        if s:
            return s
    if website and website.strip():
        host = urlparse(normalize_url(website)).netloc.lower().split(":")[0]
        host = re.sub(r"^www\.", "", host)
        s = host.replace(".", "-").strip("-")
        if s:
            return s
    for m in manual_seeds or []:
        if m and m.strip():
            host = urlparse(normalize_url(m)).netloc.lower().split(":")[0]
            host = re.sub(r"^www\.", "", host)
            s = host.replace(".", "-").strip("-")
            if s:
                return s
    return "run"


def _seeds_no_search(
    website: str,
    manual_seeds: list[str] | None,
) -> list[SeedURL]:
    seeds: list[SeedURL] = [
        SeedURL(url=HttpUrl(normalize_url(website)), source="user_input"),
    ]
    for m in manual_seeds or []:
        if m and m.strip():
            seeds.append(SeedURL(url=HttpUrl(normalize_url(m)), source="manual_seed"))
    return seeds


def write_pipeline_artifacts(
    out_dir: Path,
    *,
    seeds: list[SeedURL],
    discovered: list[DiscoveredURL],
    raw_pages: list[RawPage],
    cleaned_pages: list[CleanedPage],
    chunks: list[Chunk],
    stats: dict,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw"
    cleaned_dir = out_dir / "cleaned"
    raw_dir.mkdir(exist_ok=True)
    cleaned_dir.mkdir(exist_ok=True)

    (out_dir / "seeds.json").write_text(
        json.dumps([s.model_dump(mode="json") for s in seeds], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "discovered.json").write_text(
        json.dumps([d.model_dump(mode="json") for d in discovered], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for i, page in enumerate(raw_pages, start=1):
        name = f"{i:04d}.json"
        (raw_dir / name).write_text(
            json.dumps(page.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    for i, page in enumerate(cleaned_pages, start=1):
        name = f"{i:04d}.json"
        (cleaned_dir / name).write_text(
            json.dumps(page.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    chunks_path = out_dir / "chunks.jsonl"
    with chunks_path.open("w", encoding="utf-8") as f:
        for ch in chunks:
            f.write(ch.model_dump_json() + "\n")

    (out_dir / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("wrote artifacts under %s", out_dir.resolve())


async def run_pipeline(
    company: str | None = None,
    website: str | None = None,
    manual_seeds: list[str] | None = None,
    limit: int = 20,
    *,
    no_search: bool = False,
    include_subdomains: bool | None = None,
    map_limit: int | None = None,
    write_outputs: bool = True,
) -> PipelineResult:
    """
    Stage 1–5: seed URLs → FireCrawl map → scrape (``limit`` URL đầu) → clean → chunk.
    Ghi ``out/<slug>/`` khi ``write_outputs=True``.
    """
    settings = get_settings()
    t0 = time.perf_counter()

    if no_search:
        if not website or not website.strip():
            raise ValueError("run_pipeline: cần website khi no_search=True")
        seeds = _seeds_no_search(website, manual_seeds)
    else:
        seeds = build_seed_urls(
            company=company,
            website=website,
            manual_seeds=manual_seeds,
        )
        if not seeds:
            raise ValueError(
                "run_pipeline: không có seed URL — thêm --company / --website / --manual "
                "hoặc dùng --no-search --website ..."
            )

    inc = True if include_subdomains else None
    discovered = discover_from_seeds(
        seeds,
        limit=map_limit,
        include_subdomains=inc,
    )

    if not discovered:
        raise ValueError(
            "run_pipeline: danh sách discovered rỗng sau map — kiểm tra seed / FireCrawl map."
        )
    targets = discovered[: min(limit, len(discovered))]
    target_urls = [str(d.url) for d in targets]

    raw_pages = await scrape_many(target_urls)
    cleaned_pages = [clean_page_markdown(r) for r in raw_pages]

    chunks: list[Chunk] = []
    for c in cleaned_pages:
        chunks.extend(chunk_cleaned_page(c))

    low_q = sum(1 for p in cleaned_pages if p.is_low_quality)

    stats = {
        "seed_count": len(seeds),
        "discovered_count": len(discovered),
        "scrape_target_count": len(target_urls),
        "raw_page_count": len(raw_pages),
        "cleaned_page_count": len(cleaned_pages),
        "low_quality_cleaned_count": low_q,
        "chunk_count": len(chunks),
        "duration_seconds": round(time.perf_counter() - t0, 3),
    }

    result = PipelineResult(
        seeds=seeds,
        urls=discovered,
        pages=cleaned_pages,
        chunks=chunks,
    )

    if write_outputs:
        slug = output_dir_slug(company, website, manual_seeds)
        base = Path(settings.OUTPUT_DIR) / slug
        write_pipeline_artifacts(
            base,
            seeds=seeds,
            discovered=discovered,
            raw_pages=raw_pages,
            cleaned_pages=cleaned_pages,
            chunks=chunks,
            stats=stats,
        )

    return result
