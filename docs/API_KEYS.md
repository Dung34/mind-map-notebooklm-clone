# API Keys – Hướng dẫn lấy & cấu hình

Dự án hiện tại cần **2 API key bắt buộc**:
- Perplexity (Stage 1: Search API)
- FireCrawl (Stage 2-3: map/scrape)

Phase 9 (embedding + vector index) cần thêm:
- OpenAI (Embedding API)

Phase 10 (mindmap) dùng thêm **cùng OpenAI key** cho Chat Completions (đặt tên chủ đề / synthesis sau này). NER mặc định **spaCy** (không tốn API).

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

## 5. Tính toán chi phí – toàn bộ flow

Phần này giúp ước lượng **một vòng đời điển hình**: ingest domain → chunk → embed → (tuỳ chọn) mindmap. Số tiền thực tế phụ thuộc **pricing nhà cung cấp tại thời điểm chạy**; luôn đối chiếu link trong từng mục trước khi chốt ngân sách.

### 5.1 Luồng nghiệp vụ và chỗ phát sinh chi phí

| Giai đoạn | Hoạt động | Trả phí API / tài nguyên |
|-----------|-----------|---------------------------|
| **Stage 1 – Seeds** | `build_seed_urls` → Perplexity **Search API** (`search.create`) khi **không** bật `no_search` | Perplexity (theo request, xem §5.3) |
| **Stage 2 – Map** | Firecrawl `/map` (1 request / lần chạy map) | Firecrawl **credits** (1 credit / request map) |
| **Stage 3 – Scrape** | Firecrawl `/scrape` cho từng URL được chọn (trừ URL skip nhờ cache `FIRECRAWL_SKIP_SCRAPE_FOR_KNOWN_URLS`) | Firecrawl **credits** (1 credit / URL scrape thành công, tham khảo §2) |
| **Cleaner + chunk** | Xử lý local | Không |
| **Stage 8 – Embed** | OpenAI Embeddings (`text-embedding-3-small`), batch upsert `rag_chunks` | OpenAI (theo **input tokens**) |
| **Phase 10 – Mindmap** | UMAP / HDBSCAN / cây cluster: **local CPU** | Không |
| **Phase 10 – Topic (C3+)** | `MINDMAP_LLM_MODEL` (mặc định `gpt-4o-mini`), ~1 request / cluster top-level (+ sau này nhiều hơn nếu topic đa tầng / synthesis) | OpenAI Chat (input + output tokens) |
| **Phase 10 – NER (D1, mặc định)** | spaCy | Không (chỉ chi phí vận hành máy) |
| **Phase 10 – NER LLM (tuỳ chọn)** | Chat API | OpenAI (hoặc provider khác) |

**Ingest lặp lại (incremental):** chỉ URL **mới / đổi** mới scrape và embed lại → chi phí Firecrawl + embedding **tỷ lệ thuận với delta**, không phải full domain mỗi lần.

### 5.2 Công thức tổng quát (ước lượng)

Ký hiệu:

- \(S\): số request Perplexity Search (thường **1** mỗi lần ingest có search).
- \(M\): số request map Firecrawl (thường **1**).
- \(N\): số URL scrape Firecrawl thực sự gọi API.
- \(T_{\mathrm{emb}}\): tổng **input tokens** đưa vào embedding trong run (hoặc cả pipeline nếu tính tích lũy).
- \(T_{\mathrm{in}}, T_{\mathrm{out}}\): tổng input/output tokens Chat (mindmap topic / synthesis).
- Giá đơn vị lấy từ bảng §5.3 hoặc từ env ước lượng nội bộ (§5.5).

**Firecrawl (theo credits):**

\[
\text{credits\_run} = M + N
\]

Quy đổi sang USD **phụ thuộc gói** (ví dụ gói trả phí cố định/tháng + hạn mức credit):  
\(\text{USD}_{\mathrm{fc}} \approx \dfrac{\text{credits\_run}}{\text{credits\_month}} \times \text{giá\_gói\_tháng}\) (chỉ là **chỉ báo**; không thay thế dashboard Firecrawl).

