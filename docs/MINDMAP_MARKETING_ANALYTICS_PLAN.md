# Mindmap — Kế hoạch nâng cấp phân tích Marketing & Sales

Tài liệu này bổ sung [`MINDMAP.md`](MINDMAP.md), [`PIPELINE.md`](PIPELINE.md) và [`NER_ARCHITECTURE.md`](NER_ARCHITECTURE.md). Nó mô tả **lộ trình triển khai mới** (ưu tiên ROI / Quick Wins) trên nền **implementation hiện tại** của Phase 10.

---

## 1. Mục tiêu

Làm cho artifact `mindmap.json` (và sau đó OPML) mang tính **phân tích — đánh giá** theo góc nhìn **Marketing + Sales**: nhánh nào là cơ hội / rủi ro, thuộc giai đoạn funnel nào, nhánh nào cần ưu tiên xử lý (negative sentiment, chốt sale, v.v.).

**Không** thay đổi bài toán cốt lõi vector → cluster trừ khi có feedback rõ ràng (xem Giai đoạn 3).

---

## 2. Trạng thái implementation hiện tại (baseline)

Các điểm chạm code đã có, dùng làm mốc cho kế hoạch:

| Thành phần | Vai trò | Ghi chú |
|------------|---------|---------|
| `app/mindmap/clusterer.py` | HDBSCAN top-level | — |
| `app/mindmap/recursive_cluster.py` | Cây đệ quy → `clusters_tree_raw.json` | `node_id` dạng `cluster_<label>`, con là `<parent>_c<label>` |
| `app/mindmap/topics_stage.py` | **C3** — LLM đặt tên cluster | Chỉ xử lý **cluster top-level** trong `clusters_top.json` (`cluster_0`, `cluster_1`, …, `cluster_noise`) |
| `app/mindmap/topic_extractor.py` | `OpenAITopicExtractor` | JSON strict: `title`, `summary`; `response_format: json_object` |
| `app/mindmap/tree_builder.py` | **D1** — ghép tree + `topics.json` + `entities.json` | Node con **không** có entry trong `topics.json` → fallback title (`Cluster {label}` / `Noise`) và `summary` rỗng |
| `app/mindmap/ner.py` | Entity leaf | `MINDMAP_NER_PROVIDER` (mặc định `spacy`) |
| `app/config.py` | Env mindmap | `MINDMAP_MAX_LLM_CALLS_PER_RUN`, `MINDMAP_MAX_TOKENS_PER_RUN`, NER, UMAP/HDBSCAN… |

**Khoảng trống quan trọng:** Docs (`MINDMAP.md`) mô tả thêm **LLM synthesis** riêng và **OPML export**; trong code hiện tại **chưa** có `synthesizer.py` và **chưa** có bước xuất OPML. Giá trị “wow” M&S nên gắn vào **cùng một lần gọi LLM** đang dùng cho topic (mở rộng schema), thay vì chờ một module synthesis chưa tồn tại — trừ khi sau này tách riêng vì giới hạn token hoặc batching.

**Hệ quả cho funnel/SWOT:** Nếu chỉ mở rộng C3 mà **không** bổ sung topic cho node đệ quy, các field phân tích sẽ **đầy đủ ở nhánh cấp 1**, còn node sâu vẫn thiếu context LLM cho đến khi triển khai **đặt tên/tóm tắt đa tầng** (mục tùy chọn trong Giai đoạn 1b).

---

## 3. Nguyên tắc triển khai

1. **Một vòng LLM, nhiều field:** Ưu tiên mở rộng JSON trả về từ topic extraction (`swot_category`, `funnel_stage`, …) thay vì tăng số vòng gọi API.
2. **Enum rõ trong prompt:** Giảm hallucination và hỗ trợ filter/analytics (SWOT, funnel, priority).
3. **Heuristic OPML / priority:** Tách từ điển keyword (VI/EN) ra config để team chỉnh không cần deploy code.
4. **Đo chi phí:** Mọi mở rộng LLM phải cộng dồn với `MINDMAP_MAX_LLM_CALLS_PER_RUN` và `MINDMAP_MAX_TOKENS_PER_RUN`.
5. **Refactor cấu trúc cây** chỉ khi có bằng chứng từ người dùng (sau pilot).

---

## 4. Giai đoạn 1 — Quick Wins (1–2 tuần làm việc, tùy scope)

**Mục tiêu:** Tăng tính phân tích trên output JSON với ít thay đổi kiến trúc nhất.

### 4.1 Mở rộng contract LLM topic (ưu tiên ROI cao nhất)

**Việc làm:**

1. Mở rộng `TopicPayload` và `_parse_topic_json` trong `app/mindmap/topic_extractor.py` để nhận thêm (đề xuất):
   - `swot_category`: một trong `Strength` \| `Weakness` \| `Opportunity` \| `Threat` \| `Mixed` \| `N_A` (hoặc tập tương đương ngắn gọn).
   - `funnel_stage`: một trong `Awareness` \| `Consideration` \| `Decision` \| `Retention` \| `Unknown`.
   - (Tùy chọn) `ms_notes`: một câu ≤ 25 từ — góc nhìn M&S bổ sung cho `summary`.
2. Cập nhật system/user prompt: diễn giải cluster theo **nội dung website / invest**, góc nhìn **marketing & sales**, **chỉ** chọn enum đã liệt kê.
3. Cập nhật `topics_stage.py`: ghi các field mới vào mỗi entry trong `topics.json` (và `dry_run` trả placeholder hợp lệ).
4. Cập nhật `tree_builder.py`: đưa các field này vào object node trong `mindmap.json` (ví dụ `swot_category`, `funnel_stage` song song với `title`/`summary`). Cân nhắc tăng `schema_version` lên `2` khi thêm field breaking cho consumer.

