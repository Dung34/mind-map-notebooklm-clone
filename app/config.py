from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PERPLEXITY_API_KEY: str
    FIRECRAWL_API_KEY: str

    PERPLEXITY_MAX_SEARCH_RESULTS: int = Field(default=20, ge=1, le=20)
    PERPLEXITY_VERIFY_HTTP: bool = True

    FIRECRAWL_MAP_LIMIT: int = Field(default=50, ge=1)
    FIRECRAWL_MAP_INCLUDE_SUBDOMAINS: bool = False
    FIRECRAWL_SCRAPE_CONCURRENCY: int = Field(default=5, ge=1, le=20)
    FIRECRAWL_SCRAPE_WAIT_MS: int = Field(default=1500, ge=0, le=60000)
    FIRECRAWL_SCRAPE_ONLY_MAIN: bool = True

    OUTPUT_DIR: str = "./out"
    LOG_LEVEL: str = "INFO"
    HTTP_TIMEOUT: int = Field(default=60, ge=5, le=300)

    CLEAN_PAGE_MIN_WORDS: int = Field(default=50, ge=0)

    CHUNK_MAX_WORDS: int = Field(default=400, ge=50, le=2000)
    CHUNK_MIN_WORDS: int = Field(default=15, ge=1, le=200)
    CHUNK_OVERLAP_SENTENCES: int = Field(default=2, ge=0, le=10)

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

