# Implementation Plan – Từng bước nhỏ để chạy được dự án

Mục tiêu: triển khai từ tài liệu hiện có thành project Python chạy được end-to-end:

1. Nhận input `company`/`website`  
2. Search seed URLs bằng Perplexity Search API  
3. Discover + scrape bằng FireCrawl  
4. Clean markdown theo pipeline hiện tại  
5. Chunk + enrich metadata  
6. Xuất `chunks.jsonl` và thống kê

---

## Nguyên tắc triển khai

- Mỗi bước nhỏ đều có **output kiểm chứng được**.
- Chỉ chuyển bước tiếp theo khi bước hiện tại chạy ổn.
- Ưu tiên code đơn giản, dễ debug, đúng theo docs trước rồi tối ưu sau.
- Mọi biến cấu hình đi qua `.env`.

---

## Phase 0 – Khởi tạo khung dự án

### Bước 0.1: Chốt cấu trúc thư mục

- Tạo khung:
  - `app/config.py`
  - `app/models.py`
  - `app/pipeline.py`
  - `app/search/perplexity_search.py`
  - `app/discover/firecrawl_map.py`
  - `app/crawl/firecrawl_scrape.py`
  - `app/clean/markdown_cleaner.py`
  - `app/chunk/rule_based_chunker.py`
  - `examples/run_demo.py`

### Bước 0.2: Chốt dependency

- Tạo `requirements.txt` tối thiểu:
  - `pydantic`
  - `python-dotenv`
  - `perplexityai`
  - `firecrawl-py`
  - `httpx`
  - `tenacity` (retry)

### Bước 0.3: Chốt config runtime

- Đồng bộ `.env.example` với 2 key:
  - `PERPLEXITY_API_KEY`
  - `FIRECRAWL_API_KEY`
- Add cấu hình pipeline:
  - `FIRECRAWL_MAP_LIMIT`
  - `FIRECRAWL_SCRAPE_CONCURRENCY`
  - `OUTPUT_DIR`
  - `HTTP_TIMEOUT`

**Tiêu chí xong phase 0:** import được toàn bộ module, không lỗi cấu trúc.

---

## Phase 1 – Config + Data Models

### Bước 1.1: Implement `app/config.py`

- Load env bằng `python-dotenv`.
- Expose object `Settings` (Pydantic Settings hoặc dataclass).
- Validate biến bắt buộc (`PERPLEXITY_API_KEY`, `FIRECRAWL_API_KEY`).

### Bước 1.2: Implement `app/models.py`

- Tạo model:
  - `SeedURL`
  - `DiscoveredURL`
  - `RawPage`
  - `CleanedPage`
  - `Chunk`
  - `PipelineResult`

**Tiêu chí xong phase 1:** chạy script nhỏ print `Settings` + instantiate từng model thành công.

---

## Phase 2 – Stage 1 (Perplexity Search API)

### Bước 2.1: Client + hàm search

- Tạo `Perplexity` client trong `app/search/perplexity_search.py`.
- Implement `search_seed_urls(company, website, max_results=20)`.
- Parse `res.results` -> list URL strings.

### Bước 2.2: Normalize + validate seed URLs

- Implement `normalize_url()`.
- Merge URL từ search + website input + manual seeds.
- Dedupe theo `scheme + host + path`.

### Bước 2.3: Verify URL sống/chết

- HEAD/GET nhẹ bằng `httpx`.
- Retry timeout/5xx (tenacity).
- Trả `list[SeedURL]` có `source`.

**Tiêu chí xong phase 2:** chạy unit script và in được >= vài seed URL hợp lệ cho 1 công ty thật.

---

## Phase 3 – Stage 2 (FireCrawl Map)

### Bước 3.1: Implement map call

- `app/discover/firecrawl_map.py`
- Gọi FireCrawl v2 `client.map(...)` với:
  - `url`
  - `search` (URL gốc chuẩn hoá)
  - `limit`
  - `include_subdomains`

### Bước 3.2: Filter URL

- Blacklist path rác (`/tag`, `/category`, file media...).
- Optional priority path (`/about`, `/services`, `/contact`...).
- Convert sang `list[DiscoveredURL]`.

