"""Write clusters_tree_raw.json (Phase 10 C4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_clusters_tree_raw_json(out_dir: str | Path, payload: dict[str, Any]) -> Path:
    target_dir = Path(out_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / "clusters_tree_raw.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path
