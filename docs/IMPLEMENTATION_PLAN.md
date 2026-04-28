# Implementation Plan – Từng bước nhỏ để chạy được dự án

Mục tiêu: triển khai từ tài liệu hiện có thành project Python chạy được end-to-end:

1) Nhận input `company`/`website`  
2) Search seed URLs bằng Perplexity Search API  
3) Discover + scrape bằng FireCrawl  
4) Clean markdown theo pipeline hiện tại  
5) Chunk + enrich metadata  
6) Xuất `chunks.jsonl` và thống kê

---

## Nguyên tắc triển khai

- Mỗi bước nhỏ đều có **output kiểm chứng được**.
- Chỉ chuyển bước tiếp theo khi bước hiện tại chạy ổn.
- Ưu tiên code đơn giản, dễ debug, đúng theo docs trước rồi tối ưu sau.
- Mọi biến cấu hình đi qua `.env`.

---

## Phase 0 – Khởi tạo khung dự án

### Bước 0.1: Chốt cấu trúc thư mục
- [ ] Tạo khung:
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
- [ ] Tạo `requirements.txt` tối thiểu:
  - `pydantic`
  - `python-dotenv`
  - `perplexityai`
  - `firecrawl-py`
  - `httpx`
  - `tenacity` (retry)

### Bước 0.3: Chốt config runtime
- [ ] Đồng bộ `.env.example` với 2 key:
  - `PERPLEXITY_API_KEY`
  - `FIRECRAWL_API_KEY`
- [ ] Add cấu hình pipeline:
  - `FIRECRAWL_MAP_LIMIT`
  - `FIRECRAWL_SCRAPE_CONCURRENCY`
  - `OUTPUT_DIR`
  - `HTTP_TIMEOUT`

**Tiêu chí xong phase 0:** import được toàn bộ module, không lỗi cấu trúc.

---

## Phase 1 – Config + Data Models

### Bước 1.1: Implement `app/config.py`
- [ ] Load env bằng `python-dotenv`.
- [ ] Expose object `Settings` (Pydantic Settings hoặc dataclass).
- [ ] Validate biến bắt buộc (`PERPLEXITY_API_KEY`, `FIRECRAWL_API_KEY`).

### Bước 1.2: Implement `app/models.py`
- [ ] Tạo model:
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
- [x] Tạo `Perplexity` client trong `app/search/perplexity_search.py`.
- [x] Implement `search_seed_urls(company, website, max_results=20)`.
- [x] Parse `res.results` -> list URL strings.

### Bước 2.2: Normalize + validate seed URLs
- [x] Implement `normalize_url()`.
- [x] Merge URL từ search + website input + manual seeds.
- [x] Dedupe theo `scheme + host + path`.

### Bước 2.3: Verify URL sống/chết
- [x] HEAD/GET nhẹ bằng `httpx`.
- [x] Retry timeout/5xx (tenacity).
- [x] Trả `list[SeedURL]` có `source`.

**Tiêu chí xong phase 2:** chạy unit script và in được >= vài seed URL hợp lệ cho 1 công ty thật.

---

## Phase 3 – Stage 2 (FireCrawl Map)

### Bước 3.1: Implement map call
- [x] `app/discover/firecrawl_map.py`
- [x] Gọi FireCrawl v2 `client.map(...)` với:
  - `url`
  - `search` (URL gốc chuẩn hoá)
  - `limit`
  - `include_subdomains`

### Bước 3.2: Filter URL
- [x] Blacklist path rác (`/tag`, `/category`, file media...).
- [x] Optional priority path (`/about`, `/services`, `/contact`...).
- [x] Convert sang `list[DiscoveredURL]`.

**Tiêu chí xong phase 3:** từ 1 website trả được danh sách URL sạch, không quá noisy.

---

## Phase 4 – Stage 3 (FireCrawl Scrape)

### Bước 4.1: Implement scrape one URL
- [x] `app/crawl/firecrawl_scrape.py`
- [x] `scrape_url(url)` trả `RawPage`.
- [x] Lấy markdown + metadata title/language/status.

