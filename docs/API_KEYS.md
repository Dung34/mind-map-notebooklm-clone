# API Keys – Hướng dẫn lấy & cấu hình

Dự án hiện tại cần **2 API key bắt buộc**:
- Perplexity (Stage 1: Search API)
- FireCrawl (Stage 2-3: map/scrape)

Phase 9 (embedding + vector index) cần thêm:
- OpenAI (Embedding API)

---

## 1. Perplexity API

**Mục đích:** Stage 1 – tìm seed URLs bằng Search API (`client.search.create`).

### Lấy API key
1. Truy cập <https://www.perplexity.ai/settings/api>.
2. Đăng nhập tài khoản Perplexity.
3. Bấm **Generate API Key** -> copy key `pplx-...`.
4. Đảm bảo tài khoản có credit khả dụng.

### Cấu hình
```env
PERPLEXITY_API_KEY=pplx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
PERPLEXITY_MAX_SEARCH_RESULTS=20
PERPLEXITY_VERIFY_HTTP=true
```

- `PERPLEXITY_MAX_SEARCH_RESULTS`: 1–20 (giới hạn API).
- `PERPLEXITY_VERIFY_HTTP`: `true`/`false` — có HEAD/GET kiểm tra URL seed trước khi giữ.

---

## 2. FireCrawl API

**Mục đích:** Stage 2 (`/map`) + Stage 3 (`/scrape`).

### Lấy API key
1. Truy cập <https://www.firecrawl.dev>.
2. Đăng ký bằng GitHub/Google.
3. Vào **Dashboard -> API Keys** -> copy key `fc-...`.

### Plan
| Plan | Credits/tháng | Giá |
|------|---------------|-----|
| Free | 500 | $0 |
| Hobby | 3,000 | $19/tháng |
| Standard | 100,000 | $99/tháng |

### Pricing cho Search (`/map` + `search` param)
- Dùng `search` trong `/map` **không cộng thêm phí riêng**.
- Tính theo credit của `/map`: **1 credit / request**.
- Mỗi `/scrape` thành công: **1 credit / URL**.

> Ví dụ: 1 lần `/map` (search theo domain) + 40 URL scrape thành công = **41 credits**.

### Cấu hình
```env
FIRECRAWL_API_KEY=fc-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
FIRECRAWL_MAP_LIMIT=50
FIRECRAWL_MAP_INCLUDE_SUBDOMAINS=false
FIRECRAWL_SCRAPE_CONCURRENCY=5
FIRECRAWL_SCRAPE_WAIT_MS=1500
FIRECRAWL_SCRAPE_ONLY_MAIN=true
```

---

## 3. OpenAI API (Embedding)

**Mục đích:** Phase 9 – tạo embedding cho chunks (model mặc định: `text-embedding-3-small`).

### Lấy API key
1. Truy cập <https://platform.openai.com/api-keys>.
2. Tạo secret key mới -> copy key `sk-...`.
3. Nạp billing hợp lệ cho project.

### Pricing tham khảo (Embedding)

> Giá có thể thay đổi theo thời gian, luôn kiểm tra trang pricing chính thức trước khi chốt ngân sách.

- Trang pricing: <https://platform.openai.com/docs/pricing>
- Model đang dùng: `text-embedding-3-small`
- Cách tính: theo **input tokens**

Ví dụ ước lượng:
- 1,000,000 tokens input với `text-embedding-3-small`:
  - nếu đơn giá là **$0.02 / 1M tokens** -> chi phí ~ **$0.02**

Công thức:
`cost_estimate = (input_tokens / 1_000_000) * unit_price_per_1m_tokens`

### Bảng ước lượng nhanh (tham chiếu)

> Ví dụ dưới đây dùng **đơn giá giả định** `unit_price_per_1m_tokens = $0.02` cho `text-embedding-3-small`.
> Khi pricing thay đổi, chỉ cần thay biến đơn giá là ra số mới.

| Input tokens | Công thức                 | Chi phí ước lượng |
|--------------|---------------------------|-------------------|
| 1,000,000    | `1 * $0.02`               | `$0.02`           |
| 10,000,000   | `10 * $0.02`              | `$0.20`           |
| 50,000,000   | `50 * $0.02`              | `$1.00`           |

Khuyến nghị thực tế:
- Ghi `embedding_tokens_total` vào `stats.json` sau mỗi run.
- Tính thêm `embedding_cost_estimate_usd` để theo dõi trend chi phí theo domain/tháng.

### Cấu hình
```env
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
EMBEDDING_MODEL=text-embedding-3-small
```

---

## 4. File `.env` đầy đủ

Sao chép `.env.example` -> `.env` rồi điền:

```env
# === Perplexity ===
PERPLEXITY_API_KEY=
PERPLEXITY_MAX_SEARCH_RESULTS=20
PERPLEXITY_VERIFY_HTTP=true

# === FireCrawl ===
FIRECRAWL_API_KEY=
FIRECRAWL_MAP_LIMIT=50
FIRECRAWL_MAP_INCLUDE_SUBDOMAINS=false
FIRECRAWL_SCRAPE_CONCURRENCY=5
FIRECRAWL_SCRAPE_WAIT_MS=1500
FIRECRAWL_SCRAPE_ONLY_MAIN=true

# === Pipeline ===
OUTPUT_DIR=./out
LOG_LEVEL=INFO
HTTP_TIMEOUT=60
CLEAN_PAGE_MIN_WORDS=50
CHUNK_MAX_WORDS=220
CHUNK_MIN_WORDS=50
CHUNK_OVERLAP_SENTENCES=2

# === Phase 9 (Productionization) ===
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/cleaner_raw_data
VECTOR_TABLE=rag_chunks
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=
EMBEDDING_MODEL=text-embedding-3-small
WORKER_CONCURRENCY=2
INACTIVE_TTL_DAYS=7
```

---

## 5. Bảo mật

- **KHÔNG** commit `.env` lên git – đã có trong `.gitignore`.
- Khi deploy: dùng secret manager (AWS Secrets Manager, Doppler, 1Password CLI...).
- Rotate key định kỳ để giảm rủi ro lộ key.
- Khi share repo: dùng `.env.example` làm template, **không có giá trị thật**.

---

## 6. Kiểm tra nhanh API key

Một script `examples/check_keys.py` (sẽ thêm sau) giúp ping 2 service:

```bash
python examples/check_keys.py
```

Output mong muốn:
```
[OK]  Perplexity   – search.create returned 10 results in 1.2s
[OK]  FireCrawl    – /map?url=example.com returned 12 links in 0.8s
```
