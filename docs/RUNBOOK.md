# Runbook - One Flow (Phase 9)

Tài liệu này là luồng vận hành duy nhất cho hệ thống ingest production.

## 1) Full flow `/ingest`

`POST /ingest` hiện chạy full end-to-end:

1. Seed + discover URL
2. Scrape (có skip scrape cho URL known nếu có cache)
3. Clean + chunk
4. Delta + manifest artifacts
5. Embedding (`text-embedding-3-small`)
6. Upsert vector vào pgvector (`VECTOR_TABLE`)
7. Cập nhật trạng thái vào `ingest_runs`
8. Theo dõi bằng `GET /jobs/{run_id}`

## 2) Start local stack

```powershell
docker compose up -d
docker compose ps
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

## 3) API commands (single workflow)

- **Dry-run (không chạy ingest thật):**

```bash
curl -X POST http://127.0.0.1:8000/ingest -H "Content-Type: application/json" -d "{\"website\":\"fptsoftware.com\",\"no_search\":true,\"limit\":5,\"dry_run\":true}"
```

- **Run ingest thật (full flow):**

```bash
curl -X POST http://127.0.0.1:8000/ingest -H "Content-Type: application/json" -d "{\"website\":\"fptsoftware.com\",\"no_search\":true,\"limit\":5}"
```

- **Check trạng thái run:**

```bash
curl http://127.0.0.1:8000/jobs/<run_id>
```

- **Reindex (chỉ embed + upsert từ cache chunks):**

```bash
curl -X POST http://127.0.0.1:8000/ingest/reindex -H "Content-Type: application/json" -d "{\"website\":\"fptsoftware.com\",\"limit\":0}"
```

## 4) Inputs tối thiểu

- Dùng company:

```json
{"company":"FPT Software"}
```

- Dùng website:

```json
{"website":"fptsoftware.com","no_search":true}
```

## 5) Outputs cần kiểm tra

- API job status: `queued/running/success/failed`
- Artifacts: `out/<slug>/stats.json`, `delta.json`, `manifest.json`, `embeddings.jsonl`
- DB schema nền sau migration:
  - `ingest_runs`
  - `page_index`
  - `chunk_index`
  - `rag_chunks` (`VECTOR_TABLE` mặc định, có `notebooklm_id` + `chunk_text`)

## 6) Guardrails + error contracts

- `MAX_SCRAPE_URLS_PER_RUN`
- `MAX_EMBEDDING_TOKENS_PER_RUN`
- Lỗi chuẩn:
  - `validation_error`
  - `quota_exceeded`
  - `job_not_found`
  - `upstream_error`

## 7) Rollback checklist

1. Stop API process.
2. Restore previous branch/commit.
3. Restart API and check `GET /health`.
4. Chạy lại 1 request `dry_run` để verify contract.

---

## 8) Phase 10 – MindMap Builder

> Đặc tả: [`MINDMAP.md`](MINDMAP.md). Phase này build mindmap từ vectors đã upsert ở Phase 9.

### 8.1 Flow tổng quát

1. Chạy ingest Phase 9 cho website (`POST /ingest`).
2. Khi `GET /jobs/{run_id}` báo `success`, mọi vectors đã có trong `rag_chunks` với `notebooklm_id` tương ứng.
3. `POST /mindmap/build` để dựng mindmap.
4. `GET /mindmap/{mindmap_run_id}` để theo dõi.
5. Tải `mindmap.opml` qua `GET /mindmap/{mindmap_run_id}/opml`.
6. Import file `.opml` vào XMind / Logseq / MarkMap để render.

### 8.2 API commands

- **Dry-run (estimate, không gọi LLM):**

```bash
curl -X POST http://127.0.0.1:8000/mindmap/build \
  -H "Content-Type: application/json" \
  -d "{\"notebooklm_id\":\"nb_fpt_001\",\"scope_mode\":\"by_website\",\"website\":\"fptsoftware.com\",\"dry_run\":true}"
```

- **Build mindmap thật:**

```bash
curl -X POST http://127.0.0.1:8000/mindmap/build \
  -H "Content-Type: application/json" \
  -d "{\"notebooklm_id\":\"nb_fpt_001\",\"scope_mode\":\"by_website\",\"website\":\"fptsoftware.com\"}"
```

- **Theo dõi build:**

```bash
curl http://127.0.0.1:8000/mindmap/<mindmap_run_id>
```

- **Lấy JSON tree:**

```bash
curl http://127.0.0.1:8000/mindmap/<mindmap_run_id>/tree
```

- **Tải OPML (render được):**

```bash
curl -o mindmap.opml http://127.0.0.1:8000/mindmap/<mindmap_run_id>/opml
```

### 8.3 Inputs scope

| `scope_mode`     | Field bắt buộc                     | Khi nào dùng                                   |
| ---------------- | ---------------------------------- | ---------------------------------------------- |
| `by_website`     | `notebooklm_id`, `website`         | Build mindmap mới nhất cho domain (default)    |
| `by_run_id`      | `notebooklm_id`, `run_id`          | Build mindmap reproducible theo 1 ingest run   |
| `by_chunk_ids`   | `notebooklm_id`, `chunk_ids[]`     | Debug / build cho subset thủ công              |

### 8.4 Outputs cần kiểm tra

- DB: bảng `mindmap_runs` (`status=success`, `cluster_count > 0`, `leaf_count > 0`).
- Artifacts dưới `out/<slug>/mindmap/<mindmap_run_id>/`:
  - `mindmap.json` – tree chính.
  - `mindmap.opml` – render được (mở thử trong XMind / Logseq).
  - `manifest.json` – params + stats.
  - `topics.json`, `entities.json` – debug.

### 8.5 Guardrails + error contracts (mindmap)

- `MINDMAP_MAX_VECTORS_PER_RUN` (default `10000`)
- `MINDMAP_MAX_LLM_CALLS_PER_RUN` (default `200`)
- `MINDMAP_MAX_TOKENS_PER_RUN` (default `200000`)
- Bắt buộc filter scope: `notebooklm_id + is_active=true`
- Lỗi chuẩn:
  - `validation_error`
  - `not_found_vectors`
  - `quota_exceeded`
  - `clustering_failed`
  - `upstream_error`

### 8.6 Quality smoke check

Trước khi đóng task build:

- [ ] `noise_ratio < 0.5` (xem `manifest.json`).
- [ ] `cluster_count` không vượt cảnh báo (default `MAX_CLUSTERS_WARN=50`).
- [ ] Mỗi leaf có `chunk_ids` không rỗng và tồn tại trong `rag_chunks`.
- [ ] Mọi record mindmap đều thuộc đúng `notebooklm_id` đã truyền vào request.
- [ ] OPML mở được trên XMind/Logseq, hiển thị 3 cấp depth.

### 8.7 Rollback (mindmap)

1. Mindmap không ảnh hưởng vectors – an toàn rebuild bất cứ lúc nào.
2. Nếu build lỗi giữa chừng, không cần rollback DB; chỉ cần xoá thư mục `out/<slug>/mindmap/<mindmap_run_id>/` và row `mindmap_runs` tương ứng.
3. Nếu LLM provider quota cạn: bật `MINDMAP_SKIP_SYNTHESIS=true`, build lại để có ít nhất topic + tree (description rỗng).

