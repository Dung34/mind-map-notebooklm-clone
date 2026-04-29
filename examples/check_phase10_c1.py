"""Phase 10 C1 smoke check: load vectors by scope from rag_chunks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.mindmap.vector_loader import (  # noqa: E402
    NotFoundVectorsError,
    load_vectors_by_chunk_ids,
    load_vectors_by_run_id,
    load_vectors_by_website,
)


def main() -> None:
    p = argparse.ArgumentParser(description="Phase 10 C1 vector loader smoke check")
    p.add_argument("--notebooklm-id", required=True)
    p.add_argument(
        "--scope-mode",
        required=True,
        choices=["by_website", "by_run_id", "by_chunk_ids"],
    )
    p.add_argument("--website")
    p.add_argument("--run-id")
    p.add_argument("--chunk-ids", nargs="*", default=[])
    args = p.parse_args()

    try:
        if args.scope_mode == "by_website":
            if not args.website:
                raise ValueError("--website is required for by_website")
            loaded = load_vectors_by_website(
                notebooklm_id=args.notebooklm_id,
                website=args.website,
            )
        elif args.scope_mode == "by_run_id":
            if not args.run_id:
                raise ValueError("--run-id is required for by_run_id")
            loaded = load_vectors_by_run_id(
                notebooklm_id=args.notebooklm_id,
                run_id=args.run_id,
            )
        else:
            if not args.chunk_ids:
                raise ValueError("--chunk-ids is required for by_chunk_ids")
            loaded = load_vectors_by_chunk_ids(
                notebooklm_id=args.notebooklm_id,
                chunk_ids=args.chunk_ids,
            )

        unique_urls = len({str(m.get("source_url") or "") for m in loaded.meta_by_id.values()})
        sample_ids = loaded.chunk_ids[:5]
        print(
            json.dumps(
                {
                    "ok": True,
                    "scope_mode": args.scope_mode,
                    "vector_count": int(loaded.vectors.shape[0]),
                    "vector_dim": int(loaded.vectors.shape[1]),
                    "unique_urls": unique_urls,
                    "sample_chunk_ids": sample_ids,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except NotFoundVectorsError as e:
        print(json.dumps({"ok": False, "error": "not_found_vectors", "detail": str(e)}, ensure_ascii=False, indent=2))
    except Exception as e:  # pragma: no cover - smoke script
        print(json.dumps({"ok": False, "error": "unexpected_error", "detail": str(e)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

