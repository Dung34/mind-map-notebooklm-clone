from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, HttpUrl


class SeedURL(BaseModel):
    url: HttpUrl
    source: Literal["perplexity", "user_input", "manual_seed"]
    title: Optional[str] = None
    snippet: Optional[str] = None
    relevance: Optional[float] = None


class DiscoveredURL(BaseModel):
    url: HttpUrl
    domain: str
    discovered_via: Literal["firecrawl_map"] = "firecrawl_map"
    score: Optional[float] = None


class RawPage(BaseModel):
    url: HttpUrl
    title: Optional[str] = None
    markdown: str
    html: Optional[str] = None
    status_code: int = 200
    crawled_at: datetime
    language: Optional[str] = None


class CleanedPage(BaseModel):
    url: HttpUrl
    title: Optional[str] = None
    text: str
    word_count: int
    language: Optional[str] = None
    crawled_at: datetime
    is_low_quality: bool = False


class Chunk(BaseModel):
    chunk_id: str
    source_url: HttpUrl
    page_title: Optional[str] = None
    section_heading: Optional[str] = None
    text: str
    word_count: int
    crawled_at: datetime
    chunk_index: int


class PipelineResult(BaseModel):
    seeds: list[SeedURL]
    urls: list[DiscoveredURL]
    pages: list[CleanedPage]
    chunks: list[Chunk]

