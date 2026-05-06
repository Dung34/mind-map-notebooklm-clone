# Parallel Mindmap Flow Design (Legacy + Business Strategy)

Tai lieu nay de xuat cach tao luong mindmap song song an toan, giu nguyen baseline cu va mo rong luong moi theo huong phan tich chien luoc.

---

## 1) Muc tieu

- Giu nguyen luong `legacy` dang on dinh de regression.
- Them luong moi `business_strategy` khong lam vo contract hien tai.
- Cho phep A/B test chat luong va chi phi giua 2 luong.
- Dat nen tang de chuyen doi dan sang luong moi khi KPI dat nguong.

---

## 2) Nguyen tac thiet ke

1. **Mode o boundary, khong chen sau**  
   Chi chon mode o diem vao (CLI/API), khong rai `if mode` khap module core.

2. **Share toi da, fork toi thieu**  
   Share cac thanh phan on dinh (vector loader, clustering, tree infra).  
   Fork cac thanh phan mang tinh nghiep vu (framework selector, priority, output contract).

3. **Artifact tach biet ro rang**  
   Tuyet doi khong ghi de output legacy.

4. **Schema versioned**  
   Moi output flow moi phai co `schema_version` + `flow_mode`.

---

## 3) Hien trang va quyet dinh

### 3.1 Da co trong code

- Ingest + vector: `app/main.py`, `app/pipeline.py`, `app/embed/*`, `app/vector/*`
- Mindmap stage (script-based):
  - `app/mindmap/vector_loader.py`
  - `app/mindmap/clusterer.py`
  - `app/mindmap/reducer.py`
  - `app/mindmap/topic_extractor.py`
  - `app/mindmap/topics_stage.py`
  - `app/mindmap/recursive_cluster.py`
  - `app/mindmap/ner.py`
  - `app/mindmap/tree_builder.py`

### 3.2 Chua co (docs-only)

- `_actionPriority` / `_actionReason` utility runtime
- API mindmap build/read chinh thuc
- OPML exporter runtime

### 3.3 Quyết định thiet ke

- Khong sua hanh vi luong `legacy`.
- Tao orchestrator moi cho mode `business_strategy`.
- Giu API ingest hien tai; bo sung entrypoint rieng cho mindmap build.

---

## 4) Kien truc de xuat

## 4.1 Flow mode

- `legacy`: hanh vi cu, output cu, de regression.
- `business_strategy`: them intent/framework + action priority + output schema mo rong.

## 4.2 Module mapping (Share vs Fork)

### Share (giu nguyen)
- `app/mindmap/vector_loader.py`
- `app/mindmap/clusterer.py`
- `app/mindmap/reducer.py`
- `app/mindmap/recursive_cluster.py`
- `app/mindmap/ner.py`

### Fork nhe / adapter
- `topic` layer:
  - Legacy: dung logic cu
  - Business: adapter them framework-aware prompt rules neu can
- `tree` layer:
  - Legacy: builder cu
  - Business: post-processor bo sung `_actionPriority`, `_actionReason`, `framework_tag`

### New modules (de xuat)
- `app/mindmap/flow_runner.py`  
  Interface chung chay luong theo mode.
- `app/mindmap/modes/legacy_flow.py`
- `app/mindmap/modes/business_strategy_flow.py`
- `app/mindmap/business/action_priority.py`  
  Rule utility xep `High|Normal`.
- `app/mindmap/business/framework_selector.py`  
  Map query -> framework (rule-based ban dau).
- `app/mindmap/contracts.py`  
  Schema helpers + validate + version tags.

---

## 5) Entry points de xuat

## 5.1 CLI (lam truoc, roi API)

- Them script:
  - `examples/check_mindmap_parallel.py`
- Tham so:
  - `--mode legacy|business_strategy`
  - `--query "..."`
  - `--scope website|notebooklm_id|run_id`

## 5.2 API (lam sau khi CLI on)

- `POST /mindmap/build`
  - body: `mode`, `query`, scope params
- `GET /mindmap/{id}`
  - metadata + status
- `GET /mindmap/{id}/tree`
  - tra JSON tree theo mode/schema

