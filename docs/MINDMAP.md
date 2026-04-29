# Phase 10 – MindMap Builder (Vector → Tree → OPML)

Tài liệu này đặc tả **Phase 10**: dựng mindmap cho 1 lần invest dựa trên vector embedding đã upsert ở Phase 9.

> Đọc trước [`ARCHITECTURE.md`](ARCHITECTURE.md) và [`PIPELINE.md`](PIPELINE.md) (Phase 9) để hiểu bối cảnh ingest + vector store.

---

## 1. Mục tiêu

Sau khi Phase 9 đã sinh ra:

- `out/<slug>/chunks.jsonl` (text + metadata)
- `out/<slug>/embeddings.jsonl` (`chunk_id` + vector 1536-dim)
- Bảng `rag_chunks` trong pgvector (`chunk_id`, `notebooklm_id`, `chunk_text`, `source_url`, `embedding`, `metadata`)

Phase 10 phải:

1. Lấy toàn bộ vectors của **1 invest run** từ pgvector (hoặc embeddings.jsonl).
2. Cluster bằng **HDBSCAN** để gom chunk theo chủ đề.
3. Đặt tên chủ đề cho mỗi cluster bằng **LLM** dựa trên chunk đại diện.
4. **Recursive clustering** để tìm sub-branch trong từng cluster lớn.
5. **NER** cho leaf để bổ sung entity (PERSON/ORG/PRODUCT/LOCATION/DATE...).
6. Build **JSON tree** với `citation = chunk_ids`.
7. **LLM synthesis** viết mô tả ngắn cho mỗi node.
8. Export **OPML 2.0** để render trên các tool mindmap (XMind/Freemind/Logseq...).

---

## 2. End-to-end flow

```mermaid
flowchart TB
    A["pgvector: rag_chunks<br/>(scope theo run_id / website)"] --> B[Vector Loader]
    B --> C[UMAP dim-reduction<br/>1536 → 8]
    C --> D[HDBSCAN top-level]
    D --> E[Group chunk_id by cluster]
    E --> F[Topic Extraction<br/>LLM đặt tên branch]
    F --> G{cluster_size ≥ MIN_RECURSE?}
    G -->|yes| H[Recursive HDBSCAN<br/>depth ≤ MAX_DEPTH]
    G -->|no| I[Mark as leaf]
    H --> F
    I --> J[NER for leaves]
    J --> K[Build JSON tree<br/>citation = chunk_ids]
    K --> L[LLM synthesis<br/>(node descriptions)]
    L --> M["Artifacts:<br/>mindmap.json, mindmap.opml"]
    M --> N["DB: mindmap_runs"]
```

Thứ tự rút gọn theo yêu cầu:

```
vector + chunk_id
    → Vector DB (index)
    → HDBSCAN (cluster toàn bộ)
    → Gom chunk_id theo cluster
    → Topic extraction (LLM đặt tên branch)
    → Recursive clustering (tìm sub-branch)
    → NER (tìm leaf)
    → JSON tree (với citation = chunk_ids)
    → LLM synthesis (viết mô tả)
    → OPML → render
```

---

## 3. Scope của 1 lần build mindmap

Một **mindmap build** gắn với:

- `run_id` của Phase 9 (hoặc `website_slug` để gộp nhiều run gần nhất), **bắt buộc xác định scope**.
- Snapshot vectors tại thời điểm build → kết quả cluster reproducible.
- Output là 1 `mindmap_run_id` riêng (không trùng `ingest_run_id`).

Quy tắc chọn vectors:

| Mode                   | Lấy gì từ pgvector                                                                |
| ---------------------- | --------------------------------------------------------------------------------- |
| `by_run_id`            | Tất cả `chunk_id` có `metadata->>'run_id' = :run_id` trong cùng `notebooklm_id`   |
| `by_website` (default) | Tất cả `chunk_id` còn `is_active=true` theo `notebooklm_id` và host `website`      |
| `by_chunk_ids`         | Tập `chunk_id` truyền vào, luôn filter theo `notebooklm_id`                        |

