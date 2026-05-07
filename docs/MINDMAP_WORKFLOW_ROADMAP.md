## Mindmap Workflow Roadmap

Roadmap triển khai spec end-to-end:

`companyName -> seedUrl -> map -> scrape -> chunking -> embedding -> clusters -> topics -> framework analyses -> mindmap`

---

### Goal

- [ ] Có 1 API chạy full workflow end-to-end
- [ ] Đầu ra ổn định, đúng schema, có retry/resume
- [ ] Kiểm soát được chất lượng + chi phí + quan sát vận hành

---

## Phase 0 — Freeze Spec (1–2 ngày)

### Deliverables

- [ ] Chốt flow chuẩn và tên stage chính thức
- [ ] Chốt contract input/output mỗi stage + schema version
- [ ] Chốt quality gates (mindmap structure, framework schema, retry policy)
- [ ] Chốt cost guardrails (max URLs, max LLM calls, max tokens/run)

### Acceptance Criteria

- [ ] Có tài liệu flow + contract được sign-off
- [ ] Có danh sách error codes chuẩn theo stage

---

## Phase 1 — Orchestrator API (3–5 ngày)

### Deliverables

- [ ] `POST /mindmap/workflows/run`
- [ ] `GET /mindmap/workflows/jobs/{jobId}`
- [ ] `GET /mindmap/workflows/jobs/{jobId}/artifacts`
- [ ] Validate payload theo `docs/schemas/mindmap_workflow_run.schema.json`
- [ ] Lưu trạng thái job (`queued/running/succeeded/failed`)

### Acceptance Criteria

- [ ] 1 API call tạo được `jobId`
- [ ] Poll status thấy tiến độ stage
- [ ] Artifacts trả đúng path/run_id

---

## Phase 2 — Stage Hardening (4–6 ngày)

### Deliverables

- [ ] Retry có kiểm soát cho stage network/LLM
- [ ] Checkpoint theo stage (resume không chạy lại từ đầu)
- [ ] Idempotency theo `idempotencyKey`
- [ ] Chuẩn hóa lỗi (`*_FAILED`, `*_VALIDATION_FAILED`, ...)

### Acceptance Criteria

- [ ] Fail ở stage giữa chừng có thể resume đúng stage
- [ ] Re-run cùng idempotency key không tạo job trùng

---

## Phase 3 — Output Quality Control (4–6 ngày)

### Deliverables

- [ ] Siết schema cho `framework_analyses_overview.json`
- [ ] Auto-repair 1 vòng khi framework output sai schema
- [ ] Siết validate stage4:
  - [ ] root 4–6 theme
  - [ ] theme 2–4 insight
  - [ ] insight 1–3 action
  - [ ] action children = []
- [ ] Rule phát hiện generic/duplicate themes

### Acceptance Criteria

- [ ] Tỉ lệ pass schema framework >= 95%
- [ ] Tỉ lệ pass stage4 strict validate >= 90%
- [ ] Mindmap không còn lỗi cấu trúc

---

## Phase 4 — Cost & Performance Optimization (3–5 ngày)

### Deliverables

- [ ] Cache kết quả framework analyses theo cluster fingerprint
- [ ] Token budgeting + truncate policy theo stage
- [ ] Parallelization hợp lý theo cluster (kèm provider rate-limit)
- [ ] Báo cáo cost per run

### Acceptance Criteria

- [ ] Giảm chi phí >= 30% so với baseline
- [ ] Thời gian end-to-end giảm đáng kể ở cùng dữ liệu

---

## Phase 5 — Observability & Ops (2–4 ngày)

### Deliverables

- [ ] Log chuẩn theo stage (`startedAt`, `endedAt`, `durationMs`, `status`)
- [ ] Metrics: latency, token usage, fail rate, retry count
- [ ] Audit trail: run_id, model, prompt version, schema version
- [ ] Cảnh báo khi fail rate/cost vượt ngưỡng

### Acceptance Criteria

- [ ] Truy vết được đầy đủ 1 run trong < 2 phút
- [ ] Có dashboard tối thiểu cho team vận hành

---

## Phase 6 — Production Readiness (3–5 ngày)

### Deliverables

- [ ] Auth + rate limit + tenant quota
- [ ] Contract tests cho API
- [ ] Golden tests trên 2–3 website chuẩn
- [ ] Runbook vận hành + rollback plan

### Acceptance Criteria

- [ ] Pilot production pass checklist
- [ ] Không có blocker P0/P1 trước go-live

---

## Milestones

- [ ] **M1 (tuần 1):** API orchestration chạy end-to-end
- [ ] **M2 (tuần 2):** reliability + resume + error model chuẩn
- [ ] **M3 (tuần 3):** quality + cost optimization
- [ ] **M4 (tuần 4):** production pilot

---

## Definition of Done

- [ ] Từ `seedUrl` chạy full workflow bằng 1 API call
- [ ] Sinh đủ artifacts đến `mindmap_generated.json` và `mindmap_generated.md`
- [ ] Mindmap pass strict structure validate
- [ ] Framework analyses pass schema target
- [ ] Có retry/resume/idempotency hoạt động thực tế
- [ ] Có metrics latency/cost/success rate theo run

---

## Backlog ưu tiên ngay (Next 5 Tasks)

- [ ] Tạo `workflow_service` orchestrate toàn bộ stage
- [ ] Thêm endpoint `POST /mindmap/workflows/run`
- [ ] Thêm endpoint `GET /mindmap/workflows/jobs/{jobId}`
- [ ] Gắn stage4 input ưu tiên từ `framework_analyses_overview.json`
- [ ] Bổ sung integration test cho happy path end-to-end

