# Architecture – CleanerRawData Pipeline

Tài liệu này mô tả kiến trúc tổng thể, data model và các quyết định thiết kế của pipeline.

---

## 1. High-level architecture

```mermaid
flowchart TB
    subgraph Input
        I1[Tên công ty]
        I2[Website URL]
    end

    subgraph Stage1[1. Search API - Perplexity]
        S1[Perplexity SDK<br/>client.search.create()<br/>query: company + website]
    end

    subgraph Stage2[2. Discover - FireCrawl Map]
        S2[POST /v1/map<br/>search: website URL<br/>limit: N]
    end

    subgraph Stage3[3. Crawl - FireCrawl]
        S3a[POST /v1/scrape<br/>formats: markdown]
        S3b[POST /v1/crawl<br/>limit, includePaths]
    end

    subgraph Stage4[4. Clean Markdown]
        S4[strip_markdown<br/>filter_blocks<br/>dedup_blocks]
    end

    subgraph Stage5[5. Rule-based Chunking]
        S5[Heading heuristic<br/>+ sentence split<br/>+ overlap by sentences]
    end

    subgraph Storage
        DB[(JSONL / Parquet<br/>+ optional VectorDB)]
    end

    I1 --> S1
    I2 --> S1
    I2 --> S2
    S1 -->|seed URLs + domains| S2
    S2 -->|filtered URLs| S3a
    S2 -->|filtered URLs| S3b
    S3a --> S4
    S3b --> S4
    S4 --> S5
    S5 --> DB
```

---

## 2. Data model giữa các bước

Tất cả model dùng **Pydantic v2** để validate.

```python
# app/models.py (khung)

from pydantic import BaseModel, HttpUrl
from datetime import datetime
from typing import Optional, Literal

class SeedURL(BaseModel):
    url: HttpUrl
    source: Literal["perplexity", "user_input", "manual_seed"]
    title: Optional[str] = None
    snippet: Optional[str] = None
    relevance: Optional[float] = None   # score tự gán (nếu cần)

class DiscoveredURL(BaseModel):
    url: HttpUrl
    domain: str
    discovered_via: Literal["firecrawl_map"]
    score: Optional[float] = None

class RawPage(BaseModel):
    url: HttpUrl
    title: Optional[str]
    markdown: str                       # raw markdown từ FireCrawl
    html: Optional[str] = None          # giữ lại nếu cần debug
    status_code: int
    crawled_at: datetime
    language: Optional[str] = None

class CleanedPage(BaseModel):
    url: HttpUrl
    title: Optional[str]
    text: str                            # plain text đã clean
    word_count: int
    language: Optional[str]
    crawled_at: datetime
    is_low_quality: bool = False         # True nếu quá ngắn sau clean

class Chunk(BaseModel):
    chunk_id: str
    section_heading: Optional[str]
    text: str
    source_url: HttpUrl
    page_title: Optional[str]
    word_count: int
    crawled_at: datetime
    chunk_index: int
```

### Vì sao tách `RawPage` và `CleanedPage`?

- **Debug & re-process**: khi đổi rule clean/chunk, không cần crawl lại (tốn quota FireCrawl).
- **Caching**: lưu `RawPage` theo hash để dedupe.
- **Audit**: so sánh trước/sau clean để đánh giá chất lượng.

---

## 3. Orchestrator (`app/pipeline.py`)

```python
async def run_pipeline(
    company: str | None = None,
    website: str | None = None,
    manual_seeds: list[str] | None = None,
    limit: int = 20,
    *,
    no_search: bool = False,
    include_subdomains: bool | None = None,
    map_limit: int | None = None,
    write_outputs: bool = True,
) -> PipelineResult:
    # Stage 1: seeds → Stage 2: map → Stage 3: scrape_many
    # Stage 4–5: clean + chunk; có thể ghi out/<slug>/…
```

Triển khai ở mức demo:
- Stage 1 dùng Perplexity Search API qua SDK (`client.search.create()`), Stage 2-3 dùng FireCrawl SDK.
- Stage 4, 5 chạy CPU-bound → có thể đẩy vào `asyncio.to_thread` hoặc process pool nếu volume lớn.
- Mỗi stage đều **idempotent + cache-able** theo input hash.

---

## 4. Quyết định thiết kế

### 4.1 Vì sao dùng Perplexity Search API ở bước 1?

| Phương án                  | Ưu điểm                                  | Nhược điểm |
|---------------------------|------------------------------------------|------------|
| Seed URL thủ công         | Đơn giản, minh bạch                      | Coverage thấp nếu chỉ có ít URL đầu vào |
| Search API thường         | Kết quả thuần, dễ kiểm soát              | Cần tự lọc nhiều URL nhiễu |
| **Perplexity Search API** | Tập trung cho web search, trả URL nhanh để bootstrap seed | Vẫn cần lọc domain và verify URL |

Chọn Perplexity Search API để bootstrap seed URLs nhanh khi đầu vào chỉ có tên công ty hoặc website chưa đầy đủ.

