# Pipeline – Chi tiết từng bước

Tài liệu này đi sâu vào **mục đích, input/output, request mẫu, tham số tinh chỉnh và pitfall** của từng stage.

> Đọc trước `[ARCHITECTURE.md](ARCHITECTURE.md)` để có bức tranh tổng thể.

---

## Stage 1 – Perplexity Seed Discovery

### Mục tiêu

Từ **tên công ty** và/hoặc **website URL**, dùng Perplexity để tìm danh sách URL "hạt giống" (seed URLs), sau đó hợp nhất với manual seed (nếu có).

### Tại sao cần stage này?

Khi chỉ có tên công ty, Perplexity giúp tìm nhanh các trang chính thức (homepage/about/products/contact/news) thay vì tự search thủ công.

### Endpoint sử dụng

Dùng **Perplexity Search API** qua SDK (`client.search.create`) để lấy danh sách URL web, sau đó normalize/validate nội bộ.

### SDK mẫu (Perplexity)

```python
import os
from urllib.parse import urlparse, urlunparse
from perplexity import Perplexity

client = Perplexity(api_key=os.getenv("PERPLEXITY_API_KEY"))

def normalize_url(u: str) -> str:
    u = u.strip()
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    p = urlparse(u)
    return urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip("/") or "/", "", "", ""))

def search_perplexity(company: str, website: str | None = None) -> list[str]:
    q = f"Find official URLs for company: {company}."
    if website:
        q += f" Company website: {website}."
    q += " Return homepage, about, products/services, contact, careers, and recent news URLs."

    res = client.search.create(
        query=q,
        max_results=10,
    )
    # Chuẩn hoá về list URL string từ kết quả Search API
    return [item.url for item in res.results if getattr(item, "url", None)]

def build_seed_urls(company: str, website: str, manual_seeds: list[str] | None = None) -> list[str]:
    from_perplexity = search_perplexity(company, website)
    raw = [website] + from_perplexity + (manual_seeds or [])
    normalized = [normalize_url(x) for x in raw if x and x.strip()]
    return sorted(set(normalized))
```

### Output (rút gọn)

```json
[
  "https://fptsoftware.com/",
  "https://fptsoftware.com/about-us",
  "https://fptsoftware.com/services"
]
```

### Hậu xử lý

1. **Merge** URL từ Perplexity + `website` input + manual seeds.
2. **Dedupe** theo URL chuẩn hoá (`scheme + host + path`, bỏ query/fragment).
3. **Validate** định dạng URL bằng `HttpUrl`.
4. **HEAD/GET nhẹ** kiểm tra HTTP 200 để loại URL chết.
5. **Trích xuất domain chính** từ website hoặc URL có tần suất xuất hiện cao nhất.
6. **Output** → `list[SeedURL]`.

### Pitfalls

- Perplexity có thể trả URL không tồn tại/hallucination → bắt buộc verify HTTP.
- Kết quả có thể lẫn social/wiki URL → lọc theo `allowed_domains`.
- Search query quá rộng sẽ kéo nhiều URL nhiễu → nên giữ query ngắn, có company + website.

### Tham số tinh chỉnh


| Param             | Khuyến nghị                     | Ghi chú                                  |
| ----------------- | ------------------------------- | ---------------------------------------- |
| `max_results`     | `10-30`                         | Giới hạn số URL trả về để dễ lọc         |
| `manual_seeds`    | 0-10 URL                        | Bổ sung trang quan trọng nếu đã biết     |
| `validate_http`   | `True`                          | Kiểm tra sống/chết của URL trước stage 2 |
| `allowed_domains` | domain input + subdomain hợp lệ | Chặn URL ngoài phạm vi                   |


---

## Stage 2 – FireCrawl Map

### Mục tiêu

Mở rộng từ **website URL/domain đã xác định ở stage 1** ra các URL có khả năng chứa nội dung.

### SDK sử dụng

`firecrawl-py` (`FirecrawlApp`) thay cho gọi HTTP tay.

### SDK mẫu (`/map`)

