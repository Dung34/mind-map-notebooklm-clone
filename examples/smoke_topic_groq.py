"""Smoke: one Groq Chat call for mindmap topic extraction (TopicPayload, json_object mode).

Requires GROQ_API_KEY in .env or environment (pydantic loads .env from repo root).

From repo root:
  python examples/smoke_topic_groq.py

Optional model override:
  python examples/smoke_topic_groq.py --model llama-3.1-8b-instant
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.mindmap.topic_extractor import GroqTopicExtractor, TopicExtractorError  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Smoke: GroqTopicExtractor.extract_topic (1 call)")
    p.add_argument(
        "--model",
        help="Override Groq model (default from MINDMAP_GROQ_MODEL in settings)",
    )
    args = p.parse_args()

    excerpts = [
        "Our company offers cloud migration and managed services for enterprises in APAC.",
        "Contact sales for a demo; pricing is customized per project scope.",
    ]

    try:
        ex = GroqTopicExtractor(model=args.model)
        topic = ex.extract_topic(excerpts)
    except ValueError as e:
        if "GROQ_API_KEY" in str(e):
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "missing_api_key",
                        "hint": "Set GROQ_API_KEY in .env or the environment.",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            raise SystemExit(1) from e
        raise
    except ImportError as e:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "missing_groq_package",
                    "detail": str(e),
                    "hint": "pip install groq",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1) from e
    except TopicExtractorError as e:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "topic_extract_failed",
                    "detail": str(e),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1) from e

    out = {
        "ok": True,
        "provider": "groq",
        "model": ex.model,
        "topic": asdict(topic),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
