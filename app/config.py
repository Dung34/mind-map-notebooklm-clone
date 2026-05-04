from functools import lru_cache
from typing import Optional

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
    FIRECRAWL_SKIP_SCRAPE_FOR_KNOWN_URLS: bool = True

    OUTPUT_DIR: str = "./out"
    LOG_LEVEL: str = "INFO"
    HTTP_TIMEOUT: int = Field(default=60, ge=5, le=300)

    CLEAN_PAGE_MIN_WORDS: int = Field(default=50, ge=0)

    CHUNK_MAX_WORDS: int = Field(default=400, ge=50, le=2000)
    CHUNK_MIN_WORDS: int = Field(default=15, ge=1, le=200)
    CHUNK_OVERLAP_SENTENCES: int = Field(default=2, ge=0, le=10)

    OPENAI_API_KEY: Optional[str] = None
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_BATCH_SIZE: int = Field(default=32, ge=1, le=256)
    EMBEDDING_MAX_RETRIES: int = Field(default=4, ge=0, le=10)
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/cleaner_raw_data"
    VECTOR_TABLE: str = "rag_chunks"
    MAX_SCRAPE_URLS_PER_RUN: int = Field(default=50, ge=1, le=10000)
    MAX_EMBEDDING_TOKENS_PER_RUN: int = Field(default=500000, ge=1000, le=100000000)
    SCRAPE_EST_COST_PER_URL_USD: float = Field(default=0.01, ge=0.0, le=10.0)
    EMBED_EST_COST_PER_1K_TOKENS_USD: float = Field(default=0.00002, ge=0.0, le=1.0)

    MINDMAP_LLM_MODEL: str = "gpt-4o-mini"
    MINDMAP_LLM_TEMPERATURE: float = Field(default=0.2, ge=0.0, le=2.0)
    MINDMAP_TOPIC_REPR_K: int = Field(default=5, ge=1, le=20)
    MINDMAP_TOPIC_TEXT_LIMIT: int = Field(default=600, ge=100, le=8000)
    MINDMAP_MAX_DEPTH: int = Field(default=3, ge=1, le=10)
    MINDMAP_MIN_RECURSE_SIZE: int = Field(default=12, ge=2, le=10000)
    MINDMAP_SUB_MIN_CLUSTER_SIZE: int = Field(default=3, ge=2, le=1000)
    MINDMAP_SUB_MIN_SAMPLES: int = Field(default=2, ge=1, le=10000)
    MINDMAP_SUB_N_NEIGHBORS: int = Field(default=8, ge=2, le=200)
    MINDMAP_NER_PROVIDER: str = "spacy"
    MINDMAP_NER_MODEL: str = "xx_ent_wiki_sm"
    MINDMAP_NER_TOP_K: int = Field(default=8, ge=1, le=100)
    MINDMAP_NER_MAX_CHUNKS: int = Field(default=20, ge=1, le=200)
    MINDMAP_NER_TEXT_LIMIT: int = Field(default=8000, ge=200, le=200000)
    MINDMAP_MAX_VECTORS_PER_RUN: int = Field(default=10000, ge=1, le=500000)
    MINDMAP_MAX_LLM_CALLS_PER_RUN: int = Field(default=200, ge=0, le=10000)
    MINDMAP_MAX_TOKENS_PER_RUN: int = Field(default=200000, ge=1000, le=100000000)
    MINDMAP_UMAP_N_NEIGHBORS: int = Field(default=15, ge=2, le=200)
    MINDMAP_UMAP_N_COMPONENTS: int = Field(default=8, ge=2, le=128)
    MINDMAP_UMAP_MIN_DIST: float = Field(default=0.0, ge=0.0, le=1.0)
    MINDMAP_UMAP_RANDOM_STATE: int = 42
    MINDMAP_HDBSCAN_MIN_CLUSTER_SIZE: int = Field(default=5, ge=2, le=10000)
    MINDMAP_HDBSCAN_MIN_SAMPLES: int = Field(default=2, ge=1, le=10000)
    MINDMAP_SMALL_N_THRESHOLD: int = Field(default=20, ge=2, le=100000)

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

