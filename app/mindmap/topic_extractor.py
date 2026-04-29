"""LLM topic naming for clusters (strict JSON)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings


class TopicExtractorError(RuntimeError):
    """Non-retryable topic extraction failure."""


@dataclass
class TopicPayload:
    title: str
    summary: str


def _strip_json_fence(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _parse_topic_json(content: str) -> TopicPayload:
    raw = _strip_json_fence(content)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise TopicExtractorError("LLM output is not a JSON object")
    title = data.get("title")
    summary = data.get("summary")
    if not isinstance(title, str) or not isinstance(summary, str):
        raise TopicExtractorError('Expected {"title": str, "summary": str}')
    title = title.strip()
    summary = summary.strip()
    if not title or not summary:
        raise TopicExtractorError("Empty title or summary")
    return TopicPayload(title=title, summary=summary)


def _with_network_retry(fn):
    return retry(
        reraise=True,
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)),
    )(fn)


class OpenAITopicExtractor:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for topic extraction")
        self.model = model or settings.MINDMAP_LLM_MODEL
        self.temperature = float(temperature if temperature is not None else settings.MINDMAP_LLM_TEMPERATURE)
        self.timeout_seconds = timeout_seconds or settings.HTTP_TIMEOUT

    def _chat_once(self, system: str, user: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            resp = client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        if resp.status_code in (429, 500, 502, 503, 504):
            raise httpx.ReadError(f"retryable status from chat API: {resp.status_code}")
        if resp.status_code >= 400:
            raise TopicExtractorError(f"chat api error {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise TopicExtractorError("chat api returned no choices")
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if not isinstance(content, str):
            raise TopicExtractorError("chat api returned empty content")
        return content

    def extract_topic(self, excerpts: list[str]) -> TopicPayload:
        if not excerpts:
            raise TopicExtractorError("excerpts is empty")

        system = (
            "You name topical clusters extracted from a company website.\n"
            'Return strict JSON: {"title": str, "summary": str}.\n'
            "- title: 3–7 words, English or Vietnamese matching the chunks.\n"
            "- summary: 1 sentence, ≤ 30 words, describe what unifies these chunks.\n"
            "- No emojis, no prefixes like \"Topic:\" or \"Summary:\"."
        )
        lines = []
        for i, text in enumerate(excerpts, start=1):
            lines.append(f"[{i}] {text}")
        user = "Below are representative excerpts from a cluster. Propose a topic.\n\n" + "\n".join(lines)

        last_err: Exception | None = None
        for _attempt in range(2):
            try:
                content = _with_network_retry(lambda: self._chat_once(system, user))()
                return _parse_topic_json(content)
            except (json.JSONDecodeError, TopicExtractorError) as e:
                last_err = e
                user = user + "\n\nReturn ONLY valid JSON with keys title and summary. No markdown."
            except Exception:
                raise
        raise TopicExtractorError(f"failed to parse topic JSON: {last_err}") from last_err