> Mặc định Phase 10 dùng `by_website` để mindmap luôn phản ánh state mới nhất của domain trong đúng notebook.

Quy ước scope bắt buộc:

- Mọi ingest run phải gắn `notebooklm_id`.
- Mọi query build mindmap phải có `notebooklm_id` (trực tiếp hoặc suy ra từ `run_id`).
- Query mặc định: `WHERE notebooklm_id = :notebooklm_id AND is_active = true`.

---

## 4. Data contracts

### 4.1 Tree node schema

```jsonc
{
  "id": "n_0",                          // ID nội bộ trong tree
  "depth": 0,                           // 0 = root, 1 = top-level branch...
  "title": "FPT Software – Services",   // Topic name (LLM)
  "summary": "1-2 câu tóm tắt nhánh.",  // LLM synthesis
  "size": 84,                           // số chunk trong nhánh (tính cộng dồn con)
  "chunk_ids": ["e2bb82db790e", ...],   // citation: chunk_id thuộc node này
  "representative_chunk_ids": [...],    // top-K chunk gần centroid (dùng cho Topic / Synthesis)
  "entities": [                         // chỉ leaf mới có
    {"text": "FPT Software", "label": "ORG", "score": 0.92}
  ],
  "children": [/* TreeNode[] */]
}
```

Quy ước:

- `chunk_ids` ở **leaf** = các chunk thực sự thuộc cluster đó.
- `chunk_ids` ở **non-leaf** = union của children (rolled up).
- `representative_chunk_ids` luôn từ **chính cluster đó** (không lấy từ con) để LLM thấy đúng vùng nội dung của node.
- `id` ổn định trong 1 build, không cần ổn định giữa các build.

### 4.2 Artifact files

Tất cả ghi dưới `out/<slug>/mindmap/<mindmap_run_id>/`:

| File                                    | Nội dung                                                              |
| --------------------------------------- | --------------------------------------------------------------------- |
| `vectors_snapshot.jsonl`                | `chunk_id`, `vector_checksum`, `source_url`, `text_preview` (debug)   |
| `clusters_top.json`                     | Output HDBSCAN top-level: `{cluster_label: [chunk_ids]}` + noise list |
| `clusters_tree_raw.json`                | Cây cluster sau recursive (chưa có topic name / synthesis)            |
| `topics.json`                           | `{node_id: {title, summary, representative_chunk_ids, llm_meta}}`     |
| `entities.json`                         | `{leaf_node_id: [Entity]}`                                            |
| `mindmap.json`                          | Tree node schema 4.1 (artifact chính)                                 |
| `mindmap.opml`                          | OPML 2.0 (render được)                                                |
| `manifest.json`                         | `mindmap_run_id`, `pipeline_version`, params, stats                   |
| `stats.json`                            | counts + duration mỗi stage                                           |

### 4.3 DB schema (Alembic migration mới)

Bảng `mindmap_runs`:

```sql
CREATE TABLE mindmap_runs (
    mindmap_run_id   TEXT PRIMARY KEY,
    ingest_run_id    TEXT REFERENCES ingest_runs(run_id),
    notebooklm_id    TEXT NOT NULL,
    website          TEXT,
    scope_mode       TEXT NOT NULL,          -- 'by_run_id' | 'by_website' | 'by_chunk_ids'
    status           TEXT NOT NULL DEFAULT 'queued',
    chunk_count      INTEGER NOT NULL DEFAULT 0,
    cluster_count    INTEGER NOT NULL DEFAULT 0,
    leaf_count       INTEGER NOT NULL DEFAULT 0,
    max_depth        INTEGER NOT NULL DEFAULT 0,
    params           JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message    TEXT,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at      TIMESTAMPTZ
);
CREATE INDEX ix_mindmap_runs_website ON mindmap_runs(website);
CREATE INDEX ix_mindmap_runs_notebook_started ON mindmap_runs(notebooklm_id, started_at DESC);
```

