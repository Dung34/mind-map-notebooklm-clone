"""Stage 1: Perplexity Search API -> seed URLs (normalize, optional HTTP verify)."""

from __future__ import annotations

import logging
from typing import Literal
from urllib.parse import urlparse, urlunparse

import httpx
from perplexity import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    Perplexity,
    RateLimitError,
)
from pydantic import HttpUrl, ValidationError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.models import SeedURL

logger = logging.getLogger(__name__)

# URL rác thường gặp khi search tên công ty (có thể mở rộng)
_SOCIAL_HOST_FRAGMENTS = (
    "facebook.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "tiktok.com",
    "youtube.com",
    "reddit.com",
    "pinterest.com",
)


def normalize_url(u: str) -> str:
    u = u.strip()
    if not u:
        return u
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    p = urlparse(u)
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme, p.netloc.lower(), path, "", "", ""))


def _primary_host(website: str | None) -> str | None:
    if not website or not website.strip():
        return None
    p = urlparse(normalize_url(website))
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _host_matches_seed(host: str, primary: str) -> bool:
    h = host.lower().rstrip(".")
    p = primary.lower().lstrip("www.").rstrip(".")
    if not p:
        return True
    return h == p or h == f"www.{p}" or h.endswith("." + p)


def _is_blocked_host(host: str) -> bool:
    h = host.lower()
    return any(s in h for s in _SOCIAL_HOST_FRAGMENTS)


def _build_search_query(company: str | None, website: str | None) -> str:
    parts: list[str] = []
    if company and company.strip():
        parts.append(f'Official website and key pages for company "{company.strip()}".')
    if website and website.strip():
        parts.append(f"Known website: {website.strip()}.")
    parts.append(
        "Return URLs for: homepage, about, products or services, contact, careers, news."
    )
    return " ".join(parts)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    retry=retry_if_exception_type(
        (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)
    ),
    reraise=True,
)
def _search_create(client: Perplexity, query: str, max_results: int, timeout: float):
    return client.search.create(
        query=query,
        max_results=max_results,
        timeout=timeout,
    )


def search_seed_urls(
    company: str | None = None,
    website: str | None = None,
    *,
    max_results: int | None = None,
    api_key: str | None = None,
    http_timeout: float | None = None,
) -> list[tuple[str, str | None, str | None]]:
    """
    Gọi Perplexity Search API, trả list (url, title, snippet) — chưa normalize/verify.
    """
    settings = get_settings()
    key = api_key or settings.PERPLEXITY_API_KEY
    n = max_results if max_results is not None else settings.PERPLEXITY_MAX_SEARCH_RESULTS
    n = max(1, min(20, n))
    timeout = http_timeout if http_timeout is not None else float(settings.HTTP_TIMEOUT)

    query = _build_search_query(company, website)
    if not query.strip():
        return []

    client = Perplexity(api_key=key)
    try:
        res = _search_create(client, query, n, timeout)
    finally:
        client.close()

    out: list[tuple[str, str | None, str | None]] = []
    for r in res.results:
        if r.url:
            out.append((r.url, r.title or None, r.snippet or None))
    return out


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(httpx.TransportError),
    reraise=True,
)
def _head_or_get(client: httpx.Client, url: str) -> httpx.Response:
    r = client.head(url)
    if r.status_code in (405, 501):
        r = client.get(url)
    return r


def verify_url_reachable(url: str, timeout: float) -> bool:
    """True nếu URL trả 2xx/3xx sau redirect."""
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            r = _head_or_get(client, url)
            return 200 <= r.status_code < 400
    except (httpx.HTTPError, httpx.TransportError):
        return False


def build_seed_urls(
    company: str | None = None,
    website: str | None = None,
    manual_seeds: list[str] | None = None,
    *,
    max_results: int | None = None,
    verify_http: bool | None = None,
    filter_to_website_domain: bool = True,
) -> list[SeedURL]:
    """
    Merge: website (user_input) + manual_seeds + Perplexity search (perplexity),
    normalize, dedupe (ưu tiên thứ tự trên), lọc domain / social, optional verify HTTP.
    """
    settings = get_settings()
    do_verify = settings.PERPLEXITY_VERIFY_HTTP if verify_http is None else verify_http
    timeout = float(settings.HTTP_TIMEOUT)
    primary = _primary_host(website)

    SeedSource = Literal["perplexity", "user_input", "manual_seed"]
    ordered: list[tuple[str, SeedSource]] = []
    if website and website.strip():
        ordered.append((normalize_url(website), "user_input"))
    for m in manual_seeds or []:
        if m and m.strip():
            ordered.append((normalize_url(m), "manual_seed"))

    try:
        raw_search = search_seed_urls(
            company=company,
            website=website,
            max_results=max_results,
        )
    except Exception:
        logger.exception("Perplexity search failed")
        raw_search = []

    for url, title, snippet in raw_search:
        nu = normalize_url(url)
        if not nu:
            continue
        host = urlparse(nu).netloc.lower()
        if _is_blocked_host(host):
            continue
        if filter_to_website_domain and primary and not _host_matches_seed(host, primary):
            continue
        ordered.append((nu, "perplexity"))

    seen: set[str] = set()
    candidates: list[tuple[str, SeedSource]] = []
    for url, source in ordered:
        if url in seen:
            continue
        seen.add(url)
        candidates.append((url, source))

    titles_by_url: dict[str, str | None] = {}
    snippets_by_url: dict[str, str | None] = {}
    for url, title, snippet in raw_search:
        nu = normalize_url(url)
        if nu and nu not in titles_by_url:
            titles_by_url[nu] = title
            snippets_by_url[nu] = snippet

    seeds: list[SeedURL] = []
    for url, source in candidates:
        if do_verify and not verify_url_reachable(url, timeout):
            logger.debug("seed dropped (unreachable): %s", url)
            continue
        try:
            http = HttpUrl(url)
        except ValidationError:
            logger.debug("seed dropped (invalid HttpUrl): %s", url)
            continue
        title = titles_by_url.get(url) if source == "perplexity" else None
        snippet = snippets_by_url.get(url) if source == "perplexity" else None
        seeds.append(
            SeedURL(
                url=http,
                source=source,
                title=title,
                snippet=snippet,
            )
        )

    return seeds
