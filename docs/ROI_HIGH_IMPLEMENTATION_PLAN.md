# Ke hoach trien khai ROI cao cho Mindmap phan tich doanh nghiep

Tai lieu nay mo ta lo trinh trien khai **ROI cao** cho he thong mindmap, duoc toi uu theo nguyen tac:
- Lam it nhung tang gia tri nhin thay ngay.
- Han che refactor lon khi chua co du lieu xac nhan.
- Bui duoc tren codebase hien tai (ingest -> clean -> chunk -> artifact) de trien khai nhanh.

---

## 1) Muc tieu kinh doanh

- Tang "wow value" cua output mindmap cho user business.
- Nang kha nang hanh dong: moi nhanh co y nghia chien luoc ro rang.
- Kiem soat chi phi token/compute theo tung run.
- Tao du lieu do luong de quyet dinh buoc tiep theo (mo rong hay giu nhe).

---

## 2) Nguyen tac uu tien ROI

1. **Output-first**: uu tien nang cap chat luong output truoc khi them he thong phuc tap.
2. **Rule + schema truoc, AI nang sau**: dung schema chat + heuristic nhe truoc khi bat LLM nang.
3. **Do luong moi buoc**: moi thay doi phai co KPI de quyet dinh giu/bo.
4. **Pilot co gioi han**: deep analysis chi chay tren mau nho, khong scale ngay.

---

## 3) Roadmap ROI cao theo 3 giai doan

## Giai doan A - Quick Wins (Tuan 1, ROI cao nhat)

### A1. Harden + validate schema node M&S (da implement)
- Trang thai hien tai: da co 3 truong trong code path mindmap:
  - `swot_category`
  - `funnel_stage`
  - `ms_notes`
- Viec can lam trong giai doan A:
  - Khoa chat contract output (schema docs + parser behavior)
  - Bo sung/ra soat regression test de dam bao 100% node luon co du key
  - Theo doi ty le enum hop le va fallback rate qua tung run
  - Xac nhan fallback an toan (`N_A`, `Unknown`, `""`) van hoat dong on dinh

**Gia tri mang lai**
- User thay ngay duoc "insight chien luoc", khong chi la tom tat noi dung.
- Giam loi parser va giam output vo nghia.
- Tranh hieu nham "da co tinh nang nhung chua co bao chung on dinh".

### A2. Them Action Priority rule-based
- Gan metadata:
  - `_actionPriority`: `High | Normal`
  - `_actionReason`: ly do ngan gon
- Rule de xep `High`:
  - Match keyword rui ro/chot sale
  - Hoac ket hop (`Threat` + `Consideration`)...

**Gia tri mang lai**
- Business team co ngay danh sach "nen hanh dong truoc".
- Tang kha nang ung dung thuc te ma chua can AI phuc tap.

### A3. Bo query default nhung van mo cho user nhap
- Query mac dinh de tranh man hinh trong/khong biet bat dau.
- Neu user nhap query rieng thi uu tien query user.

**Gia tri mang lai**
- Tang completion rate lan dau.
- Giam friction cho user moi.

---

## Giai doan B - Tang do sau co kiem soat (Tuan 2)

### B1. Hybrid retrieval nhe de nang chat luong chunk
- Ket hop semantic top-K + entity/keyword match.
- Rerank de chon tap chunk phu hop voi framework (SWOT/Compare/Root cause...).

**Gia tri mang lai**
- Mindmap giam lan man, tang do dung context.
- Tang do tin cay truoc khi mo rong model.

### B2. Intent -> framework selector (ban dau rule-based)
- Input query -> map framework:
  - SWOT / Deep Dive / Compare / Root Cause / Pros-Cons
- Luu framework trong metadata run de theo doi.

**Gia tri mang lai**
- Cau truc mindmap hop nhu cau user hon.
- De danh gia A/B va tinh chinh prompt.

---

## Giai doan C - Deep Analysis pilot (Tuan 3, chi neu can)

### C1. Pilot NER nang cao tren mau nho
- Thu nghiem NER bang LLM/model nhe tren sample dai dien.
- Dat tran token/cost per run.
- So sanh voi baseline rule/spaCy.

**Quyet dinh sau pilot**
- Tiep tuc LLM-NER
- Hoac hybrid
- Hoac quay ve rule/spaCy neu ROI thap

### C2. Hoan lai refactor lon (Guided Tree / Graph DB)
- Chi lam khi metric va feedback cho thay can thiet ro rang.
- Tranh "xay som" he thong nang truoc khi co bang chung.

---

## 4) KPI bat buoc theo doi

- `% node co swot_category + funnel_stage hop le`
- `% node High duoc user/business xac nhan dung`
- `Avg time to first useful insight`
- `Token/run` va `Cost/run`
- `% run thanh cong khong can xu ly thu cong`

---

## 5) Ke hoach thuc thi theo sprint

### Sprint 1 (5 ngay)
- Hoan thanh A1 (harden/validate) + A2 + A3
- Them test regression schema node
- Chot bo query test chuan (Q01-Q10)

**Done khi**
- 100% node co du key M&S
- Khong crash khi enum sai
- Co action priority cho moi node

### Sprint 2 (5 ngay)
- Hoan thanh B1 + B2
- Bat dashboard/log summary cho retrieval quality
- Chay benchmark nho tren bo query test

**Done khi**
- Tang do phu hop chunk (manual check) so voi baseline
- Giam output "chung chung", tang so node co insight hanh dong

---

## 6) Thu tu uu tien neu tai nguyen han che

1. A1 Harden/Validate Schema M&S (da co, can chot on dinh)
2. A2 Action Priority
3. A3 Default query + user override
4. B2 Intent selector (rule)
5. B1 Hybrid retrieval + rerank
6. C1 NER pilot
7. C2 Guided Tree / Graph DB

---

## 7) Risk chinh va giam thieu

- **Schema output khong on dinh**
  - Giam thieu: strict schema + normalize enum + fallback.
- **Chi phi token tang nhanh**
  - Giam thieu: token budget/run + pilot mau nho + canh bao som.
- **Tree dep ky thuat nhung kho dung business**
  - Giam thieu: uu tien KPI "actionability", khong chay theo do phuc tap.

---

## 8) Ket luan

Lo trinh ROI cao nhat cho du an hien tai la:
- **Lam nhanh va chac o tang output + metadata (A)**
- **Nang retrieval va framework selector co kiem soat (B)**
- **Chi mo rong NER/refactor lon khi metric va feedback xac nhan (C)**

Cach di nay giup tang gia tri san pham som, giam rui ro ky thuat, va van giu duoc duong mo rong ve sau.
