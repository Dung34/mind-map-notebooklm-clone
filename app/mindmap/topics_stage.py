"""Build topics.json payload from clusters_top + loaded vectors (Phase 10 C3)."""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.mindmap.representative import representative_chunk_ids
from app.mindmap.topic_extractor import GroqTopicExtractor, OpenAITopicExtractor, mindmap_topic_extractor
from app.mindmap.vector_loader import LoadedVectors


def _excerpts_for_repr(
    loaded: LoadedVectors,
    repr_ids: list[str],
    text_limit: int,
) -> list[str]:
    out: list[str] = []
    for rid in repr_ids:
        meta = loaded.meta_by_id.get(rid) or {}
        text = meta.get("chunk_text")
        if not isinstance(text, str):
            text = ""
        text = text.strip()
        if text_limit > 0:
            text = text[:text_limit]
        out.append(text if text else "(no text)")
    return out


def extract_topics_for_clusters_top(
    loaded: LoadedVectors,
    clusters_doc: dict[str, Any],
    *,
    dry_run: bool = False,
) -> tuple[dict[str, Any], int]:
    """Return (topics.json-like dict, number of LLM calls made)."""
    settings = get_settings()
    k = settings.MINDMAP_TOPIC_REPR_K
    text_limit = settings.MINDMAP_TOPIC_TEXT_LIMIT
    max_calls = settings.MINDMAP_MAX_LLM_CALLS_PER_RUN

    mindmap_run_id = str(clusters_doc.get("mindmap_run_id") or "")
    clusters = clusters_doc.get("clusters") or []
    noise_ids = list(clusters_doc.get("noise_chunk_ids") or [])

    if not isinstance(clusters, list):
        raise ValueError("clusters_top.clusters must be a list")

    extractor: GroqTopicExtractor | OpenAITopicExtractor | None = None

    topics: dict[str, Any] = {
        "schema_version": 2,
        "mindmap_run_id": mindmap_run_id,
    }
    llm_calls = 0
    topic_provider = settings.MINDMAP_TOPIC_PROVIDER.strip().lower()
    llm_model = settings.MINDMAP_GROQ_MODEL if topic_provider == "groq" else settings.MINDMAP_LLM_MODEL

    for cl in clusters:
        if not isinstance(cl, dict):
            continue
        label = cl.get("label")
        if label is None:
            continue
        chunk_ids = cl.get("chunk_ids") or []
        if not isinstance(chunk_ids, list):
            continue
        node_id = f"cluster_{int(label)}"
        repr_ids = representative_chunk_ids(loaded, [str(x) for x in chunk_ids], top_k=k)

        if dry_run:
            topics[node_id] = {
                "cluster_label": int(label),
                "title": f"Cluster {label} (dry-run)",
                "summary": "LLM skipped; use excerpts only.",
                "swot_category": "N_A",
                "funnel_stage": "Unknown",
                "ms_notes": "",
                "representative_chunk_ids": repr_ids,
                "llm_meta": {"source": "dry_run", "model": llm_model},
            }
            continue

        if llm_calls >= max_calls:
            raise RuntimeError(
                f"MINDMAP_MAX_LLM_CALLS_PER_RUN={max_calls} exceeded while naming clusters"
            )

        if extractor is None:
            extractor = mindmap_topic_extractor()

        excerpts = _excerpts_for_repr(loaded, repr_ids, text_limit)
        topic = extractor.extract_topic(excerpts)
        llm_calls += 1
        topics[node_id] = {
            "cluster_label": int(label),
            "title": topic.title,
            "summary": topic.summary,
            "swot_category": topic.swot_category,
            "funnel_stage": topic.funnel_stage,
            "ms_notes": topic.ms_notes,
            "representative_chunk_ids": repr_ids,
            "llm_meta": {"source": topic_provider, "model": llm_model},
        }

    if noise_ids:
        repr_noise = representative_chunk_ids(loaded, [str(x) for x in noise_ids], top_k=k)
        topics["cluster_noise"] = {
            "cluster_label": -1,
            "title": "Misc / Unclustered",
            "summary": "Chunks not assigned to a dense topic cluster.",
            "swot_category": "N_A",
            "funnel_stage": "Unknown",
            "ms_notes": "",
            "representative_chunk_ids": repr_noise,
            "llm_meta": {"source": "deterministic"},
        }

    return topics, llm_calls
