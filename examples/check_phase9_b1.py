"""Phase 9 B1: batch embeddings + retry smoke check."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.config import get_settings
from app.embed.openai_embedding_service import EmbeddingItem, OpenAIEmbeddingService
from app.pipeline import output_dir_slug


def _load_input_chunks(out_dir: Path) -> list[dict]:
    delta_path = out_dir / "chunks_delta.jsonl"
    base_path = out_dir / "chunks.jsonl"
    source = delta_path if delta_path.exists() and delta_path.stat().st_size > 0 else base_path
    if not source.exists():
        return []
    rows: list[dict] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description="Phase 9 B1 embedding smoke check")
    p.add_argument("--website", required=True)
    p.add_argument("--limit", type=int, default=0, help="Embed first N chunks (0 = all)")
    args = p.parse_args()

    settings = get_settings()
    slug = output_dir_slug(None, args.website, None)
    out_dir = Path(settings.OUTPUT_DIR) / slug
    chunks = _load_input_chunks(out_dir)
    if args.limit > 0:
        chunks = chunks[: args.limit]
    if not chunks:
        print(json.dumps({"ok": False, "reason": "no chunks input found"}, ensure_ascii=False, indent=2))
        return

    items = [EmbeddingItem(chunk_id=str(c["chunk_id"]), text=str(c["text"])) for c in chunks]
    service = OpenAIEmbeddingService()
    results = service.embed_items(items)

    out_path = out_dir / "embeddings.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(
                json.dumps(
                    {
                        "chunk_id": r.chunk_id,
                        "embedding_model": r.embedding_model,
                        "dim": r.dim,
                        "vector": r.vector,
                        "vector_checksum": r.vector_checksum,
                        "upsert_status": r.upsert_status,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    print(
        json.dumps(
            {
                "ok": True,
                "slug": slug,
                "embedded_count": len(results),
                "output": str(out_path),
                "model": settings.EMBEDDING_MODEL,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

