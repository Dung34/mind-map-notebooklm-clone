"""Phase 10 D1 smoke: NER on leaf nodes + build final mindmap.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.mindmap import (
    build_entities_payload,
    build_mindmap_payload,
    write_entities_json,
    write_mindmap_json,
)
from app.mindmap.vector_loader import (
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


def main() -> None:
    p = argparse.ArgumentParser(description="Phase 10 D1 smoke check")
    p.add_argument("--clusters-tree", required=True, help="Path to clusters_tree_raw.json from C4")
    p.add_argument("--topics", required=True, help="Path to topics.json from C3")
    p.add_argument(
        "--output-dir",
        help="Directory for entities.json and mindmap.json (default: same folder as clusters_tree_raw)",
    )
    args = p.parse_args()

    tree_path = Path(args.clusters_tree).resolve()
    topics_path = Path(args.topics).resolve()
    tree_doc = json.loads(tree_path.read_text(encoding="utf-8"))
    topics_doc = json.loads(topics_path.read_text(encoding="utf-8"))

    scope = tree_doc.get("scope") or {}
    notebooklm_id = str(scope.get("notebooklm_id") or "")
    if not notebooklm_id:
        raise SystemExit("clusters_tree_raw.scope.notebooklm_id is required")

    out_dir = Path(args.output_dir).resolve() if args.output_dir else tree_path.parent

    try:
        loaded = _load_vectors_from_scope(scope, notebooklm_id)
        entities_payload = build_entities_payload(loaded, tree_doc)
        entities_path = write_entities_json(out_dir, entities_payload)

        mindmap_payload = build_mindmap_payload(loaded, tree_doc, topics_doc, entities_payload)
        mindmap_path = write_mindmap_json(out_dir, mindmap_payload)

        leaf_count = len(entities_payload.get("entities_by_leaf") or {})
        max_entities_per_leaf = max(
            [len(v) for v in (entities_payload.get("entities_by_leaf") or {}).values()] or [0]
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "mindmap_run_id": tree_doc.get("mindmap_run_id"),
                    "scope_mode": scope.get("scope_mode"),
                    "notebooklm_id": notebooklm_id,
                    "leaf_count": leaf_count,
                    "max_entities_per_leaf": max_entities_per_leaf,
                    "entities_json": str(entities_path),
                    "mindmap_json": str(mindmap_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except NotFoundVectorsError as e:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "not_found_vectors",
                    "detail": str(e),
                    "notebooklm_id": notebooklm_id,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception as e:  # pragma: no cover
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "unexpected_error",
                    "detail": str(e),
                    "notebooklm_id": notebooklm_id,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
