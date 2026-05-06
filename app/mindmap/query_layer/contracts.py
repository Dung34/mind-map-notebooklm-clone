"""Contracts for Stage 3 query layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

FrameworkTag = Literal["SWOT", "DeepDive", "Compare", "RootCause", "ProsCons"]
CandidateSource = Literal["mindmap_node", "topic_entry"]

DEFAULT_STRATEGIC_QUERY = (
    "Assess the company's position in the industry ecosystem, including partners, suppliers, customers, and strategic dependencies"
)


@dataclass(slots=True)
class QueryLayerInput:
    artifact_root: str
    query: str | None = None
    top_k_semantic: int = 24
    top_k_entity: int = 20
    top_k_final: int = 12

    def normalized_query(self) -> str:
        q = (self.query or "").strip()
        return q if q else DEFAULT_STRATEGIC_QUERY


@dataclass(slots=True)
class FrameworkSelection:
    framework_tag: FrameworkTag
    intent_confidence: float
    matched_rules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "framework_tag": self.framework_tag,
            "intent_confidence": round(float(self.intent_confidence), 4),
            "matched_rules": list(self.matched_rules),
        }


@dataclass(slots=True)
class CandidateItem:
    candidate_id: str
    source: CandidateSource
    source_ref: str
    title: str
    text: str
    swot_category: str = "N_A"
    funnel_stage: str = "Unknown"
    framework_tag: str = ""
    semantic_score: float = 0.0
    entity_score: float = 0.0
    framework_boost: float = 0.0
    final_score: float = 0.0
    matched_entities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("semantic_score", "entity_score", "framework_boost", "final_score"):
            data[key] = round(float(data[key]), 6)
        return data


@dataclass(slots=True)
class QueryLayerResult:
    query: str
    framework_tag: FrameworkTag
    intent_confidence: float
    selected_context: list[CandidateItem]
    semantic_candidates: list[CandidateItem]
    entity_candidates: list[CandidateItem]
    debug: dict[str, Any]
    schema_version: int = 1
    flow_mode: str = "business_strategy"
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "flow_mode": self.flow_mode,
            "generated_at": self.generated_at,
            "query": self.query,
            "framework_tag": self.framework_tag,
            "intent_confidence": round(float(self.intent_confidence), 4),
            "candidates": {
                "semantic": [c.to_dict() for c in self.semantic_candidates],
                "entity": [c.to_dict() for c in self.entity_candidates],
            },
            "selected_context": [c.to_dict() for c in self.selected_context],
            "debug": self.debug,
        }

