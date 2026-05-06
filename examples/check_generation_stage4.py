"""Stage 4 generation smoke: retrieval_context.json -> mindmap_generated.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.mindmap.generation_stage4 import Stage4GenerationError, generate_stage4_from_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 4 generation smoke check")
    parser.add_argument(
        "--retrieval-context",
        required=True,
        help="Path to retrieval_context.json from query layer",
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: same dir as retrieval_context -> mindmap_generated.json)",
    )
    args = parser.parse_args()

    try:
        out_path = generate_stage4_from_file(
            args.retrieval_context,
            output_path=args.output,
        )
        payload = json.loads(Path(out_path).read_text(encoding="utf-8"))
        tree = payload.get("tree") or {}
        child_count = len(tree.get("children") or []) if isinstance(tree, dict) else 0
        print(
            json.dumps(
                {
                    "ok": True,
                    "provider": payload.get("provider"),
                    "model": payload.get("model"),
                    "framework_tag": payload.get("framework_tag"),
                    "output": str(out_path),
                    "root_title": tree.get("title") if isinstance(tree, dict) else "",
                    "root_children": child_count,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except Stage4GenerationError as e:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "generation_error",
                    "detail": str(e),
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
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()

