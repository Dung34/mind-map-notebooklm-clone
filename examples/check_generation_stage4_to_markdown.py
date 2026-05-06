"""Stage 4 utility: convert mindmap_generated.json to markdown outline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.mindmap.generation_stage4 import Stage4GenerationError, stage4_json_file_to_markdown_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert stage4 mindmap JSON to markdown")
    parser.add_argument(
        "--input",
        required=True,
        help="Path to mindmap_generated.json",
    )
    parser.add_argument(
        "--output",
        help="Output markdown path (default: same path with .md extension)",
    )
    args = parser.parse_args()

    try:
        out_path = stage4_json_file_to_markdown_file(args.input, output_path=args.output)
        print(
            json.dumps(
                {
                    "ok": True,
                    "input": str(Path(args.input).resolve()),
                    "output": str(out_path),
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