```python
from firecrawl import FirecrawlApp

app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))

result = app.map_url(
    "https://fptsoftware.com",
    params={
        "search": "https://fptsoftware.com",
        "limit": 100,
        "includeSubdomains": False,
        "ignoreSitemap": False,
    },
)
urls: list[str] = result.get("links", [])
```

### Cách dùng `search` param trong pipeline này

- `/map` có thể trả về rất nhiều internal links.
- Pipeline này chỉ dùng `search` theo **URL đầu vào** để giữ kết quả bám sát domain mục tiêu.
- Việc lọc trang quan trọng thực hiện ở bước hậu xử lý bằng blacklist/priority paths + `limit`.

### Hậu xử lý

1. **Filter** theo regex blacklist:
  ```python
   BLACKLIST = re.compile(
       r"/(tag|category|page/\d+|search|login|cart|wp-admin|wp-content|"
       r"\.(jpg|png|pdf|zip|mp4))$",
       re.IGNORECASE,
   )
  ```
2. **Whitelist** path quan trọng nếu có:
  ```python
   PRIORITY = ["/about", "/services", "/products", "/careers", "/contact", "/news"]
  ```
3. **Cap** số lượng URL để demo không tốn quota (`limit=20–50`).
4. **Output** → `list[DiscoveredURL]`.

### Pitfalls

- Free tier FireCrawl có **rate limit 10 req/s** – chỉ gọi `/map` 1 lần/domain là ổn.
- Một số site SPA không có sitemap → `/map` trả về ít URL → cần fallback dùng seed URLs từ stage 1.
- Khi `includeSubdomains=True`, lượng URL có thể tăng gấp 5–10 lần → dùng cẩn thận.

---

## Stage 3 – FireCrawl Crawl (Markdown)

### Mục tiêu

Lấy **nội dung từng URL** dưới dạng Markdown sạch (FireCrawl đã chạy headless browser, render JS, strip HTML noise).

### Hai endpoint, chọn theo nhu cầu


| Endpoint     | Dùng khi                           | Cơ chế                        |
| ------------ | ---------------------------------- | ----------------------------- |
| `/v1/scrape` | Đã có list URL cụ thể (≤ vài chục) | Đồng bộ, mỗi call = 1 URL     |
| `/v1/crawl`  | Cần crawl đệ quy cả site           | Async job, có `jobId` để poll |


Demo này dùng `**/v1/scrape`** vì đã có URL từ stage 2.

### SDK mẫu (`/scrape`)

```python
result = app.scrape_url(
    url,
    params={
        "formats": ["markdown"],         # có thể thêm "html", "links"
        "onlyMainContent": True,         # bỏ header/footer/nav
        "waitFor": 1500,                 # ms, chờ JS render
        "blockAds": True,
        "removeBase64Images": True,
    },
)["data"]
markdown = result["markdown"]
title    = result["metadata"]["title"]
lang     = result["metadata"].get("language")
```

### Crawl song song

```python
sem = asyncio.Semaphore(5)        # tránh vượt rate limit FireCrawl

async def scrape_one(url: str) -> RawPage | None:
    async with sem:
        try:
            ...
        except Exception:
            return None

pages = await asyncio.gather(*(scrape_one(u) for u in urls))
pages = [p for p in pages if p]
```

### Pitfalls

- `onlyMainContent=True` đôi khi **cắt nhầm** nội dung trên site có layout phức tạp → nếu output rỗng, retry với `False`.
- Trang Cloudflare/captcha → FireCrawl trả 403 → skip + log.
- **Quota:** mỗi call `/scrape` thành công = 1 credit. Cẩn thận khi limit lớn.

---

## Stage 4 – Clean Markdown → Plain Text

### Mục tiêu

Áp dụng đúng pipeline cleaner hiện tại:

1. `strip_markdown` (remove syntax markdown/html).
2. `filter_blocks` (lọc nav/boilerplate theo block).
3. `dedup_blocks` (loại paragraph trùng).
4. Trả về plain text sạch để chunking.

### Pipeline xử lý (theo code)

```python
text = strip_markdown(raw_markdown)
text = filter_blocks(text)
text = dedup_blocks(text)
```

### Quy tắc chính trong cleaner

