"""Orchestrator: seeds → map → scrape → clean → chunk; optional ghi artifact."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
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
PIPELINE_VERSION = "phase9-a5"


def _run_id_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _normalize_text_for_hash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def content_hash(text: str) -> str:
    norm = _normalize_text_for_hash(text)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _page_index_latest_path(out_dir: Path) -> Path:
    return out_dir / "page_index_latest.json"


def load_previous_page_index(out_dir: Path) -> dict[str, dict]:
    """Đọc snapshot index gần nhất theo URL; trả {} nếu chưa có."""
    p = _page_index_latest_path(out_dir)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("failed to parse previous page index: %s", p, exc_info=True)
        return {}
    out: dict[str, dict] = {}
    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict) and row.get("normalized_url"):
                out[str(row["normalized_url"])] = row
    return out


def build_page_index_entries(cleaned_pages: list[CleanedPage], *, run_id: str) -> list[dict]:
    now_iso = datetime.now(timezone.utc).isoformat()
    entries: list[dict] = []
    for p in cleaned_pages:
        url = normalize_url(str(p.url))
        entries.append(
            {
                "normalized_url": url,
                "content_hash": content_hash(p.text),
                "last_run_id": run_id,
                "is_active": True,
                "word_count": p.word_count,
                "updated_at": now_iso,
            }
        )
    entries.sort(key=lambda x: x["normalized_url"])
    return entries


def _index_map(entries: list[dict]) -> dict[str, dict]:
    return {str(e["normalized_url"]): e for e in entries if e.get("normalized_url")}


def compute_index_changes(previous: dict[str, dict], current: dict[str, dict]) -> dict[str, int]:
    prev_urls = set(previous.keys())
    cur_urls = set(current.keys())
    new_urls = cur_urls - prev_urls
    removed_urls = prev_urls - cur_urls
    changed_urls = {
        u
        for u in (cur_urls & prev_urls)
        if current[u].get("content_hash") != previous[u].get("content_hash")
    }
    unchanged_urls = (cur_urls & prev_urls) - changed_urls
    return {
        "page_index_previous_count": len(prev_urls),
        "page_index_current_count": len(cur_urls),
        "page_index_new_count": len(new_urls),
        "page_index_changed_count": len(changed_urls),
        "page_index_unchanged_count": len(unchanged_urls),
        "page_index_removed_count": len(removed_urls),
    }


def build_delta_payload(previous: dict[str, dict], current: dict[str, dict], *, run_id: str) -> dict:
    """A3: sinh delta chi tiết new/changed/unchanged/removed theo normalized_url + content_hash."""
    prev_urls = set(previous.keys())
    cur_urls = set(current.keys())

    new_urls = sorted(cur_urls - prev_urls)
    removed_urls = sorted(prev_urls - cur_urls)
    changed_urls = sorted(
        u
        for u in (cur_urls & prev_urls)
        if current[u].get("content_hash") != previous[u].get("content_hash")
    )
    unchanged_urls = sorted((cur_urls & prev_urls) - set(changed_urls))

    return {
        "run_id": run_id,
        "new_urls": new_urls,
        "changed_urls": changed_urls,
        "unchanged_urls": unchanged_urls,
        "removed_urls": removed_urls,
        "summary": {
            "new_count": len(new_urls),
            "changed_count": len(changed_urls),
            "unchanged_count": len(unchanged_urls),
            "removed_count": len(removed_urls),
        },
    }


def _urls_for_delta_rechunk(delta: dict) -> set[str]:
    new_urls = [normalize_url(u) for u in delta.get("new_urls", [])]
    changed_urls = [normalize_url(u) for u in delta.get("changed_urls", [])]
    return set(new_urls + changed_urls)


def load_cached_cleaned_pages(out_dir: Path) -> dict[str, CleanedPage]:
    """Load cleaned cache from previous run keyed by normalized_url."""
    cleaned_dir = out_dir / "cleaned"
    if not cleaned_dir.exists():
        return {}
    out: dict[str, CleanedPage] = {}
    for path in sorted(cleaned_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            cleaned = CleanedPage.model_validate(payload)
            out[normalize_url(str(cleaned.url))] = cleaned
        except Exception:
            logger.warning("failed to parse cached cleaned page: %s", path, exc_info=True)
    return out


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
    run_id: str,
    input_payload: dict,
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

    # Snapshot index cho incremental (A2): URL + content_hash của cleaned pages.
    prev_map = load_previous_page_index(out_dir)
    entries = build_page_index_entries(cleaned_pages, run_id=run_id)
    cur_map = _index_map(entries)
    changes = compute_index_changes(prev_map, cur_map)
    delta = build_delta_payload(prev_map, cur_map, run_id=run_id)
    _page_index_latest_path(out_dir).write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / f"page_index_snapshot_{run_id}.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "delta.json").write_text(
        json.dumps(delta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # A4: chỉ xuất delta chunks cho URL new/changed.
    delta_urls = _urls_for_delta_rechunk(delta)
    chunks_delta = [c for c in chunks if normalize_url(str(c.source_url)) in delta_urls]
    chunks_delta_path = out_dir / "chunks_delta.jsonl"
    with chunks_delta_path.open("w", encoding="utf-8") as f:
        for ch in chunks_delta:
            f.write(ch.model_dump_json() + "\n")

    stats.update(changes)
    stats["delta_new_url_count"] = len(delta.get("new_urls", []))
    stats["delta_changed_url_count"] = len(delta.get("changed_urls", []))
    stats["delta_unchanged_url_count"] = len(delta.get("unchanged_urls", []))
    stats["delta_removed_url_count"] = len(delta.get("removed_urls", []))
    stats["delta_rechunk_url_count"] = len(delta_urls)
    stats["chunk_count_delta"] = len(chunks_delta)
    (out_dir / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    manifest = {
        "run_id": run_id,
        "pipeline_version": PIPELINE_VERSION,
        "input": input_payload,
        "stats": stats,
        "artifacts": {
            "delta": str(out_dir / "delta.json"),
            "chunks_delta": str(chunks_delta_path),
            "chunks": str(chunks_path),
            "page_index_latest": str(_page_index_latest_path(out_dir)),
        },
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
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
    run_id = _run_id_now()

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
    target_urls = [normalize_url(str(d.url)) for d in targets]

    slug = output_dir_slug(company, website, manual_seeds)
    base = Path(settings.OUTPUT_DIR) / slug
    prev_index = load_previous_page_index(base) if write_outputs else {}
    cached_cleaned = load_cached_cleaned_pages(base) if write_outputs else {}

    scrape_urls = list(target_urls)
    skipped_urls: list[str] = []
    if settings.FIRECRAWL_SKIP_SCRAPE_FOR_KNOWN_URLS and write_outputs and prev_index:
        scrape_urls = [u for u in target_urls if u not in prev_index]
        skipped_urls = [u for u in target_urls if u in prev_index]
        # If cache is missing for a "known" URL, force scrape to avoid data loss.
        missing_cache = [u for u in skipped_urls if u not in cached_cleaned]
        if missing_cache:
            scrape_urls.extend(missing_cache)
            skipped_urls = [u for u in skipped_urls if u not in set(missing_cache)]

    raw_pages = await scrape_many(scrape_urls)
    cleaned_fresh = [clean_page_markdown(r) for r in raw_pages]
    cleaned_from_cache = [cached_cleaned[u] for u in skipped_urls if u in cached_cleaned]
    cleaned_by_url: dict[str, CleanedPage] = {}
    for p in cleaned_from_cache + cleaned_fresh:
        cleaned_by_url[normalize_url(str(p.url))] = p
    cleaned_pages = [cleaned_by_url[u] for u in target_urls if u in cleaned_by_url]

    chunks: list[Chunk] = []
    for c in cleaned_pages:
        chunks.extend(chunk_cleaned_page(c))

    low_q = sum(1 for p in cleaned_pages if p.is_low_quality)

    stats = {
        "seed_count": len(seeds),
        "discovered_count": len(discovered),
        "scrape_target_count": len(target_urls),
        "scrape_selected_count": len(scrape_urls),
        "scrape_skipped_count": len(skipped_urls),
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
        write_pipeline_artifacts(
            base,
            run_id=run_id,
            input_payload={
                "company": company,
                "website": website,
                "manual_seeds": manual_seeds or [],
                "limit": limit,
                "no_search": no_search,
                "include_subdomains": include_subdomains,
                "map_limit": map_limit,
            },
            seeds=seeds,
            discovered=discovered,
            raw_pages=raw_pages,
            cleaned_pages=cleaned_pages,
            chunks=chunks,
            stats=stats,
        )

    return result
