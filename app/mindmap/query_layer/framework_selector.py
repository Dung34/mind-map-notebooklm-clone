"""Rule-based intent detection and framework selection for Stage 3."""

from __future__ import annotations

import re
from typing import Iterable

from app.mindmap.query_layer.contracts import FrameworkSelection, FrameworkTag


_FRAMEWORK_RULES: dict[FrameworkTag, tuple[str, ...]] = {
    "SWOT": (
        "swot",
        "strength",
        "weakness",
        "opportunity",
        "threat",
    ),
    "Compare": (
        "compare",
        "competitor",
        "benchmark",
        "versus",
        "vs",
        "alternative",
        "comparison",
        "difference",
    ),
    "RootCause": (
        "root cause",
        "why",
        "reason",
        "driver",
        "because",
        "underlying issue",
        "causal",
    ),
    "ProsCons": (
        "pros and cons",
        "pros cons",
        "pros",
        "cons",
        "trade-off",
        "tradeoff",
        "drawback",
        "advantages and disadvantages",
        "benefits and risks",
    ),
    "DeepDive": (
        "deep dive",
        "in-depth",
        "detailed analysis",
        "breakdown",
        "thorough",
        "comprehensive",
    ),
}

_EXACT_TRIGGER_MAP: dict[FrameworkTag, tuple[str, ...]] = {
    "Compare": ("compare", "versus", " vs ", "comparison"),
    "RootCause": ("root cause", "why", "because", "driver"),
    "ProsCons": ("pros and cons", "trade-off", "tradeoff", "drawback"),
    "DeepDive": ("deep dive", "in-depth", "detailed analysis", "breakdown"),
    "SWOT": ("swot",),
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _count_hits(query: str, keywords: Iterable[str]) -> int:
    q = _normalize(query)
    return sum(1 for kw in keywords if kw in q)


def select_framework(query: str) -> FrameworkSelection:
    q = _normalize(query)
    if not q:
        return FrameworkSelection(framework_tag="DeepDive", intent_confidence=0.5, matched_rules=[])

    # Exact triggers have priority to reduce SWOT over-selection.
    for tag in ("Compare", "RootCause", "ProsCons", "DeepDive", "SWOT"):
        triggers = _EXACT_TRIGGER_MAP[tag]  # type: ignore[index]
        matched = [kw for kw in triggers if kw in q]
        if matched:
            confidence = min(0.98, 0.72 + 0.08 * len(matched))
            return FrameworkSelection(
                framework_tag=tag,  # type: ignore[arg-type]
                intent_confidence=confidence,
                matched_rules=matched[:5],
            )

    scores: dict[FrameworkTag, int] = {
        tag: _count_hits(q, kws) for tag, kws in _FRAMEWORK_RULES.items()
    }
    best_tag: FrameworkTag = max(scores, key=scores.get)
    best_score = scores[best_tag]

    if best_score <= 0:
        return FrameworkSelection(framework_tag="DeepDive", intent_confidence=0.5, matched_rules=[])

    matched = [kw for kw in _FRAMEWORK_RULES[best_tag] if kw in q]
    confidence = min(0.95, 0.55 + 0.12 * best_score)
    return FrameworkSelection(
        framework_tag=best_tag,
        intent_confidence=confidence,
        matched_rules=matched[:5],
    )

