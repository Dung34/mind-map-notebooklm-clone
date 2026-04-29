"""Phase 10 C4 smoke: load vectors -> recursive clusters -> clusters_tree_raw.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.config import get_settings
from app.mindmap.recursive_cluster import build_clusters_tree_raw_payload
from app.mindmap.tree_cluster_artifacts import write_clusters_tree_raw_json
from app.mindmap.vector_loader import (
    NotFoundVectorsError,
    load_vectors_by_chunk_ids,
    load_vectors_by_run_id,
    load_vectors_by_website,
)
from app.pipeline import output_dir_slug


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


def _resolve_notebooklm_id(raw: str | None, company: str | None, website: str | None) -> str:
    if raw and raw.strip():
        return raw.strip()
    base = (website or company or "default").strip().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    if not base:
        base = "default"
    return f"nb_{base}"


def _new_mindmap_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"mm_{ts}_{uuid4().hex[:8]}"


def _resolve_output_dir(
    output_dir_arg: str | None,
    *,
    company: str | None,
    website: str | None,
    mindmap_run_id: str,
) -> Path:
    if output_dir_arg:
        return Path(output_dir_arg).resolve()
    settings = get_settings()
    slug = output_dir_slug(company, website, None)
    return (Path(settings.OUTPUT_DIR) / slug / "mindmap" / mindmap_run_id).resolve()


def main() -> None:
    p = argparse.ArgumentParser(description="Phase 10 C4 recursive clustering smoke check")
    p.add_argument(
        "--clusters-top",
        help="Path to clusters_top.json: reuse scope + mindmap_run_id, write next to that file unless --output-dir",
    )
    p.add_argument("--notebooklm-id", help="Notebook scope id. Optional, auto-resolve from website/company.")
    p.add_argument("--company", help="Company input used to auto-resolve notebooklm_id when omitted.")
    p.add_argument(
        "--scope-mode",
        choices=["by_website", "by_run_id", "by_chunk_ids"],
        help="Required unless --clusters-top is set.",
    )
    p.add_argument("--website")
    p.add_argument("--run-id")
    p.add_argument("--chunk-ids", nargs="*", default=[])
    p.add_argument("--mindmap-run-id", help="Optional run id; default mm_<utc>_<uuid8> or from clusters_top.")
    p.add_argument("--output-dir", help="Optional output directory for clusters_tree_raw.json.")
    args = p.parse_args()

    clusters_path: Path | None = None
    if args.clusters_top:
        clusters_path = Path(args.clusters_top).resolve()
        doc = json.loads(clusters_path.read_text(encoding="utf-8"))
        scope = dict(doc.get("scope") or {})
        notebooklm_id = str(scope.get("notebooklm_id") or "").strip()
        if not notebooklm_id:
            raise SystemExit("clusters_top.scope.notebooklm_id is required")
        mindmap_run_id = (
            args.mindmap_run_id.strip()
            if args.mindmap_run_id
            else str(doc.get("mindmap_run_id") or _new_mindmap_run_id())
        )
        scope_mode = str(scope.get("scope_mode") or "")
        out_dir = (
            Path(args.output_dir).resolve()
            if args.output_dir
            else clusters_path.parent.resolve()
        )
    else:
        if not args.scope_mode:
            raise SystemExit("Either --clusters-top or --scope-mode is required")
        notebooklm_id = _resolve_notebooklm_id(args.notebooklm_id, args.company, args.website)
        mindmap_run_id = args.mindmap_run_id.strip() if args.mindmap_run_id else _new_mindmap_run_id()
        scope = {
            "scope_mode": args.scope_mode,
            "notebooklm_id": notebooklm_id,
            "website": args.website,
            "run_id": args.run_id,
            "chunk_ids": args.chunk_ids,
        }
        scope_mode = args.scope_mode
        out_dir = _resolve_output_dir(
            args.output_dir,
            company=args.company,
            website=args.website,
            mindmap_run_id=mindmap_run_id,
        )

    try:
        loaded = _load_vectors_from_scope(scope, notebooklm_id)

        payload = build_clusters_tree_raw_payload(
            loaded,
            mindmap_run_id=mindmap_run_id,
            scope=scope,
        )
        out_path = write_clusters_tree_raw_json(out_dir, payload)

        max_d = payload["metrics"]["tree_max_depth"]
        has_subbranch = max_d >= 2

        print(
            json.dumps(
                {
                    "ok": True,
                    "mindmap_run_id": mindmap_run_id,
                    "scope_mode": scope_mode,
                    "notebooklm_id": notebooklm_id,
                    "vector_count": payload["metrics"]["vector_count"],
                    "tree_node_count": payload["metrics"]["tree_node_count"],
                    "tree_max_depth": max_d,
                    "has_subbranch_depth_ge_2": has_subbranch,
                    "clusters_tree_raw_json": str(out_path),
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
                    "scope_mode": scope_mode,
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
                    "scope_mode": scope_mode,
                    "notebooklm_id": notebooklm_id,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