Note: API moi la boundary mode. Cac module core khong can biet endpoint.

---

## 6) Input / Output contract

## 6.1 Input chung

- Scope xac dinh tap chunk/vector:
  - theo `website`
  - hoac `notebooklm_id`
  - hoac `ingest_run_id`
- `query`:
  - neu rong -> dung default business query
  - neu co -> uu tien query user

## 6.2 Output metadata bat buoc

Moi artifact mindmap phai co:
- `flow_mode`: `legacy` | `business_strategy`
- `schema_version`: so nguyen
- `pipeline_version`
- `generated_at`

## 6.3 Node contract cho business mode

Ngoai cac truong co san (`title`, `summary`, `children`...), bo sung:
- `swot_category`
- `funnel_stage`
- `ms_notes`
- `_actionPriority`
- `_actionReason`
- `framework_tag`

Fallback:
- `swot_category = N_A`
- `funnel_stage = Unknown`
- `ms_notes = ""`
- `_actionPriority = Normal`
- `_actionReason = ""`

---

## 7) Artifact convention (khong de len legacy)

De xuat folder:

- `out/<slug>/mindmap/legacy/<run_id>/...`
- `out/<slug>/mindmap/business_strategy/<run_id>/...`

File toi thieu moi run:
- `manifest.json`
- `clusters_top.json`
- `topics.json`
- `clusters_tree_raw.json`
- `entities.json`
- `mindmap.json`

Trong `manifest.json` bat buoc co:
- `flow_mode`
- `schema_version`
- `input.query`
- `stats` (node_count, depth, high_priority_count, duration_seconds, token_est, cost_est)

---

## 8) KPI A/B va dieu kien cutover

## 8.1 KPI theo mode

- `schema_valid_rate`
- `% node co swot + funnel hop le`
- `% node High duoc chap nhan dung`
- `time_to_first_useful_insight`
- `duration/run`, `token/run`, `cost/run`

## 8.2 Nguong de chuyen doi

Chi xem xet cho `business_strategy` lam default khi:
- `schema_valid_rate >= 99%`
- `high_priority_acceptance` cao hon legacy tren tap test chuan
- chi phi tang trong nguong chap nhan
- khong co regression nghiem trong ve do ro/cau truc tree

---

## 9) Ke hoach trien khai de xuat (2 sprint)

## Sprint 1 (uu tien an toan + quan sat)

1. Tao `flow_runner.py` + 2 mode flow.
2. Bo sung `framework_selector.py` (rule-based).
3. Bo sung `action_priority.py` (rule-based).
4. Tao script `check_mindmap_parallel.py`.
5. Chot artifact convention + manifest mode-aware.

**Done**
- Chay duoc 2 mode tu cung 1 scope.
- Artifact tach biet, khong ghi de legacy.
- Co report KPI toi thieu theo mode.

## Sprint 2 (API + hardening)

1. Mo endpoint `/mindmap/build` mode-aware.
2. Bo sung validation contract trong `contracts.py`.
3. Viet regression tests:
   - legacy khong doi hanh vi
   - business node du key/fallback dung
4. Benchmark bo query chuan (Q01-Q10).

**Done**
- API build tree cho 2 mode.
- Dashboard/summary A/B co so lieu de quyet dinh.

---

## 10) Risk chinh va giam thieu

- **Risk: mode leak vao core module**  
  -> Bat buoc mode switch o orchestrator boundary.

- **Risk: overwrite artifact cu**  
  -> Bat buoc output path theo mode/run_id.

- **Risk: contract drift giua mode**  
  -> `schema_version` + validation truoc khi ghi artifact.

- **Risk: chi phi tang do them business logic**  
  -> Rule-based first, theo doi token/cost theo mode.

---

## 11) Ket luan

Huong dung cho du an hien tai la:
- Giu `legacy` lam baseline regression.
- Them `business_strategy` song song, do KPI thuc te.
- Chi cutover khi dat nguong chat luong/chi phi.

Day la cach mo rong an toan nhat, tranh refactor lon som, va toi uu ROI theo tung sprint.
