## Mindmap Workflow API (End-to-End)

Tài liệu này mô tả API orchestration chạy full pipeline:

`companyName -> seedUrl -> map -> scrape -> chunking -> embedding -> clusters -> topics -> framework analyses -> mindmap`

---

### 1) API Design

Khuyến nghị triển khai **async job API** để tránh timeout:

- `POST /mindmap/workflows/run`
- `GET /mindmap/workflows/jobs/{jobId}`
- `GET /mindmap/workflows/jobs/{jobId}/artifacts`

Lý do:

- workflow nhiều bước, có thể chạy vài phút.
- dễ retry theo stage.
- phù hợp UI hiển thị progress.

---

### 2) POST /mindmap/workflows/run

Khởi chạy một workflow mới.

#### Request body (rút gọn)

```json
{
  "companyName": "FPT Software",
  "seedUrl": "https://fptsoftware.com",
  "scope": {
    "notebooklm_id": "nb_default"
  },
  "discovery": {
    "maxUrls": 50,
    "includeSubdomains": false
  },
  "scrape": {
    "concurrency": 5,
    "waitMs": 1500,
    "onlyMainContent": true
  },
  "chunking": {
    "maxWords": 400,
    "minWords": 15,
    "overlapSentences": 2
  },
  "embedding": {
    "model": "text-embedding-3-small",
    "batchSize": 32
  },
  "mindmap": {
    "retrievalMode": "overview",
    "topKFinal": 12,
    "overviewRepRatio": 0.7,
    "runFrameworkAnalyses": true,
    "generateMindmap": true,
    "outputMarkdown": true
  },
  "idempotencyKey": "optional-client-key-123"
}
```

#### Response

```json
{
  "ok": true,
  "jobId": "wf_2026-05-07T06-30-00Z_a1b2c3d4",
  "status": "queued",
  "runId": "mm_2026-05-07T06-30-00Z_93e1e44d"
}
```

---

### 3) GET /mindmap/workflows/jobs/{jobId}

Lấy trạng thái và tiến độ.

#### Response (running)

```json
{
  "ok": true,
  "jobId": "wf_...",
  "status": "running",
  "currentStage": "framework_analyses",
  "progress": {
    "percent": 72,
    "completedStages": [
      "map",
      "scrape",
      "chunking",
      "embedding",
      "clusters",
      "topics",
      "retrieval_context"
    ]
  },
  "runId": "mm_..."
}
```

#### Response (succeeded)

```json
{
  "ok": true,
  "jobId": "wf_...",
  "status": "succeeded",
  "currentStage": "done",
  "runId": "mm_...",
  "metrics": {
    "urlCount": 45,
    "chunkCount": 312,
    "clusterCount": 6,
    "selectedContextCount": 12
  }
}
```

#### Response (failed)

```json
{
  "ok": false,
  "jobId": "wf_...",
  "status": "failed",
  "currentStage": "mindmap_generation",
  "error": {
    "code": "GENERATION_VALIDATION_FAILED",
    "message": "root must have 4-6 theme children",
    "retryable": true
  },
  "runId": "mm_..."
}
```

---

### 4) GET /mindmap/workflows/jobs/{jobId}/artifacts

Trả danh sách artifact output của run.

```json
{
  "ok": true,
  "jobId": "wf_...",
  "runId": "mm_...",
  "artifacts": {
    "map": "out/fptsoftware-com/map.json",
    "scrapedPages": "out/fptsoftware-com/scraped_pages.jsonl",
    "chunks": "out/fptsoftware-com/chunks.jsonl",
    "embeddings": "out/fptsoftware-com/embeddings.jsonl",
    "clustersTop": "out/fptsoftware-com/mindmap/mm_.../clusters_top.json",
    "topics": "out/fptsoftware-com/mindmap/mm_.../topics.json",
    "retrievalContext": "out/fptsoftware-com/mindmap/mm_.../retrieval_context.json",
    "frameworkAnalysesOverview": "out/fptsoftware-com/mindmap/mm_.../framework_analyses_overview.json",
    "mindmapGenerated": "out/fptsoftware-com/mindmap/mm_.../mindmap_generated.json",
    "mindmapMarkdown": "out/fptsoftware-com/mindmap/mm_.../mindmap_generated.md"
  }
}
```

---

### 5) Stage Execution Contract

Các stage theo thứ tự chuẩn:

1. `map`
2. `scrape`
3. `chunking`
4. `embedding`
5. `clusters`
6. `topics`
7. `retrieval_context` (overview/query mode)
8. `framework_analyses` (optional theo flag)
9. `mindmap_generation` (optional theo flag)
10. `mindmap_markdown` (optional theo flag)

Mỗi stage nên log:

- `startedAt`, `endedAt`, `durationMs`
- `status`
- `inputRef`, `outputRef`
- `error` nếu fail

---

### 6) Validation Rules (khuyến nghị)

- `seedUrl` phải là URL hợp lệ và thuộc HTTP/HTTPS.
- `overviewRepRatio` trong `[0, 1]`.
- `topKFinal` > 0.
- Nếu `runFrameworkAnalyses=false` thì `generateMindmap` chỉ được dùng flow `retrieval_context`.
- Nếu `generateMindmap=true` và có `framework_analyses_overview.json`, ưu tiên synthesis từ analyses.

---

### 7) Idempotency & Retry

- Hỗ trợ `idempotencyKey` để tránh chạy trùng workflow.
- Retry theo stage (không chạy lại từ đầu) cho lỗi network/provider.
- Lưu trạng thái job bền vững (DB hoặc file-state) để resume.

---

### 8) Security & Quotas

- API key/auth bắt buộc cho endpoint run.
- Rate limit theo tenant/user.
- Quota:
  - max URLs/run
  - max chunks/run
  - max LLM calls/run
  - max token budget/run

---

### 9) Mapping với code hiện tại

- Query retrieval: `app/mindmap/query_layer/orchestrator.py`
- Overview context: `app/mindmap/query_layer/overview_context.py`
- Framework analyses: `app/mindmap/query_layer/framework_batch_analysis.py`
- Mindmap synthesis: `app/mindmap/generation_stage4.py`

API orchestration mới chỉ cần wrap tuần tự các hàm hiện có.