#### 4.1. Strip markdown/html syntax

Cleaner xử lý trực tiếp bằng regex:

- Xoá HTML tags.
- Xoá image markdown (`![alt](url)`), linked-image.
- Unwrap hyperlink (`[text](url)` -> `text`), xoá bare URL.
- Bỏ heading marker `#`, blockquote `>`, code block/backticks.
- Normalize whitespace (`[ \t]+`, `\n{3,}`).

#### 4.2. Filter noise theo block

Block được tách bằng blank line (`\n\n`). Mỗi block bị loại nếu:

- Là nav block: >=60% dòng có `<5` từ (`_is_nav_block`).
- Line match boilerplate regex (`_BOILERPLATE_RE`), ví dụ `learn more`, `privacy policy`, `đăng nhập`.
- Sau khi filter còn quá ngắn (ít nội dung).

#### 4.3. Dedup block

So sánh key chuẩn hoá `lowercase + collapse spaces`; block trùng sẽ bị bỏ.

### Pitfalls

- Regex-based strip cần test kỹ với markdown lạ (nested links/edge cases).
- Nếu filter quá mạnh, page ngắn có thể bị rỗng sau Stage 4.
- Nên log số block trước/sau filter để debug quality nhanh.

---

## Stage 5 – Rule-based Chunking (heading + sentence overlap)

### Mục tiêu

Chunk theo đúng heuristic trong `chunk_text`:

- Ưu tiên tách theo section heading.
- Chunk theo số từ (word-based), không dùng token-based splitter.
- Overlap theo **số câu** giữa các chunk liên tiếp.

### Cách hoạt động (theo code)

```
1. Duyệt từng line trong cleaned text.
2. Detect heading bằng heuristic:
   - 2..15 từ
   - Không kết thúc bằng . , ; : ! ?
   - Từ đầu viết hoa
   - Không chứa dấu chấm/phẩy
3. Gom body theo từng section heading.
4. Tách section body thành câu (_split_into_sentences).
5. Tích luỹ câu đến CHUNK_MAX_WORDS (=400) thì flush chunk.
6. Giữ OVERLAP_SENTENCES (=2) câu cuối làm overlap cho chunk sau.
7. Nếu chunk < CHUNK_MIN_WORDS (=15): merge vào chunk trước hoặc bỏ.
```

### Chunk schema thực tế

`enrich_chunks(...)` tạo output có metadata:

```python
{
  "chunk_id": "ab12cd34ef56",
  "source_url": "...",
  "page_title": "...",
  "section_heading": "...",
  "text": "...",
  "word_count": 123,
  "crawled_at": "2026-04-28T03:00:00+00:00",
  "chunk_index": 0
}
```

### Tham số hiện tại trong code


| Param                        | Giá trị (`.env`)              |
| ---------------------------- | ----------------------------- |
| `CHUNK_MAX_WORDS`            | `400`                         |
| `CHUNK_MIN_WORDS`            | `15`                          |
| `CHUNK_OVERLAP_SENTENCES`    | `2` (tương đương overlap câu) |


### Pitfalls

- Sentence splitter hiện tại là regex đơn giản, có thể chưa chuẩn cho mọi câu tiếng Việt.
- Heading heuristic có thể nhận nhầm câu ngắn thành heading ở một số trang.
- Merge chunk ngắn vào chunk trước làm chunk cuối có thể vượt `CHUNK_MAX_WORDS` nhẹ.

---

## Output cuối cùng

Mỗi lần chạy pipeline, lưu ra `out/<company-slug>/`:

```
out/fpt-software/
├── seeds.json          # SeedURL[]
├── discovered.json     # DiscoveredURL[]
├── raw/
│   ├── 0001.json       # RawPage
│   └── ...
├── cleaned/
│   ├── 0001.json       # CleanedPage
│   └── ...
├── chunks.jsonl        # 1 dòng = 1 Chunk
└── stats.json          # counts + duration mỗi stage
```

`chunks.jsonl` là artifact chính, có thể đẩy thẳng vào:

- Embedding pipeline → vector DB.
- Hoặc dùng làm input cho fine-tuning / evaluation.

