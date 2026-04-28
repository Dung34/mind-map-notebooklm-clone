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
- DB metadata: bảng `ingest_runs`
- DB vectors: bảng `VECTOR_TABLE` (mặc định `rag_chunks`)

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