**Deliverable:** `topics.json` và `mindmap.json` có metadata M&S ở **các node có topic LLM** (hiện tại là cluster top-level + noise cố định).

### 4.1b (Tùy chọn, nếu cần độ sâu cây ngay)

**Đặt tên / phân loại đa tầng:** Với mỗi node không-phải-root trong `clusters_tree_raw.json`, gọi cùng extractor (hoặc batch) để lấp đầy `topics.json` theo `node_id` đầy đủ.  

**Impact:** Tăng mạnh `MINDMAP_MAX_LLM_CALLS_PER_RUN` — cần ước lượng `≈ số node nội bộ` trước khi bật. Có thể giới hạn độ sâu hoặc chỉ topic cho `depth <= 1` trong pilot.

### 4.2 OPML & mức ưu tiên hành động (Giải pháp “metrics”)

**Việc làm:**

1. Thêm module nhỏ (ví dụ `app/mindmap/opml_export.py` hoặc `ms_node_metrics.py`) — sau khi có OPML, hoặc gắn vào bước build tree:
   - Đọc text tổng hợp: `title`, `summary`, (optional) `ms_notes`, headline entity.
   - Áp **rule-based** keyword lists (file YAML/JSON trong repo hoặc env trỏ path): nhóm “tiêu cực / khiếu nại / rủi ro”, nhóm “chốt / đăng ký / demo / pricing”, v.v.
   - Gán attribute kiểu `_actionPriority`: `High` \| `Normal` (và nên có `_actionReason` ngắn: rule id hoặc keyword matched).
2. Kết hợp với `swot_category` / `funnel_stage` nếu đã có (ví dụ `Threat` + `Consideration` → ưu tiên cao hơn rule đơn lẻ).
3. Implement **xuất OPML 2.0** (hiện chưa có trong code) — nhúng attribute trên vào `<outline>` tương thích tool đích (XMind/Freemind/Logseq).

**Deliverable:** File `mindmap.opml` + tài liệu mapping attribute.

---

## 5. Giai đoạn 2 — NER & tín hiệu M&S sâu hơn

**Mục tiêu:** Entity và khái niệm domain M&S tốt hơn, có thể offline hoặc kiểm soát chi phí.

**Thứ tự đề xuất:**

1. **Rule / gazetteer không LLM:** Danh sách thương hiệu, đối thủ, thuật ngữ funnel (tiếng Việt + Anh) — merge với kết quả spaCy.
2. **Pilot LLM-NER:** `MINDMAP_NER_PROVIDER=llm` trên **sample** nhỏ (giới hạn leaf hoặc chunk), đo token; so sánh với `MINDMAP_MAX_TOKENS_PER_RUN`.
3. **Nếu vượt ngân sách:** Thu thập nhãn → huấn luyện **spaCy** nhẹ hoặc pipeline hybrid (rule → spaCy → LLM chỉ khi cần).

Chi tiết provider và artifact: xem [`NER_ARCHITECTURE.md`](NER_ARCHITECTURE.md).

---

## 6. Giai đoạn 3 — Guided Tree / taxonomy (chỉ khi cần)

**Điều kiện kích hoạt:** Sau pilot Phase 10, feedback nghiệp vụ cho thấy cây HDBSCAN đệ quy **không khớp luồng suy nghĩ** M&S (quá ngẫu nhiên, khó trình bày stakeholder).

**Phạm vi:** Gần với **thiết kế lại luồng phân cụm / orchestrator** — gắn nhánh theo ontology (Personas, Product, Pricing, Social proof, …) hoặc **guided splitting** sau cluster. **Không** khởi động song song với Giai đoạn 1.

---

## 7. Tiêu chí hoàn thành & rủi ro

| Tiêu chí | Gợi ý đo |
|----------|----------|
| Output hữu ích cho M&S | Review nhanh với 3–5 domain cụ thể; enum có tỷ lệ `Unknown` / `N_A` thấp hợp lý |
| Chi phí | Theo dõi tổng token/run; không vượt ngưỡng đã cấu hình |
| Priority OPML | Không “High” quá 50% nhánh — nếu có thì tinh chỉnh từ điển |
| Rủi ro | LLM lệch domain → siết prompt + enum; keyword trùng nghĩa → phân tầng rule + locale |

---

## 8. Mapping nhanh: file / setting cần đụng tới

| Thay đổi | File / cấu hình |
|----------|------------------|
| Schema topic + prompt | `app/mindmap/topic_extractor.py` |
| Ghi `topics.json` | `app/mindmap/topics_stage.py` |
| Node `mindmap.json` | `app/mindmap/tree_builder.py` |
| Giới hạn chi phí | `app/config.py`, `.env` — `MINDMAP_MAX_*`, `MINDMAP_LLM_MODEL` |
| NER | `app/mindmap/ner.py`, `MINDMAP_NER_*` |
| OPML + priority | Module mới + (sau nài) wire vào pipeline xuất artifact |
| Tài liệu contract | [`MINDMAP.md`](MINDMAP.md) §4 (cập nhật khi schema_version đổi) |

---

## 9. Phiên bản tài liệu

| Phiên bản | Ngày | Ghi chú |
|-----------|------|---------|
| 1.0 | 2026-05-04 | Bản kế hoạch đầu tiên trên implementation Phase 10 hiện tại |
