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
- Thiết lập migration tool (`Alembic`) và migration baseline cho 3 bảng metadata.

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
- [x] A1b. Setup Alembic + migration baseline (`ingest_runs`, `page_index`, `chunk_index`).
- [x] A2. Hash + snapshot index (`page_index_latest.json`, `page_index_snapshot_<run_id>.json`).
- [x] A3. Delta detection + `delta.json`.
- [x] A4. Selective chunking (`chunks_delta.jsonl`) + manifest.
- [x] A5. Smoke test domain thật (lần 2 giảm URL xử lý).

**Definition of done cho A1**
- [x] `docker compose up -d` và services báo `healthy`.
- [x] Chạy `alembic upgrade head` thành công trên Postgres local.
- [x] Verify có đủ 3 bảng metadata trong DB.

**Sprint B (Tuần 2) – Vector + API ingest**

- [x] B1. Embedding service (batch + retry).
- [x] B2. Vector repository (upsert/delete by `chunk_id`).
- [x] B3. API ingest/job status/dry-run.
- [x] B4. Metrics + guardrails + cost summary.
- [x] B5. Hardening + docs/runbook.

---

## Kế hoạch thực thi đề xuất (theo ngày)

- **Ngày 1:** Phase 0-1 (khung + config + models)
- **Ngày 2:** Phase 2-3 (search + map)
- **Ngày 3:** Phase 4-5 (scrape + cleaner)
- **Ngày 4:** Phase 6-7 (chunk + orchestrator + CLI)
- **Ngày 5:** Phase 8 + fix bug + polish docs
- **Ngày 6-7:** Phase 9 (incremental + embedding + ingest API)

---

## Checklist “Definition of Done”

- Chạy được command demo end-to-end.
- Có `chunks.jsonl` đúng schema mới.
- Không hard-code API key.
- Có test tối thiểu cho cleaner + chunker.
- Docs khớp với implementation thực tế.