**Tiêu chí xong phase 3:** từ 1 website trả được danh sách URL sạch, không quá noisy.

---

## Phase 4 – Stage 3 (FireCrawl Scrape)

### Bước 4.1: Implement scrape one URL

- `app/crawl/firecrawl_scrape.py`
- `scrape_url(url)` trả `RawPage`.
- Lấy markdown + metadata title/language/status.

### Bước 4.2: Implement scrape many URLs

- Chạy song song có semaphore theo `FIRECRAWL_SCRAPE_CONCURRENCY`.
- Skip lỗi từng URL, không fail cả batch.
- Trả list `RawPage`.

**Tiêu chí xong phase 4:** scrape thành công ít nhất 5-10 URL trong domain thật.

---

## Phase 5 – Stage 4 (Cleaner)

### Bước 5.1: Port code cleaner vào module

- Đưa nguyên logic:
  - `strip_markdown`
  - `filter_blocks`
  - `dedup_blocks`

### Bước 5.2: Adapter từ `RawPage` -> `CleanedPage`

- Implement `clean_page_markdown(raw_page) -> CleanedPage`.
- Tính `word_count`.

### Bước 5.3: Quality guard

- Nếu text quá ngắn thì gắn cờ/skip theo rule.
- Log số block trước/sau clean.

**Tiêu chí xong phase 5:** output text rõ ràng, không còn menu/footer rõ rệt.

---

## Phase 6 – Stage 5 (Rule-based Chunking + Enrich)

### Bước 6.1: Port chunking logic

- Đưa logic:
  - heading heuristic
  - sentence split
  - `CHUNK_MAX_WORDS`
  - `CHUNK_MIN_WORDS`
  - `OVERLAP_SENTENCES` (env: `CHUNK_OVERLAP_SENTENCES`)

### Bước 6.2: Enrich metadata

- Implement `enrich_chunks(...)` theo schema hiện tại:
  - `chunk_id`, `source_url`, `page_title`, `section_heading`
  - `text`, `word_count`, `crawled_at`, `chunk_index`

**Tiêu chí xong phase 6:** sinh `list[Chunk]` ổn định, metadata đầy đủ.

---

## Phase 7 – Orchestrator + CLI demo

### Bước 7.1: Implement `run_pipeline`

- Nối 5 stage theo flow docs.
- Trả `PipelineResult`.

### Bước 7.2: Ghi artifact ra thư mục output

- `out/<company-slug>/seeds.json`
- `out/<company-slug>/discovered.json`
- `out/<company-slug>/raw/*.json`
- `out/<company-slug>/cleaned/*.json`
- `out/<company-slug>/chunks.jsonl`
- `out/<company-slug>/stats.json`

### Bước 7.3: Demo command

- `python examples/run_demo.py --company "..." --website "..." --limit 10`

**Tiêu chí xong phase 7:** chạy 1 lệnh ra đủ artifacts, không crash.

---

## Phase 8 – Test tối thiểu trước khi dùng thật

### Bước 8.1: Unit test

- Test `normalize_url`.
- Test `strip_markdown/filter_blocks/dedup_blocks`.
- Test chunking boundary cases.

### Bước 8.2: Integration test nhẹ

- 1 domain thật, limit nhỏ (5-10 URL).
- Kiểm tra output có chunk, không rỗng, schema đúng.

### Bước 8.3: Regression dataset nhỏ

- Tạo 2-3 markdown mẫu "xấu".
- So sánh output cleaner/chunker với golden files.

**Tiêu chí xong phase 8:** tự tin chạy lặp lại nhiều domain mà không vỡ pipeline.

---

## Phase 9 – Productionization cho RAG

### Checklist tổng (theo luồng triển khai)

- Setup hạ tầng DB/Redis cho ingest jobs, cache, và vector index.
- Incremental foundation: `normalized_url`, `content_hash`, snapshot index.
- Selective processing: chỉ re-chunk/re-embed cho `new + changed`.
- Embedding + vector upsert idempotent theo `chunk_id`.
- Ingest API: tạo job, theo dõi trạng thái, hỗ trợ `dry_run`.
- Observability + guardrails: logs, metrics, cost/token limits.
- QA + rollout: unit/integration test + runbook vận hành.