**Perplexity Search API** (theo tài liệu chính thức [Pricing](https://docs.perplexity.ai/guides/pricing)): đơn giá **theo 1K requests** (không tính thêm token cho Search API). Mỗi lần `search.create` = một request:

\[
\text{USD}_{\mathrm{pplx}} \approx S \times \dfrac{\text{USD\_per\_1K\_search\_requests}}{1000}
\]

**OpenAI Embedding** (khớp `EMBED_EST_COST_PER_1K_TOKENS_USD` trong `app/config.py` – đơn vị USD / **1K tokens**):

\[
\text{USD}_{\mathrm{emb}} = T_{\mathrm{emb}} / 1000 \times \texttt{EMBED\_EST\_COST\_PER\_1K\_TOKENS\_USD}
\]

**OpenAI Chat** (mindmap), với giá mỗi triệu token input/output \(p_{\mathrm{in}}, p_{\mathrm{out}}\):

\[
\text{USD}_{\mathrm{chat}} =
\frac{T_{\mathrm{in}}}{10^6} \times p_{\mathrm{in}} +
\frac{T_{\mathrm{out}}}{10^6} \times p_{\mathrm{out}}
\]

**Tổng ước lượng một lần “full ingest + mindmap topic một tầng”:**

\[
\text{USD}_{\mathrm{total}} \approx
\text{USD}_{\mathrm{pplx}} +
\text{USD}_{\mathrm{fc}} +
\text{USD}_{\mathrm{emb}} +
\text{USD}_{\mathrm{chat}}
\]

### 5.3 Đơn giá tham chiếu (cập nhật định kỳ)

| Nhà cung cấp | SKU / hạng mục | Giá tham chiếu (USD) | Ghi chú |
|--------------|----------------|----------------------|---------|
| **Perplexity** | [Search API](https://docs.perplexity.ai/guides/pricing) | **$5 / 1.000 requests** (điển hình trong docs: raw search) | Code dùng `Perplexity().search.create` → mỗi lần gọi ~**$0,005** nếu áp đúng bảng này. Sonar / chat có bảng token + phí request riêng; **không** dùng trong Stage 1 hiện tại. |
| **Firecrawl** | Credits | **1 credit** / map request; **1 credit** / scrape URL | Giá USD = phụ thuộc **plan** (Free/Hobby/Standard…), xem [firecrawl.dev](https://www.firecrawl.dev/pricing) và dashboard. |
| **OpenAI** | `text-embedding-3-small` | Tham khảo [Pricing](https://platform.openai.com/docs/pricing) | Trong repo: `EMBED_EST_COST_PER_1K_TOKENS_USD` mặc định **0,00002** → **~$0,02 / 1M input tokens** nếu giữ mặc định. |
| **OpenAI** | `gpt-4o-mini` (Chat) | Tham khảo cùng trang pricing: điển hình **~$0,15 / 1M input**, **~$0,60 / 1M output** (Standard) | Dùng cho topic / synthesis Phase 10. |

Mọi số trên có thể thay đổi; **không** coi là cam kết pháp lý.

### 5.4 Ví dụ số (minh hoạ)

**Giả định:** một lần ingest “đầy đủ” cho một domain nhỏ:

- 1 lần Perplexity Search → \(S = 1\).
- 1 map + **40** scrape thành công → 41 credits Firecrawl.
- **150.000** tokens đưa vào embedding (tương đương ~vài chục–trăm chunk tùy độ dài).
- Mindmap: **6** cluster top-level, mỗi cluster **1** request Chat; ước mỗi request **~900** input + **~120** output tokens (system + user có 5 excerpt × ~600 ký tự + JSON trả lại).

**Ước lượng:**

| Thành phần | Tính toán gọn | USD ~ |
|------------|----------------|-------|
| Perplexity | \(1 \times 5 / 1000\) | **0,005** |
| Firecrawl | 41 credits → *phụ thuộc gói* (vd. gói $19 / 3000 cr ≈ **$0,0063**/cr) | **~0,26** |
| Embedding | \(150000/1000 \times 0,00002\) hoặc đúng theo bảng OpenAI | **~0,003** |
| Chat topic | \(6 \times (900/10^6 \times 0,15 + 120/10^6 \times 0,6)\) | **~0,0013** |
| **Tổng gợi ý** | | **~0,27–0,35** + sai số Firecrawl theo plan |

Nếu **bật** `no_search=true` và chỉ dùng seed thủ công → **bỏ** dòng Perplexity. Nếu incremental chỉ **5** URL mới → Firecrawl scrape coi **~5** credits (+ map nếu chạy lại map) thay vì 40.

### 5.5 Biến môi trường và code giới hạn / ước lượng

Trong `app/config.py` (và `.env`):

| Biến | Ý nghĩa liên quan chi phí |
|------|---------------------------|
| `PERPLEXITY_MAX_SEARCH_RESULTS` | Không đổi giá theo “số kết quả” trong Search API theo kiểu tính tiền từng URL; chỉ giới hạn payload. |
| `FIRECRAWL_MAP_LIMIT`, `MAX_SCRAPE_URLS_PER_RUN` | Trần **N** scrape → trần credits map+scrape. |
| `MAX_EMBEDDING_TOKENS_PER_RUN` | Trần token embed / run (bảo vệ ngân sách). |
| `EMBED_EST_COST_PER_1K_TOKENS_USD` | Hệ số ước lượng USD cho báo cáo nội bộ (khớp pricing OpenAI khi cập nhật). |
| `SCRAPE_EST_COST_PER_URL_USD` | Ước lượng **USD/URL** cho dry-run / báo cáo (không thay Firecrawl billing). |
| `MINDMAP_MAX_LLM_CALLS_PER_RUN` | Trần số lần gọi Chat mindmap. |
| `MINDMAP_MAX_TOKENS_PER_RUN` | Trần token Chat tích lũy (khi pipeline có đo). |
| `MINDMAP_LLM_MODEL` | Đổi model → đổi \(p_{\mathrm{in}}, p_{\mathrm{out}}\). |

### 5.6 Chi phí coi như không (local)

- Chuẩn hoá text, chunking, lưu artifact `out/…`.
- Giảm chiều UMAP, HDBSCAN, cây `clusters_tree_raw.json`.
- NER spaCy (model tải về máy).

### 5.7 Benchmark framework (để so provider crawl)

Dùng cùng 1 tập URL, cùng timeout, cùng chunk config để benchmark công bằng.

**Dataset benchmark khuyến nghị:**

- Domain: `fptsoftware.com`
- URL mẫu: 30 URL đầu tiên từ map
- Chạy 3 vòng, lấy median
- Giữ nguyên downstream (`cleaner -> chunker -> embedding`) để đo chất lượng thực dùng cho RAG

**KPI nên đo:**

| KPI | Công thức | Ý nghĩa |
|-----|-----------|---------|
| `crawl_success_rate` | `success_url_count / requested_url_count` | Độ ổn định crawl |
| `cost_per_100_urls_usd` | `total_cost_usd * 100 / requested_url_count` | Dễ so theo quy mô |
| `avg_latency_per_url_s` | `total_duration_s / success_url_count` | Tốc độ |
| `avg_words_per_chunk` | `sum(word_count) / chunk_count` | Độ đậm nội dung |
| `usable_chunk_ratio` | `vector_count / chunk_count` | Tỷ lệ chunk vào được pipeline embedding + mindmap |
| `noise_ratio_top_cluster` | từ `clusters_top.metrics.noise_ratio` | Chất lượng semantic grouping |

**Bảng benchmark (điền theo run thực tế):**

| Provider | Mode | Requested URLs | Success URLs | Chunk count | Vector count | Usable chunk ratio | Noise ratio | Latency/url (s) | Cost/run (USD) | Cost/100 URLs (USD) | Ghi chú |
|----------|------|----------------|--------------|-------------|--------------|--------------------|-------------|-----------------|----------------|----------------------|--------|
| Firecrawl | current (`map + scrape`) | 30 | 30 (ví dụ) | 74 | 57 | 0.77 | 0.00 | TBD | TBD | TBD | Baseline hiện tại |
| Jina Reader | simple | 30 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | URL->markdown nhanh, token thấp |
| Jina Reader | detail | 30 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | Snippet dài hơn, token cao hơn |
| Apify | crawler actor | 30 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | Mạnh anti-bot, setup phức tạp hơn |
| ZenRows | scrape API | 30 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | Mạnh bypass, giá tùy render mode |

**Baseline đã có từ artifact hiện tại (`fptsoftware-com`):**

- `chunk_count = 74` (từ `out/fptsoftware-com/chunks.jsonl`)
- `vector_count = 57` (từ `clusters_top.json`)
- `cluster_count = 6`, `noise_ratio = 0.0` (từ `clusters_top.json`)
- `usable_chunk_ratio = 57/74 = 0.77`

> Khuyến nghị quyết định provider theo thứ tự ưu tiên:  
> (1) `cost_per_100_urls_usd`, (2) `usable_chunk_ratio`, (3) `noise_ratio_top_cluster`, (4) `latency/url`.

---

## 6. Bảo mật

- **KHÔNG** commit `.env` lên git – đã có trong `.gitignore`.
- Khi deploy: dùng secret manager (AWS Secrets Manager, Doppler, 1Password CLI...).
- Rotate key định kỳ để giảm rủi ro lộ key.
- Khi share repo: dùng `.env.example` làm template, **không có giá trị thật**.

---

## 7. Kiểm tra nhanh API key

Một script `examples/check_keys.py` (sẽ thêm sau) giúp ping 2 service:

```bash
python examples/check_keys.py
```

Output mong muốn:
```
[OK]  Perplexity   – search.create returned 10 results in 1.2s
[OK]  FireCrawl    – /map?url=example.com returned 12 links in 0.8s
```
