from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.mindmap.query_layer import QueryLayerInput, run_query_layer, select_framework


def _write_artifacts(root: Path) -> None:
    topics = {
        "schema_version": 2,
        "mindmap_run_id": "mm_1",
        "cluster_0": {
            "title": "Market position",
            "summary": "Strength in enterprise projects",
            "swot_category": "Strength",
            "funnel_stage": "Consideration",
            "ms_notes": "Leverage case studies for partner outreach.",
        },
    }
    entities = {
        "schema_version": 1,
        "mindmap_run_id": "mm_1",
        "entities_by_leaf": {
            "leaf_1": [
                {"text": "enterprise", "label": "ORG", "count": 2},
                {"text": "partner", "label": "MISC", "count": 1},
            ]
        },
    }
    mindmap = {
        "schema_version": 2,
        "mindmap_run_id": "mm_1",
        "tree": {
            "id": "n_0_0",
            "node_id": "root",
            "title": "Root",
            "summary": "Business strategy",
            "swot_category": "N_A",
            "funnel_stage": "Unknown",
            "ms_notes": "",
            "children": [
                {
                    "id": "n_1_0",
                    "node_id": "leaf_1",
                    "title": "Enterprise growth",
                    "summary": "Partnership opportunities in enterprise market",
                    "swot_category": "Opportunity",
                    "funnel_stage": "Consideration",
                    "ms_notes": "Focus on strategic alliance.",
                    "children": [],
                }
            ],
        },
    }
    (root / "topics.json").write_text(json.dumps(topics, ensure_ascii=False), encoding="utf-8")
    (root / "entities.json").write_text(json.dumps(entities, ensure_ascii=False), encoding="utf-8")
    (root / "mindmap.json").write_text(json.dumps(mindmap, ensure_ascii=False), encoding="utf-8")


class TestQueryLayerStage3(unittest.TestCase):
    def test_framework_selector(self) -> None:
        sel = select_framework("Compare this company with competitors")
        self.assertEqual(sel.framework_tag, "Compare")
        self.assertGreater(sel.intent_confidence, 0.5)

    def test_fallback_query_and_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_artifacts(root)
            result = run_query_layer(QueryLayerInput(artifact_root=str(root), query=""))
            payload = result.to_dict()
            self.assertTrue(payload["query"])
            self.assertIn("framework_tag", payload)
            self.assertIn("selected_context", payload)

    def test_deterministic_result_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_artifacts(root)
            inp = QueryLayerInput(
                artifact_root=str(root),
                query="phan tich partner enterprise opportunity",
                top_k_semantic=5,
                top_k_entity=5,
                top_k_final=3,
            )
            first = run_query_layer(inp).to_dict()["selected_context"]
            second = run_query_layer(inp).to_dict()["selected_context"]
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()

