## Mindmap Pipeline Overview (Phase 10)

Tài liệu này mô tả data flow end-to-end để sinh **mindmap chiến lược** từ embedding thô đến `mindmap_generated.md`, tập trung vào kiến trúc **overview mode** (không phụ thuộc query người dùng).

Chuỗi bước chính:

1. **Clustering & Topic Naming**
2. **Overview Retrieval & Multi-framework Analyses**
3. **Synthesis Mindmap Generation**

---

### 1. Clustering & Topic Naming

#### 1.1. Clustering vectors → `clusters_top.json`

Nguồn dữ liệu:

- Embeddings trong bảng `rag_chunks` (Postgres), load qua `app/mindmap/vector_loader.py` → `LoadedVectors`:
  - `chunk_ids: list[str]`
  - `vectors: np.ndarray`
  - `meta_by_id: dict[str, dict]` (chứa `chunk_text`, `source_url`, `metadata`, ...)

Clustering (UMAP + HDBSCAN) tạo ra:

- `out/<website>/mindmap/<run_id>/clusters_top.json`

```json
{
  "schema_version": 1,
  "mindmap_run_id": "mm_...",
  "vector_count": 57,
  "metrics": {...},
  "chunk_ids": ["...", "..."],
  "labels": [3, 4, 3, ...],
  "clusters": [
    {
      "label": 3,
      "size": 27,
      "chunk_ids": ["...", "..."]
    },
    ...
  ],
  "noise_chunk_ids": []
}
```

#### 1.2. Đặt tên topic cho mỗi cluster → `topics.json`

File: `app/mindmap/topics_stage.py`

Hàm chính: `extract_topics_for_clusters_top(loaded: LoadedVectors, clusters_doc: dict, dry_run: bool = False)`

Bước:

- Với mỗi cluster trong `clusters_top.clusters`:
  - Lấy `chunk_ids` của cluster.
  - Chọn **k chunk đại diện** gần centroid nhất:
    - `repr_ids = representative_chunk_ids(loaded, chunk_ids, top_k=k)`
  - Cắt `chunk_text` của các repr để làm `excerpts` input cho LLM.
  - Gọi LLM (`mindmap_topic_extractor`, OpenAI hoặc Groq) để sinh:
    - `title`
    - `summary`
    - `swot_category`
    - `funnel_stage`
    - `ms_notes`
- Viết kết quả vào:

```json
{
  "schema_version": 2,
  "mindmap_run_id": "mm_...",
  "cluster_0": {
    "cluster_label": 0,
    "title": "Digital Transformation Services",
    "summary": "Company offers various digital services",
    "swot_category": "Strength",
    "funnel_stage": "Consideration",
    "ms_notes": "...",
    "representative_chunk_ids": ["...", "..."],
    "llm_meta": {"source": "openai|groq", "model": "..."}
  },
  "cluster_1": {...},
  "...": {...}
}
```

`topics.json` là **topic layer** chịu trách nhiệm đặt nhãn, thêm SWOT + funnel cho từng cluster.

---

### 2. Overview Retrieval & Multi-framework Analyses

Mục tiêu: xây **context tổng quan** và phân tích theo 5 framework cho mỗi cluster trước khi tổng hợp thành mindmap.

#### 2.1. Overview Retrieval → `retrieval_context.json`

File: `app/mindmap/query_layer/overview_context.py` (gọi từ `orchestrator.py` khi `retrieval_mode == "overview"`).

Đầu vào:

- `topics.json` (có `representative_chunk_ids`)
- `clusters_top.json`
- Scope trong `clusters_top.scope` để load `chunk_text` nếu cần.

Hàm chính: `build_overview_context_candidates(artifacts, top_k_final, rep_ratio)`

Logic tóm tắt:

- Ghép thông tin theo cluster:
  - `all_chunk_ids` = danh sách chunk của cluster từ `clusters_top`.
  - `rep_ids` = `representative_chunk_ids` từ `topics.json`.
  - `cov_ids` = các chunk còn lại trong cluster (coverage).
- Tạo `CandidateItem` cho mỗi chunk được chọn:
  - `candidate_id = "chunk::<chunk_id>"`
  - `source_ref = "cluster_<label>"`
  - `title = topic.title`
  - `text = chunk_text` (nếu load được) hoặc `summary + ms_notes`
  - `swot_category`, `funnel_stage` lấy từ topic.
  - `framework_tag = "representative"` hoặc `"coverage"`.
  - `semantic_score` giả định để ưu tiên repr.