> Không lưu cluster assignment xuống DB ở phase này (giữ nó dạng artifact để dễ regenerate). Có thể thêm bảng `mindmap_nodes` ở phase sau khi cần search/filter.

---

## 5. Thuật toán & tham số

### 5.1 Vector loading

Truy vấn pgvector:

```sql
SELECT chunk_id, notebooklm_id, source_url, chunk_text, metadata, embedding
FROM rag_chunks
WHERE notebooklm_id = :notebooklm_id
  AND is_active = true
  AND source_url ILIKE :host_pattern
  AND ($run_id IS NULL OR metadata->>'run_id' = :run_id);
```

Convert `pgvector.Vector` → `numpy.ndarray (N, 1536)`. Dùng trực tiếp `chunk_text` trong `rag_chunks` cho topic extraction & NER (không phụ thuộc `chunks.jsonl`).

### 5.2 Dim reduction (UMAP)

Vì `text-embedding-3-small` là 1536-dim, HDBSCAN trực tiếp sẽ kém ổn định. Bắt buộc reduce:

| Param           | Default | Lý do                                               |
| --------------- | ------- | --------------------------------------------------- |
| `n_neighbors`   | 15      | Cân bằng local/global structure                     |
| `n_components`  | 8       | Đủ phân biệt nhánh, tránh curse-of-dimensionality   |
| `metric`        | cosine  | Khớp với metric semantic của OpenAI embedding       |
| `min_dist`      | 0.0     | Cluster sát nhau hơn → HDBSCAN tách tốt             |
| `random_state`  | 42      | Reproducible                                        |

> Nếu `N < 20`: skip UMAP, chạy HDBSCAN trực tiếp trên cosine distance matrix.

### 5.3 HDBSCAN top-level

| Param                     | Default | Ghi chú                                                       |
| ------------------------- | ------- | ------------------------------------------------------------- |
| `min_cluster_size`        | 5       | Cluster nhỏ hơn 5 chunk thì coi là noise                      |
| `min_samples`             | 2       | Robustness vs noise                                           |
| `metric`                  | euclidean (sau UMAP) | UMAP đã encode khoảng cách             |
| `cluster_selection_method`| eom     | Excess of mass cho cluster ổn định                            |
| `cluster_selection_epsilon`| 0.0    | Để mặc định, tinh chỉnh sau khi đo                            |

Output:

- `labels[i] = -1` → noise (đẩy vào nhánh đặc biệt **"Misc / Unclustered"**).
- `labels[i] >= 0` → cluster id.

### 5.4 Đại diện cluster

Cho mỗi cluster `c`:

1. Tính centroid `μ_c = mean(vectors trong c)`.
2. Sort chunk theo `cosine_similarity(vector, μ_c)` giảm dần.
3. Lấy top-K (`TOPIC_REPR_K=5`) làm `representative_chunk_ids`.

> Nếu `len(cluster) < K`, lấy hết.

### 5.5 Topic extraction (LLM)

**Prompt mẫu** (system + user):

```
SYSTEM: You name topical clusters extracted from a company website.
Return strict JSON: {"title": str, "summary": str}.
- title: 3–7 words, English or Vietnamese matching the chunks.
- summary: 1 sentence, ≤ 30 words, describe what unifies these chunks.
- No emojis, no prefixes like "Topic:" or "Summary:".

USER:
Below are {K} representative excerpts from a cluster. Propose a topic.

[1] {repr_chunks[0].text[:600]}
[2] {repr_chunks[1].text[:600]}
...
```

Provider mặc định: **OpenAI**, model `gpt-4o-mini` (cost-first). Có thể override qua env `MINDMAP_LLM_MODEL`.

Tham số:

| Param                       | Default | Mô tả                                                |
| --------------------------- | ------- | ---------------------------------------------------- |
| `MINDMAP_LLM_MODEL`         | gpt-4o-mini | Model cho topic + synthesis                       |
| `MINDMAP_LLM_TEMPERATURE`   | 0.2     | Tránh hallucinate, vẫn đa dạng tên                   |
| `MINDMAP_TOPIC_REPR_K`      | 5       | Số chunk đại diện gửi cho LLM                        |
| `MINDMAP_TOPIC_TEXT_LIMIT`  | 600     | Số ký tự tối đa mỗi excerpt                          |

