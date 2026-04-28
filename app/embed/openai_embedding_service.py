"""OpenAI embedding service with batching and retry policy."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings


class EmbeddingServiceError(RuntimeError):
    """Raised when embedding provider fails with non-retryable errors."""


@dataclass
class EmbeddingItem:                                                                                
    chunk_id: str
    text: str


@dataclass
class EmbeddingResult:
    chunk_id: str
    embedding_model: str
    dim: int
    vector: list[float]
    vector_checksum: str
    upsert_status: str = "embedded"
    error: str | None = None


def _batched(items: list[EmbeddingItem], size: int) -> Iterable[list[EmbeddingItem]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _checksum(vec: list[float]) -> str:
    payload = ",".join(f"{x:.8f}" for x in vec)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _retry_decorator(max_attempts: int):
    return retry(
        reraise=True,
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)),
    )


class OpenAIEmbeddingService:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        batch_size: int | None = None,
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for embedding service")
        self.model = model or settings.EMBEDDING_MODEL
        self.batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
        self.timeout_seconds = timeout_seconds or settings.HTTP_TIMEOUT
        self.max_retries = max_retries if max_retries is not None else settings.EMBEDDING_MAX_RETRIES

    def _embed_batch_once(self, batch: list[EmbeddingItem]) -> list[EmbeddingResult]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "input": [item.text for item in batch],
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            resp = client.post("https://api.openai.com/v1/embeddings", headers=headers, json=payload)
        if resp.status_code in (429, 500, 502, 503, 504):
            raise httpx.ReadError(f"retryable status from embeddings API: {resp.status_code}")
        if resp.status_code >= 400:
            raise EmbeddingServiceError(
                f"embedding api error {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json().get("data", [])
        if len(data) != len(batch):
            raise EmbeddingServiceError(
                f"embedding output size mismatch: expected={len(batch)} got={len(data)}"
            )

        out: list[EmbeddingResult] = []
        for item, row in zip(batch, data):
            vec = row.get("embedding") or []
            out.append(
                EmbeddingResult(
                    chunk_id=item.chunk_id,
                    embedding_model=self.model,
                    dim=len(vec),
                    vector=vec,
                    vector_checksum=_checksum(vec),
                )
            )
        return out

    def embed_items(self, items: list[EmbeddingItem]) -> list[EmbeddingResult]:
        if not items:
            return []

        wrapped = _retry_decorator(max_attempts=max(1, self.max_retries + 1))(self._embed_batch_once)
        out: list[EmbeddingResult] = []
        for batch in _batched(items, self.batch_size):
            out.extend(wrapped(batch))
        return out

