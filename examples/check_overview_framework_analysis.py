"""Run 1 LLM/cluster framework analysis on latest retrieval output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.mindmap.query_layer import generate_overview_framework_analyses_for_latest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate framework analyses for latest mindmap run")
    parser.add_argument(
        "--output-dir",
        help="Base out dir (default from settings.OUTPUT_DIR)",
    )
    parser.add_argument(
        "--website",
        help="Optional website host folder under out (e.g. fptsoftware-com)",
    )
    parser.add_argument(
        "--output",
        help="Optional output file path (default: <artifact-root>/framework_analyses_overview.json)",
    )
    args = parser.parse_args()

    out_path = generate_overview_framework_analyses_for_latest(
        output_dir=args.output_dir,
        website=args.website,
        output_path=args.output,
    )
    print(json.dumps({"ok": True, "output": str(out_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

