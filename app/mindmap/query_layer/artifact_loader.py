"""Load and normalize mindmap artifacts for Stage 3 query retrieval."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.mindmap.query_layer.contracts import CandidateItem


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_artifact(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Missing required artifact: {path}")
    return path


def _walk_tree(node: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [node]
    for child in node.get("children") or []:
        if isinstance(child, dict):
            out.extend(_walk_tree(child))
    return out


def _as_str(v: Any, fallback: str = "") -> str:
    return str(v).strip() if v is not None else fallback


def load_stage3_artifacts(artifact_root: str | Path) -> dict[str, Any]:
    root = Path(artifact_root).resolve()
    topics = _read_json(_require_artifact(root / "topics.json"))
    entities = _read_json(_require_artifact(root / "entities.json"))
    mindmap = _read_json(_require_artifact(root / "mindmap.json"))
    return {"artifact_root": str(root), "topics": topics, "entities": entities, "mindmap": mindmap}


def build_candidates_from_artifacts(artifacts: dict[str, Any]) -> list[CandidateItem]:
    topics_doc = artifacts["topics"]
    mindmap_doc = artifacts["mindmap"]
    tree = mindmap_doc.get("tree") or {}

    items: list[CandidateItem] = []
    seen_ids: set[str] = set()

    for node in _walk_tree(tree):
        node_id = _as_str(node.get("node_id")) or _as_str(node.get("id"))
        if not node_id:
            continue
        title = _as_str(node.get("title"), fallback=f"Node {node_id}")
        summary = _as_str(node.get("summary"))
        ms_notes = _as_str(node.get("ms_notes"))
        text = " ".join(x for x in (title, summary, ms_notes) if x).strip()
        if not text:
            text = title

        c = CandidateItem(
            candidate_id=f"node::{node_id}",
            source="mindmap_node",
            source_ref=node_id,
            title=title,
            text=text,
            swot_category=_as_str(node.get("swot_category"), "N_A") or "N_A",
            funnel_stage=_as_str(node.get("funnel_stage"), "Unknown") or "Unknown",
        )
        items.append(c)
        seen_ids.add(c.candidate_id)

    for key, topic in topics_doc.items():
        if key in {"schema_version", "mindmap_run_id"} or not isinstance(topic, dict):
            continue
        title = _as_str(topic.get("title"), fallback=key)
        summary = _as_str(topic.get("summary"))
        notes = _as_str(topic.get("ms_notes"))
        text = " ".join(x for x in (title, summary, notes) if x).strip() or title
        cid = f"topic::{key}"
        if cid in seen_ids:
            continue
        items.append(
            CandidateItem(
                candidate_id=cid,
                source="topic_entry",
                source_ref=key,
                title=title,
                text=text,
                swot_category=_as_str(topic.get("swot_category"), "N_A") or "N_A",
                funnel_stage=_as_str(topic.get("funnel_stage"), "Unknown") or "Unknown",
            )
        )

    return items