- Dedupe + fairness:
  - Đảm bảo mỗi cluster có ít nhất một repr trong `selected_context`.
  - Chia quota rep/coverage theo `overview_rep_ratio` (mặc định 0.7).
- Sắp xếp theo `final_score` và cắt theo `top_k_final`.

Output: `retrieval_context.json`

```json
{
  "schema_version": 1,
  "flow_mode": "business_strategy",
  "query": "Assess the company's position in the industry ecosystem, ...",
  "framework_tag": "SWOT",
  "selected_context": [
    {
      "candidate_id": "chunk::128c...",
      "source": "topic_entry",
      "source_ref": "cluster_5",
      "title": "Privacy Centric Personalization",
      "text": "...",
      "swot_category": "Opportunity",
      "funnel_stage": "Awareness",
      "framework_tag": "representative",
      "semantic_score": 1.0,
      "final_score": 0.88,
      "matched_entities": []
    },
    "..."
  ],
  "debug": {
    "overview": {
      "rep_ratio": 0.7,
      "clusters_used": 6,
      ...
    }
  }
}
```

#### 2.2. Multi-framework Analyses per Cluster → `framework_analyses_overview.json`

File: `app/mindmap/query_layer/framework_batch_analysis.py`

Hàm public:

- `generate_overview_framework_analyses(artifact_root, output_path=None)`
- `generate_overview_framework_analyses_for_latest(output_dir=None, website=None, output_path=None)`

Pipeline:

1. Đọc `retrieval_context.json`, nhóm context theo `source_ref`:
   - `_group_cluster_context(retrieval_payload)`:
     - `cluster_id -> { title, summary, rep[], cov[] }`
2. Với mỗi `cluster_id`:
   - Xây `system` prompt multi-framework (SWOT, DeepDive, Compare, RootCause, ProsCons).
   - Xây `user` prompt:
     - cluster metadata: `cluster_id`, `cluster_title`, `cluster_summary`
     - `REPRESENTATIVE_SNIPPETS` (repr context)
     - `COVERAGE_SNIPPETS` (coverage context)
   - Gọi `_call_llm(system, user)` → JSON chứa đủ 5 framework và `cross_framework_synthesis`.
3. Gộp tất cả cluster thành:

`framework_analyses_overview.json`:

```json
{
  "schema_version": 1,
  "generated_at": "...",
  "artifact_root": ".../mm_.../",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "cluster_count": 6,
  "frameworks": ["SWOT", "DeepDive", "Compare", "RootCause", "ProsCons"],
  "clusters": {
    "cluster_0": {
      "cluster_id": "cluster_0",
      "cluster_title": "Digital Transformation Services",
      "framework_analyses": {
        "SWOT": { "summary": "...", ... },
        "DeepDive": { "summary": "...", ... },
        "Compare": { "summary": "...", ... },
        "RootCause": { "summary": "...", ... },
        "ProsCons": { "summary": "...", ... }
      },
      "cross_framework_synthesis": {
        "top_3_priorities": ["...", "...", "..."],
        "biggest_risk": "...",
        "next_best_action": "..."
      }
    },
    "cluster_1": { ... },
    "...": { ... }
  }
}
```

Tầng này cung cấp **tổng quan chiến lược theo 5 góc nhìn** cho từng cluster, trước khi tổng hợp thành mindmap.

---

### 3. Synthesis Mindmap Generation

#### 3.1. Sinh mindmap từ analyses → `mindmap_generated.json`

File: `app/mindmap/generation_stage4.py`

Hàm chính cho synthesis từ analyses:

- `generate_stage4_tree_from_analyses(analyses_doc: dict[str, Any]) -> dict[str, Any]`
- `generate_stage4_from_analyses_file(analyses_path, output_path=None) -> Path`

**System prompt:**

- Vai trò: *senior strategy synthesis engine*.
- Nhiệm vụ: tạo **một** cây mindmap business từ multi-cluster analyses.
- Quy định:
  - Không hallucinate (facts, numbers, clients, competitors...).
  - Sử dụng tín hiệu từ cả 5 framework (SWOT, DeepDive, Compare, RootCause, ProsCons).
  - Cấu trúc cứng:
    - root: type = `root`, có 4–6 theme children.
    - theme: type = `theme`, có 2–4 insight children.
    - insight: type = `insight`, có 1–3 action children.
    - action: type = `action`, `children = []`.
  - `title`: 3–8 từ, business specific.
  - `summary`: 1 câu, ≤ 30 từ.