> **Mitigation:** verify mỗi URL từ kết quả search có HTTP 200 + thuộc domain hợp lệ trước khi đẩy sang stage 2.

### 4.2 Vì sao FireCrawl `/map` thay vì tự crawl sitemap?

- `/map` đã gộp cả `sitemap.xml`, internal links và chỉ cần **search theo URL thường** (`search` param).
- Trả về list URL nhanh (vài giây) – đủ dùng cho demo, không cần dựng worker.
- Có thể filter bằng `includeSubdomains`, `limit` (search theo URL đầu vào).

### 4.3 Vì sao crawl sang Markdown?

- Markdown giữ được **cấu trúc heading** (H1/H2/H3) → giúp chunker bám section, không cắt giữa heading.
- Loại bỏ phần lớn HTML noise (script, style, attribute) ngay từ FireCrawl.
- Dễ dàng convert sang plain text với rule đơn giản hơn rất nhiều so với HTML.

### 4.4 Pipeline clean Markdown (theo cleaner hiện tại)

Thứ tự xử lý:

1. **`strip_markdown`**:
   - Xoá HTML tags, image markdown, linked-image, bare URL.
   - Unwrap hyperlink (`[text](url)` -> `text`).
   - Bỏ markdown markers (`#`, `>`, backticks, code blocks).
   - Normalize whitespace.
2. **`filter_blocks`**:
   - Tách block theo `\n\n`.
   - Loại nav blocks bằng heuristic (`>=60%` dòng ngắn).
   - Loại line match boilerplate regex (EN + VI).
3. **`dedup_blocks`**:
   - Dedupe paragraph theo key chuẩn hoá (`lowercase + collapse spaces`).

### 4.5 Vì sao dùng Rule-based Chunking (heading + sentence overlap)?

| Cách                                      | Ưu | Nhược |
|-------------------------------------------|----|-------|
| Fixed-size (500 words/tokens)             | Đơn giản, nhanh | Cắt giữa câu, mất ngữ cảnh |
| **Rule-based (heading + sentence overlap)** | Bám cấu trúc web tốt, chi phí thấp, dễ debug | Heading heuristic có thể nhận nhầm |
| Semantic (embedding-based)                | Cắt theo chuyển ý tốt hơn | Tốn chi phí và độ phức tạp |

Chọn Rule-based làm mặc định cho MVP để pipeline chạy ổn định, rẻ và dễ debug.

Luật cắt hiện tại:
- Detect section heading theo heuristic (2-15 từ, viết hoa đầu dòng, không kết thúc dấu câu).
- Tách body thành câu bằng regex đơn giản.
- Tích luỹ đến `CHUNK_MAX_WORDS=400` thì tạo chunk.
- Giữ overlap `OVERLAP_SENTENCES=2` cho chunk kế tiếp.
- Chunk ngắn hơn `CHUNK_MIN_WORDS=15` thì merge vào chunk trước hoặc bỏ.

---

## 5. Error handling & retry

| Stage          | Loại lỗi              | Xử lý                                             |
|----------------|----------------------|---------------------------------------------------|
| Perplexity     | 429 / 5xx            | Retry exponential backoff (3 lần, base 2s).         |
| Seed URL input | URL không hợp lệ      | Normalize + validate bằng `HttpUrl`, reject sớm.    |
| FireCrawl map  | Empty result          | Fallback: dùng trực tiếp các seed URL hợp lệ.      |
| FireCrawl scrape | Timeout / 4xx       | Skip URL, ghi log, tiếp tục các URL khác.         |
| Clean markdown | Trang quá ngắn (<50 từ) | Đánh dấu `quality=low`, skip khỏi chunking.    |
| Chunking       | Heading detect hoặc sentence split lệch | Merge chunk ngắn + fallback split theo word count. |

---

## 6. Observability

- **Structured logging** (`structlog` hoặc `loguru`):
  - Mỗi stage log `{stage, input_id, duration_ms, output_count}`.
- **Metrics** (sau demo):
  - `pipeline_pages_crawled_total`
  - `pipeline_chunks_total`
  - `pipeline_stage_duration_seconds{stage=...}`
- **Trace ID**: mỗi lần chạy gắn `run_id = uuid4()` xuyên suốt 5 stage.

---

## 7. Bảo mật & rate limit

- API keys load từ `.env`, **không hard-code**.
- Dùng SDK clients:
  - Perplexity qua Search API SDK (`client.search.create`)
  - FireCrawl qua `FirecrawlApp(api_key=...)`
- Bọc call SDK bằng timeout/retry ở service layer.
- Throttle FireCrawl (mặc định free tier ~5 req/s) bằng `asyncio.Semaphore`.
- Tôn trọng `robots.txt` ở stage Map (FireCrawl đã handle, vẫn cần check).

---

## 8. Testing strategy

- **Unit test** cho mỗi stage với SDK mocks (mock Perplexity/FireCrawl client methods).
- **Golden test** cho `clean_markdown`: nhập markdown mẫu → so sánh output với file `.expected.txt`.
- **Integration test** end-to-end với 1 domain nhỏ + record cassette (`vcrpy`).
