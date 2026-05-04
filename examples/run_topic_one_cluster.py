"""One topic LLM call for a single HDBSCAN cluster (by label) from clusters_top.json."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.config import get_settings  # noqa: E402
from app.mindmap.representative import representative_chunk_ids  # noqa: E402
from app.mindmap.topic_extractor import TopicExtractorError, mindmap_topic_extractor  # noqa: E402
from app.mindmap.vector_loader import (  # noqa: E402
    NotFoundVectorsError,
    load_vectors_by_chunk_ids,
    load_vectors_by_run_id,
    load_vectors_by_website,
)


def _load_vectors_from_scope(scope: dict, notebooklm_id: str):
    mode = scope.get("scope_mode")
    if mode == "by_website":
        website = scope.get("website")
        if not website:
            raise ValueError("scope.website required for by_website")
        return load_vectors_by_website(notebooklm_id=notebooklm_id, website=str(website))
    if mode == "by_run_id":
        run_id = scope.get("run_id")
        if not run_id:
            raise ValueError("scope.run_id required for by_run_id")
        return load_vectors_by_run_id(notebooklm_id=notebooklm_id, run_id=str(run_id))
    if mode == "by_chunk_ids":
        chunk_ids = scope.get("chunk_ids") or []
        if not chunk_ids:
            raise ValueError("scope.chunk_ids required for by_chunk_ids")
        return load_vectors_by_chunk_ids(
            notebooklm_id=notebooklm_id, chunk_ids=[str(x) for x in chunk_ids]
        )
    raise ValueError(f"Unknown scope_mode: {mode!r}")


def _excerpts_for_repr(loaded, repr_ids: list[str], text_limit: int) -> list[str]:
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


def main() -> None:
    p = argparse.ArgumentParser(description="One topic extract call for cluster label N")
    p.add_argument("--clusters-top", required=True, type=Path, help="Path to clusters_top.json")
    p.add_argument("--label", type=int, required=True, help="HDBSCAN cluster label (e.g. 1)")
    args = p.parse_args()

    clusters_path = args.clusters_top.expanduser().resolve()
    if not clusters_path.is_file():
        raise SystemExit(f"File not found: {clusters_path}")

    doc = json.loads(clusters_path.read_text(encoding="utf-8"))
    scope = doc.get("scope") or {}
    notebooklm_id = str(scope.get("notebooklm_id") or "")
    if not notebooklm_id:
        raise SystemExit("clusters_top.scope.notebooklm_id is required")

    clusters = doc.get("clusters") or []
    cl = None
    for c in clusters:
        if isinstance(c, dict) and c.get("label") == args.label:
            cl = c
            break
    if cl is None:
        raise SystemExit(f"No cluster with label={args.label} in clusters_top.json")

    chunk_ids = cl.get("chunk_ids") or []
    if not isinstance(chunk_ids, list) or not chunk_ids:
        raise SystemExit("cluster has no chunk_ids")

    settings = get_settings()
    k = settings.MINDMAP_TOPIC_REPR_K
    text_limit = settings.MINDMAP_TOPIC_TEXT_LIMIT
    provider = settings.MINDMAP_TOPIC_PROVIDER.strip().lower()
    llm_model = settings.MINDMAP_GROQ_MODEL if provider == "groq" else settings.MINDMAP_LLM_MODEL

    try:
        loaded = _load_vectors_from_scope(scope, notebooklm_id)
        repr_ids = representative_chunk_ids(loaded, [str(x) for x in chunk_ids], top_k=k)
        excerpts = _excerpts_for_repr(loaded, repr_ids, text_limit)
        ex = mindmap_topic_extractor()
        topic = ex.extract_topic(excerpts)
    except NotFoundVectorsError as e:
        print(json.dumps({"ok": False, "error": "not_found_vectors", "detail": str(e)}, indent=2))
        raise SystemExit(1) from e
    except TopicExtractorError as e:
        print(json.dumps({"ok": False, "error": "topic_extract_failed", "detail": str(e)}, indent=2))
        raise SystemExit(1) from e

    out = {
        "ok": True,
        "llm_calls": 1,
        "cluster_label": args.label,
        "node_id": f"cluster_{args.label}",
        "provider": provider,
        "model": llm_model,
        "representative_chunk_ids": repr_ids,
        "topic": asdict(topic),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