**User prompt từ analyses:**

- `_user_prompt_from_analyses(analyses_doc)` tạo context dạng text:
  - Cho mỗi cluster:
    - `cluster_id`, `cluster_title`.
    - `cross_framework_synthesis.top_3_priorities`.
    - `cross_framework_synthesis.biggest_risk`.
    - `cross_framework_synthesis.next_best_action`.
    - `framework_analyses.<Framework>.summary` cho 5 framework.
  - Kèm hướng dẫn:
    - Synthesize cross-cluster, không summary tuần tự từng cluster.
    - Tạo 4–6 theme, mỗi theme 2–4 insight, mỗi insight 1–3 action.
    - Chỉ dùng evidence từ analyses, nếu thiếu: `"Insufficient evidence from provided analyses."`.

**Validate & auto-repair:**

- `_validate_tree_node(...)`:
  - Kiểm tra type (`root`, `theme`, `insight`, `action`).
  - Kiểm tra số lượng children theo rule:
    - root: 4–6 theme.
    - theme: 2–4 insight.
    - insight: 1–3 action.
    - action: 0 children.
- `_generate_tree_with_repair(system, user_base, provider)`:
  - Lần 1: generate + validate.
  - Nếu fail: lần 2 gửi lại lỗi validate + yêu cầu regenerate đúng schema.
  - Nếu vẫn fail: raise `Stage4GenerationError`.

**Output:** `mindmap_generated.json`

```json
{
  "schema_version": 1,
  "flow_mode": "business_strategy",
  "generated_at": "...",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "framework_tag": "SYNTHESIS",
  "query": "overview synthesis from framework analyses",
  "tree": {
    "title": "Strategic Mindmap for Business Growth",
    "summary": "...",
    "type": "root",
    "children": [
      {
        "title": "Privacy-Centric Strategies",
        "summary": "...",
        "type": "theme",
        "children": [
          {
            "title": "Enhance Data Privacy Practices",
            "summary": "...",
            "type": "insight",
            "children": [
              {
                "title": "Develop Comprehensive Privacy Policy",
                "summary": "...",
                "type": "action",
                "children": []
              }
            ]
          },
          "..."
        ]
      },
      "..."
    ]
  }
}
```

#### 3.2. Xuất markdown → `mindmap_generated.md`

File: `app/mindmap/generation_stage4.py`

Hàm:

- `stage4_json_to_markdown(stage4_payload)`
- `stage4_json_file_to_markdown_file(stage4_json_path, output_path=None)`

Output:

```markdown
# Mindmap Generated

- Framework: `SYNTHESIS`
- Query: overview synthesis from framework analyses

## Outline
- **Strategic Mindmap for Business Growth** (root): ...
  - **Privacy-Centric Strategies** (theme): ...
    - **Enhance Data Privacy Practices** (insight): ...
      - **Develop Comprehensive Privacy Policy** (action): ...
  - **Digital Transformation Leadership** (theme): ...
  - ...
```

---

### 4. CLI Commands Tóm Tắt

- **Overview retrieval (chọn context):**

```bash
python examples/check_query_layer_stage3.py \
  --artifact-root "out/fptsoftware-com/mindmap/mm_.../" \
  --retrieval-mode overview \
  --top-k-final 12
```

- **Multi-framework analyses (1 LLM / cluster):**

```bash
python examples/check_overview_framework_analysis.py \
  --website fptsoftware-com
```

- **Sinh mindmap từ analyses:**

```bash
python examples/check_generation_stage4.py \
  --framework-analyses "out/fptsoftware-com/mindmap/mm_.../framework_analyses_overview.json" \
  --output "out/fptsoftware-com/mindmap/mm_.../mindmap_generated.json"
```

- **Convert sang markdown:**

```bash
python examples/check_generation_stage4_to_markdown.py \
  --input "out/fptsoftware-com/mindmap/mm_.../mindmap_generated.json" \
  --output "out/fptsoftware-com/mindmap/mm_.../mindmap_generated.md"
```

Tài liệu này là spec chuẩn cho pipeline từ `clusters_top` → `topics` → `retrieval_context` → `framework_analyses_overview` → `mindmap_generated`.
