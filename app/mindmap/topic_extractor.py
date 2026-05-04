"""LLM topic naming for clusters (strict JSON)."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings

SWOT_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        "Strength",
        "Weakness",
        "Opportunity",
        "Threat",
        "Mixed",
        "N_A",
    }
)
FUNNEL_STAGES: Final[frozenset[str]] = frozenset(
    {
        "Awareness",
        "Consideration",
        "Decision",
        "Retention",
        "Unknown",
    }
)
_DEFAULT_SWOT: Final[str] = "N_A"
_DEFAULT_FUNNEL: Final[str] = "Unknown"
_MS_NOTES_MAX_LEN: Final[int] = 500

MINDMAP_CLUSTER_TOPIC_JSON_SCHEMA: dict[str, Any] = {
    "name": "mindmap_cluster_topic",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {
                "type": "string",
                "description": "Short topic label, 3–7 words, EN or VI.",
            },
            "summary": {
                "type": "string",
                "description": "One sentence, max ~30 words, what unifies the excerpts.",
            },
            "swot_category": {
                "type": "string",
                "enum": list(SWOT_CATEGORIES),
            },
            "funnel_stage": {
                "type": "string",
                "enum": list(FUNNEL_STAGES),
            },
            "ms_notes": {
                "type": "string",
                "description": "One short M&S insight sentence; may be empty.",
            },
        },
        "required": [
            "title",
            "summary",
            "swot_category",
            "funnel_stage",
            "ms_notes",
        ],
    },
}


class TopicExtractorError(RuntimeError):
    """Non-retryable topic extraction failure."""


@dataclass
class TopicPayload:
    title: str
    summary: str
    swot_category: str
    funnel_stage: str
    ms_notes: str


def _strip_json_fence(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _normalize_enum(value: Any, allowed: frozenset[str], default: str) -> str:
    if not isinstance(value, str):
        return default
    s = value.strip()
    if s in allowed:
        return s
    lower = s.lower()
    for candidate in allowed:
        if candidate.lower() == lower:
            return candidate
    return default


def _parse_topic_json(content: str) -> TopicPayload:
    raw = _strip_json_fence(content)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        preview = (raw[:120] + "...") if len(raw) > 120 else raw
        raise TopicExtractorError(
            "Invalid JSON from model (use double quotes for keys/strings, not single quotes). "
            f"Decode error at line {e.lineno} col {e.colno}: {e.msg}. Preview: {preview!r}"
        ) from e
    if not isinstance(data, dict):
        raise TopicExtractorError("LLM output is not a JSON object")
    title = data.get("title")
    summary = data.get("summary")
    swot_raw = data.get("swot_category")
    funnel_raw = data.get("funnel_stage")
    ms_notes_raw = data.get("ms_notes")

    if not isinstance(title, str) or not isinstance(summary, str):
        raise TopicExtractorError("Expected string title and summary")
    title = title.strip()
    summary = summary.strip()
    if not title or not summary:
        raise TopicExtractorError("Empty title or summary")

    swot = _normalize_enum(swot_raw, SWOT_CATEGORIES, _DEFAULT_SWOT)
    funnel = _normalize_enum(funnel_raw, FUNNEL_STAGES, _DEFAULT_FUNNEL)

    if not isinstance(ms_notes_raw, str):
        ms_notes = ""
    else:
        ms_notes = ms_notes_raw.strip()
        if len(ms_notes) > _MS_NOTES_MAX_LEN:
            ms_notes = ms_notes[:_MS_NOTES_MAX_LEN].rstrip()

    return TopicPayload(
        title=title,
        summary=summary,
        swot_category=swot,
        funnel_stage=funnel,
        ms_notes=ms_notes,
    )


def _mindmap_topic_system_prompt() -> str:
    return (
      "You are an expert Marketing & Sales Strategist analyzing topical clusters extracted from a company's website to find actionable insights.\n"
"Rules for JSON extraction:\n"
"- title: 3–7 words, English or Vietnamese, capturing the core topic of the excerpts.\n"
"- summary: Exactly 1 sentence, ≤ 30 words, explaining what unifies these excerpts.\n"
"- swot_category: MUST be exactly one of [Strength, Weakness, Opportunity, Threat, Mixed, N_A].\n"
"  + Strength: Internal capabilities, services offered, USPs, or positive achievements.\n"
"  + Weakness: Internal flaws, limitations, or missing features.\n"
"  + Opportunity: External market trends, growing customer needs, or tech advancements.\n"
"  + Threat: Competitor actions, market risks, or barriers to entry.\n"
"  + Mixed: Use only if the excerpts have a clear balance of both positive and negative strategic traits.\n"
"  + N_A: Avoid if possible. Strictly use only if the content is purely factual without any strategic value.\n"
"- funnel_stage: MUST be exactly one of [Awareness, Consideration, Decision, Retention, Unknown].\n"
"  + Awareness: Broad concepts, industry trends, pain points, or high-level corporate introductions. (Use this as DEFAULT if unclear).\n"
"  + Consideration: Specific solutions, capabilities, architectures, or case studies.\n"
"  + Decision: Pricing, direct comparisons, guarantees, or conversion actions.\n"
"  + Retention: Customer support, updates, or loyalty programs for existing users.\n"
"  + Unknown: DO NOT USE unless absolutely necessary.\n"
"- ms_notes: 1 distinct actionable M&S insight sentence (e.g., 'Use this point to target X demographic' or 'Highlight this in pitch decks'). Empty if redundant.\n"
"- Constraints: No emojis. No prefixes. Output strictly matches the schema."
    )


def _mindmap_topic_user_prompt(excerpts: list[str]) -> str:
    lines = []
    for i, text in enumerate(excerpts, start=1):
        lines.append(f"[{i}] {text}")
    return "Below are representative excerpts from a cluster. Propose a topic.\n\n" + "\n".join(lines)


def _run_topic_extraction_loop(
    excerpts: list[str],
    chat_once: Callable[[str, str], str],
) -> TopicPayload:
    if not excerpts:
        raise TopicExtractorError("excerpts is empty")
    system = _mindmap_topic_system_prompt()
    user = _mindmap_topic_user_prompt(excerpts)
    last_err: Exception | None = None
    for _attempt in range(2):
        try:
            content = _with_network_retry(lambda: chat_once(system, user))()
            return _parse_topic_json(content)
        except (json.JSONDecodeError, TopicExtractorError) as e:
            last_err = e
            user = (
                user
                + "\n\nReturn ONLY valid JSON with keys: title, summary, swot_category, "
                "funnel_stage, ms_notes. No markdown."
            )
        except Exception:
            raise
    raise TopicExtractorError(f"failed to parse topic JSON: {last_err}") from last_err


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
            "response_format": {
                "type": "json_schema",
                "json_schema": MINDMAP_CLUSTER_TOPIC_JSON_SCHEMA,
            },
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
        return _run_topic_extraction_loop(excerpts, self._chat_once)


class GroqTopicExtractor:
    """Topic + M&S fields via Groq Chat Completions (same `TopicPayload` as OpenAI path)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        try:
            from groq import Groq
        except ImportError as e:  # pragma: no cover
            raise ImportError("Install the `groq` package (see requirements.txt)") from e

        settings = get_settings()
        key = (api_key or settings.GROQ_API_KEY or os.environ.get("GROQ_API_KEY") or "").strip()
        if not key:
            raise ValueError("GROQ_API_KEY is required for Groq topic extraction")
        self.api_key = key
        self.model = model or settings.MINDMAP_GROQ_MODEL
        self.temperature = float(temperature if temperature is not None else settings.MINDMAP_LLM_TEMPERATURE)
        self.timeout_seconds = timeout_seconds or settings.HTTP_TIMEOUT
        self._client = Groq(api_key=self.api_key)

    def _chat_once(self, system: str, user: str) -> str:
        try:
            completion = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.temperature,
                # Many Groq models only support json_object, not json_schema; parser enforces fields.
                response_format={"type": "json_object"},
                timeout=self.timeout_seconds,
            )
        except Exception as e:
            code = getattr(e, "status_code", None)
            if code is None and getattr(e, "response", None) is not None:
                code = getattr(e.response, "status_code", None)
            if code in (429, 500, 502, 503, 504):
                raise httpx.ReadError(f"retryable status from groq API: {code}") from e
            raise TopicExtractorError(f"groq chat error: {e}") from e

        choices = completion.choices or []
        if not choices:
            raise TopicExtractorError("groq returned no choices")
        msg = choices[0].message
        content = msg.content if msg is not None else None
        if not isinstance(content, str):
            raise TopicExtractorError("groq returned empty content")
        return content

    def extract_topic(self, excerpts: list[str]) -> TopicPayload:
        return _run_topic_extraction_loop(excerpts, self._chat_once)


def mindmap_topic_extractor() -> OpenAITopicExtractor | GroqTopicExtractor:
    """Instantiate topic LLM client from ``MINDMAP_TOPIC_PROVIDER`` (``openai`` or ``groq``)."""
    settings = get_settings()
    if settings.MINDMAP_TOPIC_PROVIDER.strip().lower() == "groq":
        return GroqTopicExtractor()
    return OpenAITopicExtractor()
