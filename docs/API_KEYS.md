# API Keys – Hướng dẫn lấy & cấu hình

Dự án hiện tại cần **2 API key bắt buộc**:
- Perplexity (Stage 1: Search API)
- FireCrawl (Stage 2-3: map/scrape)

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

## 3. File `.env` đầy đủ

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
CHUNK_MAX_WORDS=400
CHUNK_MIN_WORDS=15
CHUNK_OVERLAP_SENTENCES=2
```

---

## 4. Bảo mật

- **KHÔNG** commit `.env` lên git – đã có trong `.gitignore`.
- Khi deploy: dùng secret manager (AWS Secrets Manager, Doppler, 1Password CLI...).
- Rotate key định kỳ để giảm rủi ro lộ key.
- Khi share repo: dùng `.env.example` làm template, **không có giá trị thật**.

---

## 5. Kiểm tra nhanh API key

Một script `examples/check_keys.py` (sẽ thêm sau) giúp ping 2 service:

```bash
python examples/check_keys.py
```

Output mong muốn:
```
[OK]  Perplexity   – search.create returned 10 results in 1.2s
[OK]  FireCrawl    – /map?url=example.com returned 12 links in 0.8s
```