### Bước 9.0: Setup hạ tầng (Database + Redis + Vector DB)

- Chốt stack: `PostgreSQL 16` + `pgvector` (metadata/jobs/vectors) + `Redis 7.x` (queue/cache).
- Viết `docker-compose` cho local dev: postgres, redis, qdrant (tuỳ chọn).
- Thêm biến `.env`:
  - `DATABASE_URL`
  - `REDIS_URL`
  - `VECTOR_DB_URL` (Postgres/pgvector)
  - `VECTOR_TABLE`
- Tạo schema metadata:
  - `ingest_runs`
  - `page_index` (`normalized_url`, `content_hash`, `last_run_id`)
  - `chunk_index` (`chunk_id`, `source_url`, `run_id`, `is_active`)
- Healthcheck kết nối DB/Redis/Vector DB trước khi chạy pipeline.
- Thiết lập migration tool (`Alembic`) với 1 baseline migration duy nhất tạo đủ schema nền:
  - `ingest_runs`
  - `page_index`
  - `chunk_index`
  - `rag_chunks`

### Bước 9.1: Incremental ingest (delta)

- Thêm `content_hash` cho `CleanedPage`/metadata index.
- Thiết kế `previous_index` (`url`, `content_hash`, `updated_at`, `chunk_ids`).
- So sánh với run trước để sinh `delta.json` (`new/changed/unchanged/removed`).
- Chỉ xử lý lại URL thay đổi.
- Ghi `manifest.json` có `run_id`, `pipeline_version`, artifact paths.

### Bước 9.2: Embedding + vector upsert

- Tạo `chunks_delta.jsonl`.
- Chốt embedding provider/model: OpenAI `text-embedding-3-small`.
- Tích hợp embedding provider (config qua `.env`).
- Batch embedding + retry/timeout theo policy.
- Upsert vào vector DB (Qdrant/pgvector) theo `chunk_id`.
- Xử lý `removed_urls`: delete hoặc soft-delete vector cũ.
- Ghi `embeddings.jsonl` (status theo batch/chunk).

### Bước 9.3: Ingest API + job status

- FastAPI endpoint `POST /ingest`.
- Endpoint `GET /jobs/{run_id}` để theo dõi tiến trình.
- Hỗ trợ `dry_run` để estimate chi phí.
- Thêm `POST /ingest/reindex` (re-embed từ cleaned cache, không scrape lại).
- Chuẩn hoá error contract (`validation_error`, `quota_exceeded`, `upstream_error`...).

### Bước 9.4: Observability + guardrails

- Structured logs theo `run_id`.
- Metrics stage duration + token/credit estimate.
- Hard limits: max URL scrape/run, max embedding token/run.
- Cost summary theo run (`scrape_est`, `embed_est`).
- Alert khi tỷ lệ lỗi hoặc `changed_urls` tăng bất thường.
- Chốt lifecycle policy: remove -> inactive, expire `TTL=7 ngày`.

### Bước 9.6: Runtime tuning (baseline)

- Chốt worker concurrency mặc định: `2`.
- Chốt chunk profile RAG: `CHUNK_MAX_WORDS=220`, `CHUNK_MIN_WORDS=50`, `CHUNK_OVERLAP_SENTENCES=2`.
- Thêm các giá trị baseline vào `.env.example`/runtime config cho Phase 9.

### Bước 9.5: QA + rollout

- Unit test delta detection (`new/changed/unchanged/removed`).
- Unit test idempotency `chunk_id`.
- Integration test 2 lần chạy liên tiếp (lần 2 giảm workload).
- Backfill script cho artifact demo cũ.
- Runbook vận hành + rollback checklist.

**Tiêu chí xong phase 9:** chạy incremental ổn định, vector upsert idempotent, có API + observability cơ bản.

### Chia nhỏ công việc (Sprint đề xuất)

**Sprint A (Tuần 1) – Incremental chạy được**

