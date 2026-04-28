"""Stage 2: FireCrawl map -> DiscoveredURL list (filter + dedupe + seed fallback)."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from firecrawl import Firecrawl
from pydantic import HttpUrl, ValidationError

from app.config import get_settings
from app.models import DiscoveredURL, SeedURL
from app.search.perplexity_search import normalize_url

logger = logging.getLogger(__name__)

# Path / URL noise (blog pagination, assets, auth…)
_URL_BLACKLIST = re.compile(
    r"/(tag|tags|category|categories|author|feed|rss|page/\d+|search|"
    r"wp-admin|wp-content|wp-json|xmlrpc\.php)|"
    r"(?:^|[?])(replytocom=|share=|utm_)|"
    r"\.(jpg|jpeg|png|gif|webp|svg|pdf|zip|mp4|mp3|ico|woff2?)(\?|$)",
    re.IGNORECASE,
)

_PRIORITY_PATH_PREFIXES: tuple[str, ...] = (
    "/about",
    "/services",
    "/products",
    "/product",
    "/solutions",
    "/careers",
    "/contact",
    "/news",
    "/blog",
    "/company",
)


def _path_score(url: str) -> float:
    path = urlparse(url).path.lower()
    if any(path == p or path.startswith(p + "/") for p in _PRIORITY_PATH_PREFIXES):
        return 1.0
    return 0.5


def _should_drop_url(url: str) -> bool:
    if not url or not url.strip():
        return True
    return bool(_URL_BLACKLIST.search(url))


def _domain_from_url(url: str) -> str:
    return urlparse(url).netloc.lower() or ""


def discover_from_seeds(
    seeds: list[SeedURL],
    *,
    limit: int | None = None,
    map_root: str | None = None,
    search: str | None = None,
    include_subdomains: bool | None = None,
) -> list[DiscoveredURL]:
    """
    Gọi FireCrawl ``map`` (v2) từ một root URL, lọc URL rác, dedupe, merge thêm seed nếu thiếu.
    Nếu map lỗi hoặc rỗng, fallback: chỉ trả các seed (hợp lệ, không blacklist).
    """
    settings = get_settings()
    lim = limit if limit is not None else settings.FIRECRAWL_MAP_LIMIT
    inc = (
        include_subdomains
        if include_subdomains is not None
        else settings.FIRECRAWL_MAP_INCLUDE_SUBDOMAINS
    )

    if not seeds:
        return []

    root: str | None = map_root
    if not root:
        user = next((s for s in seeds if s.source == "user_input"), None)
        pick = user or seeds[0]
        root = str(pick.url)
    root_norm = normalize_url(root)
    search_str = search if search is not None else root_norm

    raw_from_map: list[str] = []
    client = Firecrawl(
        api_key=settings.FIRECRAWL_API_KEY,
        timeout=float(settings.HTTP_TIMEOUT),
    )
    try:
        map_data = client.map(
            root_norm,
            search=search_str,
            limit=lim,
            include_subdomains=inc,
            timeout=int(settings.HTTP_TIMEOUT * 1000),
        )
        raw_from_map = [normalize_url(link.url) for link in map_data.links if link.url]
    except Exception:
        logger.exception("FireCrawl map failed; falling back to seeds only")

    candidates: list[tuple[str, float]] = []
    seen: set[str] = set()

    for u in raw_from_map:
        if not u or u in seen or _should_drop_url(u):
            continue
        seen.add(u)
        candidates.append((u, _path_score(u)))

    for s in seeds:
        u = normalize_url(str(s.url))
        if not u or u in seen or _should_drop_url(u):
            continue
        seen.add(u)
        candidates.append((u, 1.0))

    candidates.sort(key=lambda x: (-x[1], x[0]))

    out: list[DiscoveredURL] = []
    for u, score in candidates[:lim]:
        try:
            out.append(
                DiscoveredURL(
                    url=HttpUrl(u),
                    domain=_domain_from_url(u),
                    score=score,
                )
            )
        except ValidationError:
            logger.debug("skip invalid discovered url: %s", u)

    return out


def discover_urls(base_url: str, limit: int | None = None) -> list[str]:
    """Tiện ích: một URL gốc -> list URL string (tương thích stub cũ)."""
    seed = SeedURL(url=normalize_url(base_url), source="user_input")
    return [str(d.url) for d in discover_from_seeds([seed], limit=limit)]
