"""Stage 3 Query Layer smoke check on existing mindmap artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.mindmap.query_layer import QueryLayerInput, run_query_layer


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Stage 3 query layer on artifact folder")
    parser.add_argument(
        "--artifact-root",
        required=True,
        help="Folder containing topics.json, entities.json, mindmap.json",
    )
    parser.add_argument("--query", help="User query (optional, fallback default if omitted)")
    parser.add_argument("--top-k-semantic", type=int, default=24)
    parser.add_argument("--top-k-entity", type=int, default=20)
    parser.add_argument("--top-k-final", type=int, default=12)
    parser.add_argument(
        "--output",
        help="Output file path (default: <artifact-root>/retrieval_context.json)",
    )
    args = parser.parse_args()

    inp = QueryLayerInput(
        artifact_root=args.artifact_root,
        query=args.query,
        top_k_semantic=args.top_k_semantic,
        top_k_entity=args.top_k_entity,
        top_k_final=args.top_k_final,
    )
    result = run_query_layer(inp)
    payload = result.to_dict()

    root = Path(args.artifact_root).resolve()
    out_path = Path(args.output).resolve() if args.output else root / "retrieval_context.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "framework_tag": payload.get("framework_tag"),
                "intent_confidence": payload.get("intent_confidence"),
                "selected_context_count": len(payload.get("selected_context") or []),
                "output": str(out_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