- [x] A1a. Setup infra local (PostgreSQL16 + pgvector, Redis7) + env + healthcheck.
- [x] A1b. Setup Alembic + single baseline migration (`ingest_runs`, `page_index`, `chunk_index`, `rag_chunks`).
- [x] A2. Hash + snapshot index (`page_index_latest.json`, `page_index_snapshot_<run_id>.json`).
- [x] A3. Delta detection + `delta.json`.
- [x] A4. Selective chunking (`chunks_delta.jsonl`) + manifest.
- [x] A5. Smoke test domain thật (lần 2 giảm URL xử lý).

**Definition of done cho A1**
- [x] `docker compose up -d` và services báo `healthy`.
- [x] Chạy `alembic upgrade head` thành công trên Postgres local.
- [x] Verify có đủ 4 bảng nền trong DB (`ingest_runs`, `page_index`, `chunk_index`, `rag_chunks`).

**Sprint B (Tuần 2) – Vector + API ingest**

- [x] B1. Embedding service (batch + retry).
- [x] B2. Vector repository (upsert/delete by `chunk_id`).
- [x] B3. API ingest/job status/dry-run.
- [x] B4. Metrics + guardrails + cost summary.
- [x] B5. Hardening + docs/runbook.

---

## Phase 10 – MindMap Builder (Vector → Tree → OPML)

> Đặc tả chi tiết: [`MINDMAP.md`](MINDMAP.md). Phase này dựng mindmap từ vectors đã upsert ở Phase 9.

### Checklist tổng

- Lấy vectors theo scope (`by_website` / `by_run_id` / `by_chunk_ids`) từ pgvector.
- Reduce dim (UMAP) → cluster (HDBSCAN) top-level.
- Đặt tên branch bằng LLM (chunk đại diện gần centroid).
- Recursive sub-cluster đến `MAX_DEPTH` hoặc cluster đủ nhỏ.
- NER cho leaf (spaCy mặc định, LLM optional).
- Build JSON tree với citation = `chunk_ids`, roll-up từ leaf lên root.
- LLM synthesis viết description cho mỗi node.
- Export OPML 2.0 + ghi artifacts dưới `out/<slug>/mindmap/<mindmap_run_id>/`.
- Bảng metadata `mindmap_runs` (Alembic migration mới).
- Chốt scope đa run theo `notebooklm_id`, và lưu `chunk_text` trực tiếp ở `rag_chunks`.
- Endpoint `POST /mindmap/build`, `GET /mindmap/{id}`, `/tree`, `/opml`.
- Observability + guardrails (token budget, max vectors, dry-run).

### Bước 10.0: Setup hạ tầng & dependency

- Thêm vào `requirements.txt`:
  - `numpy`
  - `umap-learn`
  - `hdbscan`
  - `scikit-learn`
  - `spacy` + model `xx_ent_wiki_sm` (download riêng)
  - `lxml` (cho OPML output đẹp, optional)
- Thêm `.env` keys (giữ default trong `app/config.py`):
  - `MINDMAP_LLM_MODEL=gpt-4o-mini`
  - `MINDMAP_LLM_TEMPERATURE=0.2`
  - `MINDMAP_TOPIC_REPR_K=5`
  - `MINDMAP_MAX_DEPTH=3`
  - `MINDMAP_MIN_RECURSE_SIZE=12`
  - `MINDMAP_SUB_MIN_CLUSTER_SIZE=3`
  - `MINDMAP_NER_PROVIDER=spacy`
  - `MINDMAP_NER_MODEL=xx_ent_wiki_sm`
  - `MINDMAP_MAX_VECTORS_PER_RUN=10000`
  - `MINDMAP_MAX_LLM_CALLS_PER_RUN=200`
  - `MINDMAP_MAX_TOKENS_PER_RUN=200000`
- Alembic migration `create_mindmap_runs` (theo schema ở `MINDMAP.md` §4.3).
- Lưu ý migration hiện tại:
  - notebook scope (`notebooklm_id`) và `chunk_text` đã nằm trong baseline schema.
  - Phase 10 chỉ cần thêm migration mới cho `mindmap_runs` (không cần tách 2-phase cho các cột này).