### 5.6 Recursive sub-clustering

Pseudo-code:

```python
def build_subtree(cluster_chunks, depth):
    if depth >= MAX_DEPTH:                     return leaf(cluster_chunks)
    if len(cluster_chunks) < MIN_RECURSE_SIZE: return leaf(cluster_chunks)
    sub_vectors = vectors[cluster_chunks]
    sub_reduced = umap_local(sub_vectors)      # n_neighbors nhỏ hơn
    sub_labels  = hdbscan_local(sub_reduced)   # min_cluster_size nhỏ hơn
    if num_real_clusters(sub_labels) < 2:      return leaf(cluster_chunks)
    return [build_subtree(child_chunks, depth + 1)
            for child_chunks in group_by(sub_labels)]
```

Defaults:

| Param                          | Default | Ghi chú                                  |
| ------------------------------ | ------- | ---------------------------------------- |
| `MINDMAP_MAX_DEPTH`            | 3       | Đủ để render mindmap dễ đọc              |
| `MINDMAP_MIN_RECURSE_SIZE`     | 12      | Cluster < 12 chunk → leaf                |
| `MINDMAP_SUB_MIN_CLUSTER_SIZE` | 3       | HDBSCAN min_cluster_size cho sub-level   |
| `MINDMAP_SUB_N_NEIGHBORS`      | 8       | UMAP n_neighbors cho sub-level           |

### 5.7 NER for leaves

Lựa chọn:

| Provider          | Khi nào dùng                                              |
| ----------------- | --------------------------------------------------------- |
| `spacy`           | Default, offline, đa ngôn ngữ (`xx_ent_wiki_sm`)          |
| `llm`             | Khi muốn entity chuẩn hơn cho domain (đắt hơn)            |

Pseudo-code spaCy:

```python
nlp = spacy.load("xx_ent_wiki_sm")
def ner_for_leaf(leaf_chunks):
    text = "\n\n".join(c.text for c in leaf_chunks[:NER_MAX_CHUNKS])
    doc  = nlp(text[:NER_TEXT_LIMIT])
    counter = Counter((ent.text.strip(), ent.label_) for ent in doc.ents)
    return [{"text": t, "label": l, "count": n}
            for (t, l), n in counter.most_common(NER_TOP_K)]
```

Defaults:

| Param                  | Default              |
| ---------------------- | -------------------- |
| `MINDMAP_NER_PROVIDER` | spacy                |
| `MINDMAP_NER_MODEL`    | xx_ent_wiki_sm       |
| `MINDMAP_NER_TOP_K`    | 8                    |
| `MINDMAP_NER_MAX_CHUNKS` | 20                 |
| `MINDMAP_NER_TEXT_LIMIT` | 8000               |

> Nếu spaCy model chưa cài, service phải fail gracefully và chỉ ghi `entities=[]` cho leaf đó (không crash cả pipeline).

### 5.8 LLM synthesis

Sau khi tree đã có topic name + entities, mỗi node được sinh **mô tả dài hơn** (1–2 câu):

- **Leaf node**: dùng top-3 chunk đại diện + entities → 1 câu tổng hợp.
- **Non-leaf node**: dùng titles + summaries của children → 1–2 câu mô tả nhánh.
- **Root**: dùng titles của top-level branches → 2–3 câu giới thiệu domain.

Lưu ý:

- Synthesis **không thay** `summary` của topic extraction; nó ghi đè/ enrich tuỳ flag `MINDMAP_SYNTH_OVERWRITE` (default `false` → ghi vào field `description`).
- Toàn bộ synthesis chạy **batched** để giảm cost; có thể skip bằng `MINDMAP_SKIP_SYNTHESIS=true`.

### 5.9 OPML export

