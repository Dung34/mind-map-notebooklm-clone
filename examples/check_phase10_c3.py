"""Phase 10 C3 smoke: clusters_top.json -> representatives -> LLM -> topics.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.mindmap.topic_artifacts import write_topics_json
from app.mindmap.topics_stage import extract_topics_for_clusters_top
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
    p = argparse.ArgumentParser(description="Phase 10 C3 topic extraction smoke check")
    p.add_argument(
        "--clusters-top",
        required=True,
        help="Path to clusters_top.json from C2",
    )
    p.add_argument(
        "--output-dir",
        help="Directory for topics.json (default: same folder as clusters_top)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip OpenAI calls; placeholder titles only",
    )
    args = p.parse_args()

    clusters_path = Path(args.clusters_top).resolve()
    doc = json.loads(clusters_path.read_text(encoding="utf-8"))
    scope = doc.get("scope") or {}
    notebooklm_id = str(scope.get("notebooklm_id") or "")
    if not notebooklm_id:
        raise SystemExit("clusters_top.scope.notebooklm_id is required")

    out_dir = Path(args.output_dir).resolve() if args.output_dir else clusters_path.parent

    try:
        loaded = _load_vectors_from_scope(scope, notebooklm_id)
        payload, llm_calls = extract_topics_for_clusters_top(loaded, doc, dry_run=args.dry_run)
        out_path = write_topics_json(out_dir, payload)
        print(
            json.dumps(
                {
                    "ok": True,
                    "topics_json": str(out_path),
                    "llm_calls": llm_calls,
                    "dry_run": args.dry_run,
                    "notebooklm_id": notebooklm_id,
                    "scope_mode": scope.get("scope_mode"),
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