**Definition of done 10.0:**
- `pip install -r requirements.txt` xong, import `hdbscan`/`umap` không lỗi.
- `alembic upgrade head` tạo bảng `mindmap_runs`.
- `python -m spacy download xx_ent_wiki_sm` thành công (hoặc fallback skip NER có log).
- Có kế hoạch migration 2-phase: add nullable + backfill + enforce `NOT NULL`.

### Bước 10.1: Vector loader

- Implement `app/mindmap/vector_loader.py`:
  - `load_vectors_by_website(host)` → `(chunk_ids, np.ndarray, meta_by_id)`.
  - `load_vectors_by_run_id(run_id)`.
  - `load_vectors_by_chunk_ids(ids)`.
- Đọc trực tiếp `chunk_text` từ `rag_chunks` để dùng cho topic + NER.
- Enforce filter `notebooklm_id` ở mọi mode.
- Validate: dim đồng nhất, không có vector NaN.
- Fail rõ ràng nếu scope rỗng (`not_found_vectors`).

**DOD 10.1:** Smoke `examples/check_phase10_c1.py` in ra `vector_count`, `unique_urls` cho `fptsoftware-com`.

### Bước 10.2: Dim reduction + HDBSCAN top-level

- Implement `app/mindmap/reducer.py` (UMAP wrapper, `random_state=42`).
- Implement `app/mindmap/clusterer.py`:
  - `cluster_top(vectors, params)` → `labels`, metrics (`noise_ratio`, `cluster_count`, `mean_size`).
- Bypass UMAP nếu `N < 20` (dùng cosine distance trực tiếp).
- Ghi `clusters_top.json` cho debug.

**DOD 10.2:** Smoke trả `cluster_count >= 2` và `noise_ratio < 0.5` trên dataset `fptsoftware-com`.

### Bước 10.3: Representative + Topic Extraction

- Implement `app/mindmap/representative.py` (top-K theo cosine sim với centroid).
- Implement `app/mindmap/topic_extractor.py`:
  - Prompt theo `MINDMAP.md` §5.5.
  - Strict JSON parse + retry 1 lần nếu invalid.
  - Hợp đồng output: `{title, summary}`.
- Tích hợp guardrail `MINDMAP_MAX_LLM_CALLS_PER_RUN`.

**DOD 10.3:** Mỗi top-level cluster có `title` (3–7 từ) + `summary` (≤ 30 từ).

### Bước 10.4: Recursive sub-clustering

- Implement `cluster_recursive(cluster_chunks, depth, params)` trong `clusterer.py`.
- Áp dụng `MIN_RECURSE_SIZE`, `SUB_MIN_CLUSTER_SIZE`, `MAX_DEPTH`.
- Đảm bảo idempotent về thứ tự (sort cluster theo size giảm dần).
- Mỗi sub-cluster cũng đi qua Topic Extraction.

**DOD 10.4:** Cây cluster có ít nhất 1 nhánh có sub-branch trên dataset thật, depth ≤ `MAX_DEPTH`.

### Bước 10.5: NER cho leaf

- Implement `app/mindmap/ner.py`:
  - Provider `spacy` mặc định, fallback `[]` nếu model thiếu.
  - Provider `llm` (optional, dùng prompt JSON strict).
- Aggregate top-K entities theo (`text`, `label`).
- Lưu `entities.json`.

**DOD 10.5:** Mỗi leaf có ≤ `NER_TOP_K` entities; nếu spaCy fail thì log + entities rỗng (không crash).

### Bước 10.6: Build JSON tree + roll-up citations

- Implement `app/mindmap/tree_builder.py`:
  - Roll-up `chunk_ids` từ leaf lên root.
  - Sinh `id` ổn định trong build (`n_<depth>_<index>`).
  - Validate: tổng số `chunk_ids` ở root = số input vectors.
- Output `mindmap.json`.

**DOD 10.6:** `mindmap.json` parse được, mọi `chunk_ids` đều có trong `rag_chunks`.

### Bước 10.7: LLM synthesis

- Implement `app/mindmap/synthesizer.py`:
  - Leaf prompt: chunk + entities → 1 câu.
  - Non-leaf: titles + summaries của children → 1–2 câu.
  - Root: top-level titles → 2–3 câu.