OPML 2.0 schema:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head>
    <title>{slug} – mindmap</title>
    <dateCreated>{iso}</dateCreated>
  </head>
  <body>
    <outline text="{root.title}" _note="{root.summary}">
      <outline text="{branch.title}" _note="{branch.summary}">
        <outline text="{leaf.title}" _note="{leaf.summary}"
                 _chunkIds="id1,id2,id3"/>
      </outline>
    </outline>
  </body>
</opml>
```

- `_note` chứa `summary` (nhiều mindmap viewer hiển thị note khi hover).
- `_chunkIds` là attribute custom để link ngược về citation.
- File ghi UTF-8, escape đầy đủ `<`, `>`, `&`, `"`.

---

## 6. Module layout

```
app/
├── mindmap/
│   ├── __init__.py
│   ├── service.py              # orchestrator (build_mindmap)
│   ├── vector_loader.py        # load vectors + chunk text
│   ├── reducer.py              # UMAP wrapper
│   ├── clusterer.py            # HDBSCAN top + recursive
│   ├── representative.py       # chọn chunk đại diện theo centroid
│   ├── topic_extractor.py      # LLM topic naming
│   ├── ner.py                  # spaCy / LLM NER
│   ├── tree_builder.py         # ráp JSON tree + roll-up chunk_ids
│   ├── synthesizer.py          # LLM synthesis (descriptions)
│   ├── opml_exporter.py        # OPML 2.0 writer
│   └── repository.py           # CRUD mindmap_runs
└── main.py                     # thêm route /mindmap/*
```

`examples/`:

- `examples/check_phase10_c1.py` … `check_phase10_c6.py` (smoke từng bước).

---

## 7. API contract

### 7.1 `POST /mindmap/build`

Body:

```jsonc
{
  "notebooklm_id": "nb_fpt_001",       // bắt buộc
  "scope_mode": "by_website",         // by_website | by_run_id | by_chunk_ids
  "website":   "fptsoftware.com",     // bắt buộc nếu scope_mode != by_chunk_ids
  "run_id":    null,                  // bắt buộc nếu scope_mode == by_run_id
  "chunk_ids": [],                    // bắt buộc nếu scope_mode == by_chunk_ids
  "params":    {                      // override defaults (optional)
    "max_depth": 3,
    "min_cluster_size": 5,
    "skip_synthesis": false,
    "skip_ner": false
  },
  "dry_run": false
}
```

Response:

```jsonc
{
  "mindmap_run_id": "20260428T123045Z_a1b2c3d4",
  "status_url": "/mindmap/20260428T123045Z_a1b2c3d4"
}
```

`dry_run=true` → không gọi LLM, chỉ trả estimate (`vector_count`, `est_clusters`, `est_llm_calls`, `est_cost_usd`).

Validation rules:

- Thiếu `notebooklm_id` -> `validation_error`.
- `run_id` không thuộc `notebooklm_id` -> `validation_error`.
- `chunk_ids` có phần tử ngoài notebook -> bỏ qua hoặc reject (khuyến nghị reject để rõ ràng).

### 7.2 `GET /mindmap/{mindmap_run_id}`

Trả `mindmap_runs` row + `result` (artifact paths) khi `status=success`.

### 7.3 `GET /mindmap/{mindmap_run_id}/tree`

Trả nội dung `mindmap.json` (JSON tree).

### 7.4 `GET /mindmap/{mindmap_run_id}/opml`

Trả file `mindmap.opml` (`Content-Type: text/x-opml`).

### 7.5 Error contracts (mở rộng từ Phase 9)

- `validation_error`
- `not_found_vectors` (scope rỗng)
- `quota_exceeded` (LLM token budget)
- `clustering_failed` (HDBSCAN không tìm được cluster nào sau noise)
- `upstream_error`

---

## 8. Guardrails & cost

