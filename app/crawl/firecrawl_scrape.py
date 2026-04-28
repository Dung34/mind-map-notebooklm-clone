"""Stage 3: FireCrawl scrape -> RawPage (markdown + metadata)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from firecrawl import Firecrawl
from pydantic import HttpUrl

from app.config import get_settings
from app.models import RawPage
from app.search.perplexity_search import normalize_url

if TYPE_CHECKING:
    from app.models import DiscoveredURL

logger = logging.getLogger(__name__)


def _firecrawl_client() -> Firecrawl:
    s = get_settings()
    return Firecrawl(
        api_key=s.FIRECRAWL_API_KEY,
        timeout=float(s.HTTP_TIMEOUT),
    )


def _document_to_raw_page(
    request_url: str,
    doc,
    *,
    include_html: bool,
) -> RawPage:
    from firecrawl.v2.types import Document

    if not isinstance(doc, Document):
        raise TypeError("expected firecrawl Document")

    md = doc.markdown or ""
    meta = doc.metadata_typed
    title = meta.title
    lang = meta.language
    status = meta.status_code if meta.status_code is not None else 200
    html = doc.html if include_html else None
    nu = normalize_url(request_url)
    return RawPage(
        url=HttpUrl(nu),
        title=title,
        markdown=md,
        html=html,
        status_code=int(status),
        crawled_at=datetime.now(timezone.utc),
        language=lang,
    )


def scrape_url(url: str, *, include_html: bool = False) -> RawPage:
    """
    Scrape một URL (FireCrawl v2 /scrape), trả RawPage.
    """
    settings = get_settings()
    nu = normalize_url(url)
    timeout_ms = int(settings.HTTP_TIMEOUT * 1000)
    wait_ms = settings.FIRECRAWL_SCRAPE_WAIT_MS
    only_main = settings.FIRECRAWL_SCRAPE_ONLY_MAIN
    formats: list[str] = ["markdown", "html"] if include_html else ["markdown"]

    client = _firecrawl_client()
    doc = client.scrape(
        nu,
        formats=formats,
        only_main_content=only_main,
        timeout=timeout_ms,
        wait_for=wait_ms if wait_ms > 0 else None,
        block_ads=True,
        remove_base64_images=True,
    )
    return _document_to_raw_page(nu, doc, include_html=include_html)


async def scrape_many(
    urls: list[str],
    *,
    concurrency: int | None = None,
    include_html: bool = False,
) -> list[RawPage]:
    """
    Scrape nhiều URL song song, giới hạn bởi FIRECRAWL_SCRAPE_CONCURRENCY.
    URL lỗi được bỏ qua (log warning), không làm fail cả batch.
    """
    settings = get_settings()
    sem_n = concurrency if concurrency is not None else settings.FIRECRAWL_SCRAPE_CONCURRENCY
    sem = asyncio.Semaphore(sem_n)

    async def one(u: str) -> RawPage | None:
        async with sem:
            try:
                return await asyncio.to_thread(scrape_url, u, include_html=include_html)
            except Exception:
                logger.warning("scrape failed for %s", u, exc_info=True)
                return None

    results = await asyncio.gather(*(one(u) for u in urls))
    return [p for p in results if p is not None]


def scrape_discovered(urls: list["DiscoveredURL"], **kwargs) -> list[RawPage]:
    """Sync helper: chạy scrape_many trong event loop mới (CLI / script đơn giản)."""
    str_urls = [str(d.url) for d in urls]
    return asyncio.run(scrape_many(str_urls, **kwargs))
