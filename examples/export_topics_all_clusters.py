"""Run topic LLM for every cluster in clusters_top.json; write one JSON file (same shape as topics.json)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.mindmap.topics_stage import extract_topics_for_clusters_top  # noqa: E402
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


def main() -> None:
    p = argparse.ArgumentParser(description="Export topics.json for all clusters in clusters_top.json")
    p.add_argument("--clusters-top", required=True, type=Path, help="Path to clusters_top.json")
    p.add_argument(
        "--output",
        type=Path,
        help="Output JSON path (default: <dir of clusters_top>/topics_export_<utc>.json)",
    )
    p.add_argument("--dry-run", action="store_true", help="Skip LLM; placeholders only")
    args = p.parse_args()

    clusters_path = args.clusters_top.expanduser().resolve()
    if not clusters_path.is_file():
        raise SystemExit(f"File not found: {clusters_path}")

    doc = json.loads(clusters_path.read_text(encoding="utf-8"))
    scope = doc.get("scope") or {}
    notebooklm_id = str(scope.get("notebooklm_id") or "")
    if not notebooklm_id:
        raise SystemExit("clusters_top.scope.notebooklm_id is required")

    if args.output:
        out_path = args.output.expanduser().resolve()
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = clusters_path.parent / f"topics_export_{ts}.json"

    try:
        loaded = _load_vectors_from_scope(scope, notebooklm_id)
        payload, llm_calls = extract_topics_for_clusters_top(loaded, doc, dry_run=args.dry_run)
    except NotFoundVectorsError as e:
        print(json.dumps({"ok": False, "error": "not_found_vectors", "detail": str(e)}, indent=2))
        raise SystemExit(1) from e

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "output": str(out_path),
                "llm_calls": llm_calls,
                "dry_run": args.dry_run,
                "mindmap_run_id": payload.get("mindmap_run_id"),
                "schema_version": payload.get("schema_version"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
