"""Phase 9 B2 smoke check: upsert/delete vectors by chunk_id."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.config import get_settings
from app.pipeline import output_dir_slug
from app.vector.pgvector_repository import PgVectorRepository, VectorRecord


def _load_embeddings(out_dir: Path) -> list[dict]:
    path = out_dir / "embeddings.jsonl"
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _load_chunks_map(out_dir: Path) -> dict[str, dict]:
    path = out_dir / "chunks.jsonl"
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        out[str(row["chunk_id"])] = row
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Phase 9 B2 vector repository smoke check")
    p.add_argument("--website", required=True)
    p.add_argument("--delete-first", action="store_true", help="Delete loaded chunk_ids before upsert")
    p.add_argument("--delete-after", action="store_true", help="Delete loaded chunk_ids after upsert")
    args = p.parse_args()

    settings = get_settings()
    slug = output_dir_slug(None, args.website, None)
    out_dir = Path(settings.OUTPUT_DIR) / slug

    emb_rows = _load_embeddings(out_dir)
    if not emb_rows:
        print(json.dumps({"ok": False, "reason": "embeddings.jsonl not found/empty"}, ensure_ascii=False, indent=2))
        return
    chunk_map = _load_chunks_map(out_dir)

    records: list[VectorRecord] = []
    for r in emb_rows:
        chunk_id = str(r["chunk_id"])
        chunk = chunk_map.get(chunk_id, {})
        records.append(
            VectorRecord(
                chunk_id=chunk_id,
                source_url=str(chunk.get("source_url", "")),
                embedding_model=str(r.get("embedding_model", settings.EMBEDDING_MODEL)),
                dim=int(r.get("dim", 0)),
                vector=list(r.get("vector", [])),
                metadata={
                    "page_title": chunk.get("page_title"),
                    "section_heading": chunk.get("section_heading"),
                    "crawled_at": chunk.get("crawled_at"),
                },
            )
        )

    repo = PgVectorRepository(vector_dim=records[0].dim if records else 1536)
    repo.ensure_table()

    ids = [r.chunk_id for r in records]
    deleted_before = repo.delete_by_chunk_ids(ids) if args.delete_first else 0
    upserted = repo.upsert_embeddings(records)
    count_after_upsert = repo.count_rows()
    deleted_after = repo.delete_by_chunk_ids(ids) if args.delete_after else 0
    count_final = repo.count_rows()

    print(
        json.dumps(
            {
                "ok": True,
                "slug": slug,
                "table": settings.VECTOR_TABLE,
                "loaded_embeddings": len(records),
                "deleted_before": deleted_before,
                "upserted": upserted,
                "count_after_upsert": count_after_upsert,
                "deleted_after": deleted_after,
                "count_final": count_final,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