| Guardrail                        | Default      | Lý do                              |
| -------------------------------- | ------------ | ---------------------------------- |
| `MINDMAP_MAX_VECTORS_PER_RUN`    | 10000        | Tránh build mindmap quá lớn        |
| `MINDMAP_MAX_LLM_CALLS_PER_RUN`  | 200          | Topic + synthesis cộng dồn         |
| `MINDMAP_MAX_TOKENS_PER_RUN`     | 200000       | Budget LLM cho 1 build             |
| `MINDMAP_DRY_RUN_REQUIRED_GTE`   | 1000 vectors | Bắt buộc dry-run trước nếu vượt    |

Cost summary trả về trong response giống Phase 9:

```jsonc
{
  "cost_summary": {
    "topic_calls": 14,
    "synthesis_calls": 18,
    "estimated_tokens": 42000,
    "estimated_cost_usd": 0.0084
  }
}
```

---

## 9. Observability

- Log structured theo `mindmap_run_id`, key fields: `stage`, `cluster_count`, `noise_ratio`, `mean_cluster_size`, `duration_seconds`.
- Stage durations track:
  - `load_vectors`
  - `reduce_dim`
  - `cluster_top`
  - `topic_extract`
  - `recurse_cluster`
  - `ner_leaves`
  - `synthesize`
  - `export_opml`
- Cảnh báo khi:
  - `noise_ratio > 0.5`
  - `cluster_count > MAX_CLUSTERS_WARN` (default 50)
  - `mean_cluster_size < 3`

---

## 10. Quality checklist

Trước khi đánh dấu Phase 10 done:

- [ ] Build thành công cho `fptsoftware-com` (artifact đã có ở Phase 9).
- [ ] `mindmap.json` mở được, depth ≤ 3, không có cluster rỗng.
- [ ] `mindmap.opml` import được vào XMind hoặc Logseq.
- [ ] Mỗi leaf có ≥ 1 chunk_id citation hợp lệ trong `rag_chunks`.
- [ ] Re-run cùng input cho ra kết quả gần như nhau (UMAP `random_state=42`).
- [ ] Dry-run trả estimate hợp lý, không gọi LLM thật.
- [ ] Guardrail `MINDMAP_MAX_VECTORS_PER_RUN` chặn được run quá lớn.
- [ ] Failure path (LLM lỗi) không làm mất artifact đã sinh trước đó.

---

## 11. Open questions / sẽ chốt khi build

1. ~~**Multi-run merge**~~: đã chốt policy theo `notebooklm_id` + `is_active=true`; `by_run_id` chỉ dùng audit/repro.
2. **Re-cluster vs re-rank**: lần build sau, có nên giữ nguyên `node_id` cho branch tương ứng để diff được? → để Phase 10.1.
3. **Multilingual NER**: `xx_ent_wiki_sm` có thể yếu cho domain công nghệ Việt → cân nhắc bổ sung LLM-NER chỉ cho leaf có tiếng Việt.
4. **Persistence cho tree**: có cần bảng `mindmap_nodes` để hỗ trợ search node trong DB không, hay artifact JSON là đủ?

---

## 12. Migration plan ngắn (notebook + chunk_text)

1. **Schema compatible trước**
   - Add nullable columns:
     - `ingest_runs.notebooklm_id`
     - `chunk_index.notebooklm_id`
     - `rag_chunks.notebooklm_id`
     - `rag_chunks.chunk_text`
   - Add indexes:
     - `rag_chunks(notebooklm_id, is_active)`
     - `rag_chunks(notebooklm_id, source_url)`
     - `chunk_index(notebooklm_id, is_active)`
     - `ingest_runs(notebooklm_id, started_at desc)`
2. **Dual-write**
   - `/ingest` bắt đầu nhận `notebooklm_id`.
   - Khi upsert vector: ghi `notebooklm_id` + `chunk_text` vào `rag_chunks`.
3. **Backfill**
   - Gán dữ liệu cũ về notebook mặc định (vd. `default`).
   - Backfill 3 bảng đến khi `notebooklm_id IS NULL = 0`.
4. **Enforce**
   - Chuyển `notebooklm_id` sang `NOT NULL`.
   - Query strict theo notebook.
