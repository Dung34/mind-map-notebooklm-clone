# Mindmap Marketing & Sales - Lo trinh trien khai theo ROI

Tai lieu nay tong hop lo trinh trien khai theo nguyen tac **Quick Wins (Lam it - Hieu qua nhieu)** de nang cap output `mindmap.json` theo huong phan tich Marketing + Sales.

## 1) Muc tieu tong quan

- Tang gia tri "wow" cho nguoi dung bang cach bo sung thong tin chien luoc tren moi nhanh.
- Uu tien thay doi nho, tac dong lon, tranh refactor loi qua som.
- Giu on dinh flow hien tai: vector -> cluster -> tree; chi mo rong metadata va output.

---

## 2) Thu tu uu tien trien khai

1. **Giai doan 1 - Low Hanging Fruits (1-2 ngay)**
2. **Giai doan 2 - Deep Analysis (pilot co kiem soat chi phi)**
3. **Giai doan 3 - Structural Refactor (chi khi user feedback xau)**

---

## 3) Giai doan 1 - Low Hanging Fruits

### 3.1. Giai phap 2 - Sua Prompt Synthesizer/Topic Schema (lam ngay)

**Muc tieu**
- Moi cluster co them metadata M&S:
  - `swot_category`
  - `funnel_stage`
- (Khuyen nghi) bo sung them `ms_notes` de tao insight hanh dong.

**Implementation de xuat**
- Mo rong JSON contract tra ve tu LLM theo schema strict:
  - `title`
  - `summary`
  - `swot_category` (`Strength | Weakness | Opportunity | Threat | Mixed | N_A`)
  - `funnel_stage` (`Awareness | Consideration | Decision | Retention | Unknown`)
  - `ms_notes` (chuoi ngan, co the rong)
- Chuan hoa enum o layer parser de tranh sai format.
- Merge metadata vao node tree de `mindmap.json` on dinh schema.

**ROI**
- Nhanh thay doi giao dien du lieu.
- Nguoi dung nhin vao mindmap thay ngay gia tri chien luoc, khong chi la gom nhom chu de.

**Definition of Done**
- 100% node trong `mindmap.json` co day du key:
  - `swot_category`
  - `funnel_stage`
  - `ms_notes`
- Khong crash khi LLM tra ve sai enum; co fallback an toan (`N_A`, `Unknown`, `""`).

### 3.2. Giai phap 4 - OPML Metrics `_actionPriority` (lam cung luc)

**Muc tieu**
- Danh dau nhanh can uu tien xu ly/sales bang rule-based utility nhe.

**Implementation de xuat**
- Tao utility keyword scoring:
  - tap tu khoa tieu cuc/rui ro (vi du: "khieu nai", "delay", "bug", "khong ho tro"...)
  - tap tu khoa chot sale/chuyen doi (vi du: "bao gia", "pricing", "demo", "book call"...)
- Gan metadata:
  - `_actionPriority`: `High | Normal`
  - `_actionReason`: ly do ngan (rule hoac keyword match)
- Ket hop heuristic voi `swot_category` + `funnel_stage`:
  - Vi du: `Threat + Consideration` => uu tien cao.

**ROI**
- Tao ngay danh sach nhanh "can hanh dong" cho business team.
- Gan ket qua phan tich voi hanh dong cu the.

**Definition of Done**
- Moi node co `_actionPriority`.
- Node `High` phai co `_actionReason`.
- Co bo test don vi cho keyword utility.

---

## 4) Giai doan 2 - Deep Analysis (khi can do sau du lieu)

### 4.1. Giai phap 1 - NER cho M&S theo chien luoc pilot

**Muc tieu**
- Nang chat luong entity cho use-case M&S ma van kiem soat duoc chi phi.

**Nguyen tac**
- Khong bat LLM-NER toan bo ngay lap tuc.
- Pilot nho -> do token -> so voi budget -> moi quyet dinh scale.

**Implementation de xuat**
1. Bat thu nghiem `MINDMAP_NER_PROVIDER=llm` cho sample nho.
2. Dung model chi phi thap (goi y: `gpt-4o-mini`) voi prompt JSON strict.
3. Theo doi tong token run va chi phi thuc te.
4. Neu vuot `MINDMAP_MAX_TOKENS_PER_RUN`:
   - Quay lai hybrid: rule/gazetteer + spaCy.
   - Thu thap du lieu de train spaCy nhe cho domain.

**Definition of Done**
- Co bao cao pilot:
  - So leaf/chunk da test
  - Token da dung
  - Chi phi uoc tinh
  - Chat luong entity (manual spot-check)
- Co quyet dinh ro rang:
  - Tiep tuc LLM-NER
  - Hoac hybrid
  - Hoac train spaCy nhe

---

## 5) Giai doan 3 - Structural Refactor (chi khi can)

### 5.1. Giai phap 3 - Guided Tree

**Khi nao moi lam**
- Chi kich hoat neu user feedback rang cay HDBSCAN de quy:
  - qua ngau nhien
  - kho theo luong suy nghi team kinh doanh
  - giam kha nang dung cho decision-making

**Phan viec**
- Thiet ke guided clustering/tree constraints theo business logic.
- Dinh nghia nguyen tac parent-child uu tien theo M&S intent.
- Can nhac viet lai mot phan orchestrator neu can.

**Canh bao pham vi**
- Khoi luong ngang tam refactor loi.
- Khong nen lam truoc khi co du feedback thuc te va metric that.

**Definition of Done**
- Co tieu chi danh gia "tree quality" ro rang.
- Ket qua tree moi tot hon baseline tren bo mau dai dien.

---

## 6) Ke hoach thuc thi de xuat

### Tuan 1 (Quick Wins)
- Hoan thanh schema M&S trong output LLM.
- Bo sung `_actionPriority` utility + metadata.
- Chot output docs mau va test regression.

### Tuan 2 (Neu can)
- Chay pilot LLM-NER tren sample.
- Tong hop chi phi/chat luong va chot huong hybrid/full/offline.

### Tuan 3+ (Chi khi feedback xau)
- Danh gia can thiet Guided Tree.
- Neu can, lap RFC refactor rieng truoc khi code.

---

## 7) Risk va cach giam thieu

- **Risk: schema LLM khong on dinh** -> dung strict JSON schema + normalize enum + fallback.
- **Risk: chi phi token tang** -> limit call/run + token budget + pilot nho.
- **Risk: tree dep ve ky thuat nhung kho dung business** -> chi refactor guided tree khi co feedback va metric.

---

## 8) KPI de do hieu qua

- `% node co swot_category + funnel_stage hop le`
- `% node High priority duoc business team chap nhan la dung`
- `Token/run` va `Cost/run`
- `Muc do hai long cua team kinh doanh voi mindmap output`

---

## 9) Ket luan

Thu tu toi uu de toi da ROI:

1. **Mo rong output LLM cho M&S (SWOT + Funnel + Notes)**
2. **Them `_actionPriority` rule utility**
3. **Pilot LLM-NER co gioi han budget**
4. **Chi refactor Guided Tree khi feedback xau va co du lieu xac nhan**

Huong di nay giup nang cap gia tri san pham nhanh, giam rui ro ky thuat, va giu duoc kha nang mo rong sau nay.