---

## Phase 9 – Incremental Ingest + Embedding Pipeline

Phase 9 mở rộng pipeline hiện tại (stage 1-5) bằng các bước sau để phục vụ vận hành RAG thực tế.

### Stage 6 – Delta detection (theo URL + hash)

**Mục tiêu:** xác định trang mới/thay đổi để tránh re-process toàn bộ.

**Input:**
- `cleaned/*.json` của run hiện tại
- snapshot metadata của run trước (url, content_hash)
- cleaned cache của run trước (để skip scrape nếu bật tối ưu)

**Output:**
- `delta.json` gồm:
  - `new_urls`
  - `changed_urls`
  - `unchanged_urls`
  - `removed_urls` (tuỳ chính sách)

**Pseudo-flow:**

```python
for page in cleaned_pages:
    h = sha256(normalize_text(page.text))
    prev = previous_index.get(page.url)
    if not prev:
        new_urls.append(page.url)
    elif prev.content_hash != h:
        changed_urls.append(page.url)
    else:
        unchanged_urls.append(page.url)
```

### Stage 7 – Re-chunk selective

Chỉ re-chunk cho `new_urls + changed_urls`:

- URL không đổi: giữ chunk cũ.
- URL thay đổi: regenerate chunk, đánh dấu chunk cũ là superseded.

Kết quả: `chunks_delta.jsonl`.

### Stage 7b – Scrape optimization (A5)

Mặc định (`FIRECRAWL_SKIP_SCRAPE_FOR_KNOWN_URLS=true`):

- URL đã có trong `page_index_latest.json` sẽ **không gọi scrape**.
- Pipeline dùng `cleaned` cache của run trước cho các URL này.
- Chỉ scrape URL mới (hoặc URL known nhưng thiếu cache local).

Stats quan trọng:
- `scrape_target_count`: số URL mục tiêu từ map + limit.
- `scrape_selected_count`: số URL thực sự gọi scrape.
- `scrape_skipped_count`: số URL được skip scrape nhờ cache.

### Stage 8 – Embedding + Vector upsert

**Input:** `chunks_delta.jsonl`.

**Process:**
1. Batch chunk theo kích thước tối ưu API embedding.
2. Generate vector.
3. Upsert vector DB với key `chunk_id`.
4. Ghi `embeddings.jsonl` + lỗi theo từng batch.

**Baseline đã chốt (Phase 9):**
- Embedding provider: OpenAI
- Embedding model: `text-embedding-3-small`
- Vector store: PostgreSQL 16 + `pgvector`
- Worker concurrency: `2` (best effort, cost-first)

**Metadata tối thiểu khi upsert:**
- `chunk_id`
- `source_url`
- `page_title`
- `section_heading`
- `crawled_at`
- `run_id`
- `content_hash`

### Stage 9 – Publish manifest

Sinh `manifest.json` để truy vết lần chạy:

```json
{
  "run_id": "2026-04-28T13-40-12Z_fptsoftware-com",
  "input": {"website": "fptsoftware.com", "limit": 20},
  "stats": {
    "discovered_count": 42,
    "raw_page_count": 20,
    "chunk_count_total": 640,
    "chunk_count_delta": 85
  },
  "artifacts": {
    "delta": "out/fptsoftware-com/delta.json",
    "chunks_delta": "out/fptsoftware-com/chunks_delta.jsonl",
    "embeddings": "out/fptsoftware-com/embeddings.jsonl"
  }
}
```

### Khuyến nghị vận hành

- Chạy `dry_run` trước để ước lượng chi phí (scrape + embedding).
- Thiết lập `max_urls_per_run` và `max_embedding_tokens_per_run`.
- Alert khi `changed_urls` tăng đột biến hoặc tỷ lệ chunk lỗi vượt ngưỡng.
- URL bị remove: chuyển inactive, expire sau `TTL=7 ngày`.

### Chunk profile cho RAG (đã chốt)

- `CHUNK_MAX_WORDS=220`
- `CHUNK_MIN_WORDS=50`
- `CHUNK_OVERLAP_SENTENCES=2`

