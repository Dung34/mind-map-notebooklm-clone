"""NER extraction for leaf nodes in clusters tree."""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.config import get_settings
from app.mindmap.vector_loader import LoadedVectors


def _leaf_chunk_ids_by_node(tree: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}

    def _walk(node: dict[str, Any]) -> None:
        children = node.get("children") or []
        if not children:
            node_id = str(node.get("node_id") or "")
            if node_id:
                out[node_id] = [str(x) for x in (node.get("chunk_ids") or [])]
            return
        for child in children:
            if isinstance(child, dict):
                _walk(child)

    _walk(tree)
    return out


def _entity_rows_spacy(leaf_text: str) -> list[tuple[str, str]]:
    settings = get_settings()
    try:
        import spacy  # type: ignore
    except Exception:
        return []
    try:
        nlp = spacy.load(settings.MINDMAP_NER_MODEL)
    except Exception:
        return []
    doc = nlp(leaf_text)
    rows: list[tuple[str, str]] = []
    for ent in doc.ents:
        text = ent.text.strip()
        label = ent.label_.strip()
        if text and label:
            rows.append((text, label))
    return rows


def _extract_leaf_entities(loaded: LoadedVectors, chunk_ids: list[str]) -> list[dict[str, Any]]:
    settings = get_settings()
    max_chunks = settings.MINDMAP_NER_MAX_CHUNKS
    text_limit = settings.MINDMAP_NER_TEXT_LIMIT
    top_k = settings.MINDMAP_NER_TOP_K

    parts: list[str] = []
    for cid in chunk_ids[:max_chunks]:
        meta = loaded.meta_by_id.get(cid) or {}
        text = str(meta.get("chunk_text") or "").strip()
        if text:
            parts.append(text)
    if not parts:
        return []

    leaf_text = "\n\n".join(parts)[:text_limit]
    provider = settings.MINDMAP_NER_PROVIDER.strip().lower()
    rows: list[tuple[str, str]]
    if provider == "spacy":
        rows = _entity_rows_spacy(leaf_text)
    else:
        # Optional provider (llm) is out of scope for D1 implementation.
        rows = []

    if not rows:
        return []

    counter = Counter(rows)
    return [
        {"text": key[0], "label": key[1], "count": int(count)}
        for key, count in counter.most_common(top_k)
    ]


def build_entities_payload(
    loaded: LoadedVectors,
    tree_doc: dict[str, Any],
) -> dict[str, Any]:
    tree = tree_doc.get("tree") or {}
    leaves = _leaf_chunk_ids_by_node(tree)
    entities_by_leaf = {node_id: _extract_leaf_entities(loaded, cids) for node_id, cids in leaves.items()}
    settings = get_settings()
    return {
        "schema_version": 1,
        "mindmap_run_id": str(tree_doc.get("mindmap_run_id") or ""),
        "provider": settings.MINDMAP_NER_PROVIDER,
        "model": settings.MINDMAP_NER_MODEL,
        "entities_by_leaf": entities_by_leaf,
    }
