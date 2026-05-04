# NER trong Mindmap (D1) - Kiến trúc, vận hành, và ước lượng LLM calls

Tài liệu này tổng hợp trạng thái hiện tại của dự án và cách triển khai NER theo kế hoạch Sprint D1 (`10.5 + 10.6`).

## 1) Trạng thái hiện tại trong code

- Hiện tại repo **chưa có** `app/mindmap/ner.py`.
- NER mới ở mức thiết kế trong `docs/MINDMAP.md` và `docs/IMPLEMENTATION_PLAN.md`.
- Flow đã có:
  - C2/C4: cluster (`clusters_top.json`, `clusters_tree_raw.json`)
  - C3: topic extraction (`topics.json`) bằng OpenAI Chat
- Vì chưa có stage NER, nên **số call LLM cho NER hiện tại = 0**.

## 2) NER dự kiến trong D1 làm như nào

Theo tài liệu thiết kế:

- Provider mặc định: `spacy` (`MINDMAP_NER_PROVIDER=spacy`), model `xx_ent_wiki_sm`
- Provider tùy chọn: `llm`
- Chỉ chạy NER cho **leaf nodes**
- Aggregate entity theo cặp `(text, label)` và lấy top-K
- Ghi ra `entities.json`
- Khi provider spaCy lỗi hoặc model thiếu: fail gracefully, `entities=[]`, không crash pipeline

## 3) Kiến trúc đề xuất (vẽ theo flow hiện có + D1)

```mermaid
flowchart TD
    A[rag_chunks + vectors] --> B[cluster_top / recursive_cluster]
    B --> C[clusters_tree_raw.json]
    A --> D[topics_stage + topic_extractor]
    D --> E[topics.json]

    C --> F[tree_builder (D1)]
    E --> F
    A --> G[ner_stage (D1)]
    G --> H[entities.json]
    H --> F

    F --> I[mindmap.json]
```

## 4) LLM call accounting (quan trọng để tính chi phí)

### 4.1 Hiện tại (đã chạy)

- Topic extraction C3:
  - `1 call / top-level cluster`
  - Có guardrail `MINDMAP_MAX_LLM_CALLS_PER_RUN`
- Với artifact hiện tại:
  - `top_cluster_count = 6` => ước lượng call C3 khoảng **6**

### 4.2 Sau khi làm D1 với NER mặc định `spacy`

- NER dùng local model, không gọi API.
- **LLM calls do NER = 0**.

### 4.3 Nếu bật NER provider `llm` (optional)

Ký hiệu:

- `L`: số leaf nodes trong cây
- `R_ner`: số lần retry parse/prompt lại cho mỗi leaf (0 hoặc 1, theo thiết kế strict JSON)

Ước lượng:

- `LLM_calls_ner ~= L * (1 + R_ner)`
- Tổng call toàn pipeline tại D1 (chưa synthesis):
  - `LLM_calls_total ~= calls_topic + L * (1 + R_ner)`

Với run mẫu hiện tại:

- `tree_leaf_count = 9` (từ `clusters_tree_raw.json`)
- `calls_topic ~ 6`

=> Nếu `NER=spacy`:  
`LLM_calls_total ~ 6`

=> Nếu `NER=llm` và không retry:  
`LLM_calls_total ~ 6 + 9 = 15`

=> Nếu `NER=llm` và retry xấu nhất 1 lần/leaf:  
`LLM_calls_total ~ 6 + 9*2 = 24`

## 5) Output artifacts liên quan D1

- `entities.json` (mới ở D1):
  - dạng map `leaf_node_id -> [entities...]`
- `mindmap.json` (mới ở D1):
  - tree hợp nhất từ cluster + topic + entities
  - `chunk_ids` roll-up từ leaf lên root
  - validate root coverage = input vectors

## 6) Khuyến nghị vận hành để tiết kiệm chi phí

- Mặc định giữ `MINDMAP_NER_PROVIDER=spacy` cho D1 để:
  - ổn định
  - không tăng API cost
  - không tăng latency do network
- Chỉ bật `NER=llm` cho domain có entity khó hoặc cần chất lượng cao theo ngành.
- Nếu bật `NER=llm`, nên thêm giới hạn:
  - `MINDMAP_MAX_LLM_CALLS_PER_RUN`
  - batching theo leaf và fallback về spaCy khi quota gần chạm trần.