- Cờ `MINDMAP_SKIP_SYNTHESIS=true` để bỏ qua.
- Update `description` field trong tree.

**DOD 10.7:** Mỗi node có `description` ≠ rỗng (trừ khi skip).

### Bước 10.8: OPML export

- Implement `app/mindmap/opml_exporter.py`:
  - OPML 2.0, escape XML đầy đủ.
  - Attribute `_chunkIds` cho leaf.
  - Output `mindmap.opml` UTF-8.
- Smoke test: import file vào XMind / Logseq, không lỗi parse.

**DOD 10.8:** File OPML mở được, hiển thị đúng cấu trúc cây.

### Bước 10.9: Service orchestrator + API

- Implement `app/mindmap/service.py` (`build_mindmap(...)`).
- Implement `app/mindmap/repository.py` (CRUD `mindmap_runs`).
- Thêm endpoint trong `app/main.py`:
  - `POST /mindmap/build`
  - `GET /mindmap/{id}`
  - `GET /mindmap/{id}/tree`
  - `GET /mindmap/{id}/opml`
- Xử lý `dry_run=true` → không gọi LLM, trả estimate.

**DOD 10.9:** Chạy 1 lệnh `curl POST /mindmap/build` ra `mindmap_run_id`, `GET /mindmap/{id}` báo `success` sau khi pipeline xong.

### Bước 10.10: Observability + guardrails

- Stage durations + counts vào `manifest.json`.
- Cảnh báo `noise_ratio > 0.5`.
- Hard limit `MAX_VECTORS_PER_RUN`, `MAX_LLM_CALLS_PER_RUN`, `MAX_TOKENS_PER_RUN`.
- Cost summary trả trong response.

**DOD 10.10:** Vượt budget → trả `quota_exceeded`, không bắt đầu build.

### Bước 10.11: QA + smoke + docs

- Unit test:
  - Tree roll-up đúng số chunk.
  - OPML escape ký tự đặc biệt.
  - Topic extractor parse JSON robust.
- Smoke E2E trên `fptsoftware-com`.
- Cập nhật `README.md` + `RUNBOOK.md` cho flow mindmap.

**Tiêu chí xong Phase 10:**
- API build mindmap end-to-end ổn định.
- OPML render được trên XMind/Logseq.
- Re-run idempotent (cùng input → tree gần như nhau).
- Có guardrail + dry-run.

### Sprint đề xuất Phase 10

**Sprint C (Tuần 3) – Cluster + Topic**

- [ ] C1. Bước 10.0 + 10.1 (deps + vector loader).
- [ ] C2. Bước 10.2 (UMAP + HDBSCAN top-level).
- [ ] C3. Bước 10.3 (representative + topic extraction).
- [ ] C4. Bước 10.4 (recursive sub-cluster).

**Sprint D (Tuần 4) – Tree + Render + API**

- [ ] D1. Bước 10.5 (NER) + 10.6 (tree builder).
- [ ] D2. Bước 10.7 (synthesis) + 10.8 (OPML).
- [ ] D3. Bước 10.9 (service + API + Alembic).
- [ ] D4. Bước 10.10 + 10.11 (guardrails, QA, docs).

---

## Kế hoạch thực thi đề xuất (theo ngày)

- **Ngày 1:** Phase 0-1 (khung + config + models)
- **Ngày 2:** Phase 2-3 (search + map)
- **Ngày 3:** Phase 4-5 (scrape + cleaner)
- **Ngày 4:** Phase 6-7 (chunk + orchestrator + CLI)
- **Ngày 5:** Phase 8 + fix bug + polish docs
- **Ngày 6-7:** Phase 9 (incremental + embedding + ingest API)
- **Ngày 8-9:** Phase 10 Sprint C (cluster + topic)
- **Ngày 10-11:** Phase 10 Sprint D (tree + render + API)

---

## Checklist “Definition of Done”

- Chạy được command demo end-to-end.
- Có `chunks.jsonl` đúng schema mới.
- Không hard-code API key.
- Có test tối thiểu cho cleaner + chunker.
- Docs khớp với implementation thực tế.

