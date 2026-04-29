"""Phase 10 C2 smoke check: load vectors -> UMAP/HDBSCAN -> clusters_top.json."""

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
from app.mindmap import cluster_top, reduce_umap, write_clusters_top_json
from app.mindmap.vector_loader import (
    NotFoundVectorsError,
    load_vectors_by_chunk_ids,
    load_vectors_by_run_id,
    load_vectors_by_website,
)
from app.pipeline import output_dir_slug


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
    p = argparse.ArgumentParser(description="Phase 10 C2 clustering smoke check")
    p.add_argument("--notebooklm-id", help="Notebook scope id. Optional, auto-resolve from website/company.")
    p.add_argument("--company", help="Company input used to auto-resolve notebooklm_id when omitted.")
    p.add_argument(
        "--scope-mode",
        required=True,
        choices=["by_website", "by_run_id", "by_chunk_ids"],
    )
    p.add_argument("--website")
    p.add_argument("--run-id")
    p.add_argument("--chunk-ids", nargs="*", default=[])
    p.add_argument("--mindmap-run-id", help="Optional run id; default mm_<utc>_<uuid8>.")
    p.add_argument("--output-dir", help="Optional output directory for clusters_top.json.")
    args = p.parse_args()

    notebooklm_id = _resolve_notebooklm_id(args.notebooklm_id, args.company, args.website)
    mindmap_run_id = args.mindmap_run_id.strip() if args.mindmap_run_id else _new_mindmap_run_id()
    scope = {
        "scope_mode": args.scope_mode,
        "notebooklm_id": notebooklm_id,
        "website": args.website,
        "run_id": args.run_id,
        "chunk_ids": args.chunk_ids,
    }

    try:
        if args.scope_mode == "by_website":
            if not args.website:
                raise ValueError("--website is required for by_website")
            loaded = load_vectors_by_website(notebooklm_id=notebooklm_id, website=args.website)
        elif args.scope_mode == "by_run_id":
            if not args.run_id:
                raise ValueError("--run-id is required for by_run_id")
            loaded = load_vectors_by_run_id(notebooklm_id=notebooklm_id, run_id=args.run_id)
        else:
            if not args.chunk_ids:
                raise ValueError("--chunk-ids is required for by_chunk_ids")
            loaded = load_vectors_by_chunk_ids(notebooklm_id=notebooklm_id, chunk_ids=args.chunk_ids)

        reduced = reduce_umap(loaded.vectors)
        result = cluster_top(loaded.vectors, reduced=reduced, chunk_ids=loaded.chunk_ids)
        out_dir = _resolve_output_dir(
            args.output_dir,
            company=args.company,
            website=args.website,
            mindmap_run_id=mindmap_run_id,
        )
        out_path = write_clusters_top_json(out_dir, scope, result, mindmap_run_id=mindmap_run_id)

        print(
            json.dumps(
                {
                    "ok": True,
                    "mindmap_run_id": mindmap_run_id,
                    "scope_mode": args.scope_mode,
                    "notebooklm_id": notebooklm_id,
                    "vector_count": result.metrics["vector_count"],
                    "cluster_count": result.metrics["cluster_count"],
                    "noise_ratio": result.metrics["noise_ratio"],
                    "umap_applied": result.params["umap"]["applied"],
                    "clusters_top_json": str(out_path),
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
                    "scope_mode": args.scope_mode,
                    "notebooklm_id": notebooklm_id,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception as e:  # pragma: no cover - smoke script
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "unexpected_error",
                    "detail": str(e),
                    "scope_mode": args.scope_mode,
                    "notebooklm_id": notebooklm_id,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