### Bước 4.2: Implement scrape many URLs
- [x] Chạy song song có semaphore theo `FIRECRAWL_SCRAPE_CONCURRENCY`.
- [x] Skip lỗi từng URL, không fail cả batch.
- [x] Trả list `RawPage`.

**Tiêu chí xong phase 4:** scrape thành công ít nhất 5-10 URL trong domain thật.

---

## Phase 5 – Stage 4 (Cleaner)

### Bước 5.1: Port code cleaner vào module
- [x] Đưa nguyên logic:
  - `strip_markdown`
  - `filter_blocks`
  - `dedup_blocks`

### Bước 5.2: Adapter từ `RawPage` -> `CleanedPage`
- [x] Implement `clean_page_markdown(raw_page) -> CleanedPage`.
- [x] Tính `word_count`.

### Bước 5.3: Quality guard
- [x] Nếu text quá ngắn thì gắn cờ/skip theo rule.
- [x] Log số block trước/sau clean.

**Tiêu chí xong phase 5:** output text rõ ràng, không còn menu/footer rõ rệt.

---

## Phase 6 – Stage 5 (Rule-based Chunking + Enrich)

### Bước 6.1: Port chunking logic
- [x] Đưa logic:
  - heading heuristic
  - sentence split
  - `CHUNK_MAX_WORDS`
  - `CHUNK_MIN_WORDS`
  - `OVERLAP_SENTENCES` (env: `CHUNK_OVERLAP_SENTENCES`)

### Bước 6.2: Enrich metadata
- [x] Implement `enrich_chunks(...)` theo schema hiện tại:
  - `chunk_id`, `source_url`, `page_title`, `section_heading`
  - `text`, `word_count`, `crawled_at`, `chunk_index`

**Tiêu chí xong phase 6:** sinh `list[Chunk]` ổn định, metadata đầy đủ.

---

## Phase 7 – Orchestrator + CLI demo

### Bước 7.1: Implement `run_pipeline`
- [x] Nối 5 stage theo flow docs.
- [x] Trả `PipelineResult`.

### Bước 7.2: Ghi artifact ra thư mục output
- [x] `out/<company-slug>/seeds.json`
- [x] `out/<company-slug>/discovered.json`
- [x] `out/<company-slug>/raw/*.json`
- [x] `out/<company-slug>/cleaned/*.json`
- [x] `out/<company-slug>/chunks.jsonl`
- [x] `out/<company-slug>/stats.json`

### Bước 7.3: Demo command
- [x] `python examples/run_demo.py --company "..." --website "..." --limit 10`

**Tiêu chí xong phase 7:** chạy 1 lệnh ra đủ artifacts, không crash.

---

## Phase 8 – Test tối thiểu trước khi dùng thật

### Bước 8.1: Unit test
- [ ] Test `normalize_url`.
- [ ] Test `strip_markdown/filter_blocks/dedup_blocks`.
- [ ] Test chunking boundary cases.

### Bước 8.2: Integration test nhẹ
- [ ] 1 domain thật, limit nhỏ (5-10 URL).
- [ ] Kiểm tra output có chunk, không rỗng, schema đúng.

### Bước 8.3: Regression dataset nhỏ
- [ ] Tạo 2-3 markdown mẫu "xấu".
- [ ] So sánh output cleaner/chunker với golden files.

**Tiêu chí xong phase 8:** tự tin chạy lặp lại nhiều domain mà không vỡ pipeline.

---

## Kế hoạch thực thi đề xuất (theo ngày)

- **Ngày 1:** Phase 0-1 (khung + config + models)
- **Ngày 2:** Phase 2-3 (search + map)
- **Ngày 3:** Phase 4-5 (scrape + cleaner)
- **Ngày 4:** Phase 6-7 (chunk + orchestrator + CLI)
- **Ngày 5:** Phase 8 + fix bug + polish docs

---

## Checklist “Definition of Done”

- [x] Chạy được command demo end-to-end.
- [x] Có `chunks.jsonl` đúng schema mới.
- [ ] Không hard-code API key.
- [ ] Có test tối thiểu cho cleaner + chunker.
- [ ] Docs khớp với implementation thực tế.
