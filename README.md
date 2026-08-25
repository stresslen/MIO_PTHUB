# AI Lead Intelligence & Crawler System (B2B & B2G)

Hệ thống tự động tìm kiếm, thu thập, chuẩn hóa, trích xuất thông tin trọng tâm bằng AI và chấm điểm khách hàng tiềm năng B2B/B2G trong lĩnh vực **Chuyển đổi số & AI** (OCR, Voice AI, Computer Vision, LLM, Cloud/Data, Phần mềm).

Hệ thống được thiết kế và triển khai hoàn chỉnh theo tiêu chuẩn quốc tế (Clean Architecture, Modularity, Pydantic v2, FastAPI, SQLAlchemy 2.0, Modern UI).

---

## 🏛️ Kiến Trúc Hệ Thống (Clean Architecture)

```
MIO/
├── app/
│   ├── api/                 # FastAPI Router (Leads, Crawl, Sources, Stats, Export)
│   ├── crawlers/            # Source Adapters (Báo Đấu thầu, Chính phủ, Mua sắm công, dx.gov.vn, Hà Nội)
│   ├── pipeline/            # Data Processing (Normalize, Dedup, AI Extraction, Lead Scoring)
│   ├── models/              # Pydantic Schemas & SQLAlchemy DB Models
│   ├── services/            # Business Logic (CrawlerService, LeadService, ExportService)
│   ├── database.py          # SQLite WAL Engine & Session Management
│   ├── config.py            # Global Settings & YAML Config Loaders
│   └── main.py              # FastAPI Entrypoint & Security Headers Middleware
├── configs/
│   ├── sources.yaml         # Dữ liệu bootstrap lần đầu cho worksheet Sources
│   ├── keywords.yaml        # Dữ liệu bootstrap lần đầu cho worksheet Keywords
│   └── scoring.yaml         # Cấu hình cũ, không còn quyết định kết quả scoring
├── data/
│   ├── raw/                 # Lưu trữ raw snapshot (HTML/JSON) phục vụ audit & replay
│   └── golden/              # Golden dataset phục vụ regression testing
├── static/                  # Modern Web Dashboard (HTML5, Vanilla CSS Design System, JS)
├── scripts/
│   ├── run_crawler.py       # CLI Runner chạy crawl live từ terminal
│   └── start.sh             # Script 1-click khởi động hệ thống
├── tests/                   # Bộ kiểm thử tự động toàn diện (Pytest)
├── Dockerfile               # Production Dockerfile
├── docker-compose.yml       # Docker Compose configuration
├── requirements.txt         # Dependencies
└── README.md
```

---

## 🚀 Tính Năng Nổi Bật

### 1. Thu Thập Dữ Liệu Thật 100% (Live Real-World Crawlers)
- **5 Nguồn B2B/B2G trọng yếu**:
  - `baodauthau.vn`: Báo Đấu thầu (thông báo mời thầu, kế hoạch mua sắm CNTT).
  - `baochinhphu.vn`: Cổng Thông tin điện tử Chính phủ (chính sách đầu tư, chiến lược CĐS).
  - `muasamcong.mpi.gov.vn`: Mạng Đấu thầu Quốc gia (gói thầu công B2G).
  - `dx.gov.vn`: Cổng Chuyển đổi số Quốc gia (bài toán, sáng kiến số hóa địa phương).
  - `hanoi.gov.vn`: Cổng Thông tin điện tử TP. Hà Nội (các dự án số hóa thủ đô).
- **Cơ chế chống lỗi mạng**: Hỗ trợ Custom SSL Adapter (xử lý các chứng chỉ chính phủ bảo mật `SECLEVEL=1`), Rate Limiting lịch sự, Exponential Backoff Retry và tự động lưu Snapshot vào `data/raw/` phục vụ kiểm tra nguồn gốc.

### 2. Pipeline Xử Lý Thông Minh & AI Extraction
- **Chuẩn hóa nâng cao (Normalize)**: Parser tiền tệ tiếng Việt thông minh (`"4,5 tỷ VNĐ"` -> `4,500,000,000 VND`), parser ngày tháng đa định dạng, chuẩn hóa tên đơn vị & 63 tỉnh thành.
- **Chống trùng lặp (Deduplication)**: Fingerprint băm SHA-256 xác định duy nhất từng bài đăng / gói thầu (`canonical_url + published_date + normalized_title`).
- **Trích xuất thực thể AI (AI Extractor)**: Trích xuất có cấu trúc: Tên đơn vị, loại hình tổ chức (Government/Enterprise), tóm tắt nhu cầu (1-3 câu), ngân sách, địa bàn, người liên hệ, email, số điện thoại, hạn nộp hồ sơ, minh chứng trích dẫn (`evidence`). AI extraction và scoring là bắt buộc; phản hồi lỗi/không hợp lệ khiến mục đó bị bỏ qua thay vì nhận dữ liệu hoặc điểm giả.

### 3. Chấm điểm và tạo kịch bản Sales bằng Gemini

- Gemini chịu trách nhiệm toàn bộ **total_score**, **recommended_action** (CALL, EMAIL, NURTURE) và **sales_strategy_suggestion**; backend chỉ kiểm tra schema, giới hạn điểm 0–100 và từ chối phản hồi không hợp lệ.
- Không có rule-based/OpenAI fallback. Gemini lỗi, thiếu key hoặc trả JSON sai thì mục dữ liệu chưa hoàn thiện không được lưu thành lead.
- Prompt nghiệp vụ được lưu tại key **gemini_scoring_sales_prompt** trong worksheet **Settings**.
- Trên dashboard, nút **Chấm điểm & Sales** cho phép xem, sửa, nạp gợi ý mặc định và lưu prompt mà không cần sửa code.
- Backend luôn nối dữ liệu cơ hội, minh chứng và JSON contract bắt buộc vào prompt người dùng để hạn chế hallucination.
- Prompt mặc định yêu cầu kịch bản gồm đối tượng, kênh, mục tiêu, mở đầu, thông điệp giá trị, 3–5 câu hỏi khám phá, CTA và các fact cần tránh dùng khi chưa có bằng chứng.

### 4. Giao Diện Web Dashboard Hiện Đại
- Thiết kế theo chuẩn quốc tế: Trực quan, tinh tế, responsive.
- Thẻ chỉ số KPI thời gian thực: Hot Leads, Qualified Leads, Nurture Leads, Tổng số cơ hội, Tổng ngân sách dự án.
- Bộ lọc đa chiều: Tìm kiếm tức thì, lọc theo Hành động (CALL/EMAIL/NURTURE), lọc theo Nguồn, sắp xếp theo Điểm/Ngày/Ngân sách.
- Chi tiết Lead: email/SĐT nằm cùng thông tin đơn vị và ngân sách; kịch bản tiếp cận cùng minh chứng được trình bày theo từng khối dễ dùng cho Sales. Giao diện không hiển thị cơ sở cộng/trừ điểm.
- Trình điều khiển Crawler: Nút bấm chạy crawl live ngay trên web với thanh tiến trình trực quan.
- Xuất dữ liệu: Xuất báo cáo CSV chuẩn UTF-8-BOM tương thích hoàn hảo Microsoft Excel.

---

## 🛠️ Hướng Dẫn Cài Đặt & Khởi Chạy

### Cách 1: Khởi chạy 1-Click (Khuyến nghị)
```bash
./scripts/start.sh
```

### Cách 2: Chạy thủ công
```bash
# 1. Cài đặt thư viện
pip install -r requirements.txt

# 2. Chạy Live Crawl từ terminal để thu thập dữ liệu thật
python3 -m scripts.run_crawler --all --timeframe 1_week

# 3. Khởi động Web Server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Sau khi khởi chạy:
- 🌐 **Web Dashboard**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- 📖 **Swagger API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🧪 Kiểm Thử Tự Động (Automated Testing)
```bash
pytest tests/ -v
```
Toàn bộ các tầng Normalizer, Deduplicator, Scoring Engine, Crawler Adapters và FastAPI Routes đều được kiểm thử tự động.


---

## Gemini tự bổ sung dữ liệu bằng XAH, Google Sheets và Render

### Luồng vòng 1 → vòng 2 → XAH có kiểm chứng

XAH không có trang chatbot và không được mở thành public search API. Pipeline chạy theo thứ tự cố định:

1. Gemini vòng 1 chỉ bóc tách dữ liệu có trong bài/gói thầu gốc: tổ chức, nhu cầu, ngân sách, thời hạn, website/mã số thuế nếu xuất hiện trực tiếp.
2. Nếu vòng 1 có URL hợp lệ, backend crawl website đó trong cùng domain, ưu tiên giới thiệu, lãnh đạo, liên hệ, dự án, tin tức, tuyển dụng và đấu thầu.
3. Nếu vòng 1 không có URL, Gemini chỉ tạo keyword; XAH Search tự tìm kiếm nội dung web và trả kết quả kèm URL nguồn để Gemini trích xuất hồ sơ. Nhánh này không giả lập một website chính thức và không gọi crawler website trực tiếp.
4. Nếu nhánh có URL crawl lỗi hoặc còn thiếu trường quan trọng, Gemini tạo query bổ sung; XAH trả URL, backend tải nội dung URL rồi Gemini tổng hợp lần cuối.
5. Gemini trích xuất `Company Profile`, contact và người có khả năng quyết định. Mỗi dữ liệu lưu được phải có URL và evidence trực tiếp.
6. Nếu vẫn không có dữ liệu, trường giữ `null`/`[]` và hồ sơ ghi `PROFILE_INCOMPLETE`, `DISCOVERY_FAILED`, `AI_EXTRACTION_FAILED`… Không có rule-based fallback, không đoán website, người, email hay dữ liệu giả.

Ngày đăng luôn ưu tiên metadata đáng tin cậy từ trang nguồn. Nếu trang không cung cấp ngày đăng, hệ thống dùng thời điểm crawl làm ngày đăng; ngày trong tiêu đề/nội dung không được dùng thay thế.

API key chỉ đọc từ `XAH_API_KEY` trên backend. File `.env` được loại khỏi Git và Docker build context.

### Google Sheets làm database bền vững

Google Sheets là nguồn lưu bền vững; SQLite chỉ là cache truy vấn cục bộ để giữ nguyên các bộ lọc/dashboard SQL đang có. Khi khởi động, backend hợp nhất hai chiều: nạp dữ liệu từ Sheets vào cache rồi chuyển các lead cục bộ còn thiếu lên Sheets. Mỗi lead mới và thay đổi trạng thái tiếp tục được ghi lên Sheets; hồ sơ vòng 2 được upsert vào các tab riêng và giữ URL/evidence để kiểm tra.

Setup một lần:

1. Tạo một Google Sheet trống và lấy ID trong URL `/spreadsheets/d/<SPREADSHEET_ID>/edit`.
2. Trong Google Cloud, bật Google Sheets API, tạo Service Account và tải JSON key.
3. Share Google Sheet quyền Editor cho giá trị `client_email` trong JSON key.
4. Điền backend/Render env:

```env
GOOGLE_SHEETS_SPREADSHEET_ID=17Glsl0gB7e0YKWAmxPdDUSDysGaeujudmN21Gts0GFw
GOOGLE_SERVICE_ACCOUNT_JSON=<toàn bộ JSON trên một dòng hoặc base64 của JSON>
GOOGLE_SHEETS_LEADS_WORKSHEET=gid:0
GOOGLE_SHEETS_SETTINGS_WORKSHEET=Settings
GOOGLE_SHEETS_KEYWORDS_WORKSHEET=Keywords
GOOGLE_SHEETS_SOURCES_WORKSHEET=Sources
GOOGLE_SHEETS_ORGANIZATIONS_WORKSHEET=Organizations
GOOGLE_SHEETS_CONTACTS_WORKSHEET=Contacts
GOOGLE_SHEETS_EVIDENCE_WORKSHEET=Organization_Evidence
GOOGLE_SHEETS_PROJECTS_WORKSHEET=Projects
GOOGLE_SHEETS_NEWS_WORKSHEET=News
GOOGLE_SHEETS_JOBS_WORKSHEET=Jobs
GOOGLE_SHEETS_TENDERS_WORKSHEET=Tenders
GOOGLE_SHEETS_INTERACTIONS_WORKSHEET=Interactions
```

Backend ghi lead trực tiếp vào tab `gid=0`, đồng thời tự tạo worksheet `Settings`, `Keywords`, `Sources`, `Organizations`, `Contacts`, `Organization_Evidence`, `Projects`, `News`, `Jobs`, `Tenders`, `Interactions` và header khi kết nối lần đầu. Lần đầu mở trình chỉnh prompt, backend tự tạo key **gemini_scoring_sales_prompt** trong **Settings**; mọi lần lưu sau cập nhật trực tiếp cùng key và áp dụng cho các lượt chấm điểm tiếp theo. `configs/keywords.yaml` chỉ seed dữ liệu khi tab `Keywords` còn trống; sau đó pipeline đọc keyword từ cache đồng bộ với Google Sheets. Để chuyển dữ liệu lead hiện có ngay, chạy `.venv/bin/python -m scripts.migrate_to_google_sheets`. Kiểm tra trạng thái an toàn tại `GET /api/storage/status`; endpoint này không bao giờ trả credential.

Toàn bộ 10 nguồn và 19 seed URL được lưu trong worksheet `Sources`; `configs/sources.yaml` chỉ seed khi worksheet trống. Nút **Thêm URL** lưu website mới trước khi kiểm tra. Nguồn không crawl được vẫn nằm trong Sheet với trạng thái `NEEDS_ADAPTER` và thông báo cần cập nhật sau.

Trên trang **Nguồn dữ liệu**, nút **Từ khóa** cho phép nhập TXT/CSV, chuỗi phân cách bằng `,` hoặc `;`, và danh sách xuống dòng. Keyword mới được ghi thẳng vào Sheet, chống trùng không phân biệt chữ hoa/thường và dùng ngay sau khi đồng bộ. Chỉ lead đã qua AI xử lý hợp lệ mới được upsert vào worksheet Leads.

### Cào thủ công và đặt lịch

- Nút **Cào lại dữ liệu** cho phép chọn đúng 1 ngày, 1 tuần hoặc 1 tháng trước.
- Nút **Đặt lịch cào dữ liệu** chỉ cần chọn giờ chạy hàng ngày theo múi giờ `Asia/Ho_Chi_Minh`.
- Cấu hình lịch được ghi vào worksheet `Settings`, nên được khôi phục sau khi Render restart.
- Chỉ chạy một Uvicorn worker để tránh một lịch bị kích hoạt nhiều lần.

### Deploy Render

Repo đã có `render.yaml`. Tạo Render Blueprint từ file này và nhập các biến `sync: false` khi được hỏi:

- `XAH_API_KEY`
- `GEMINI_API_KEY` (có thể dùng cùng gateway key hiện tại)
- `GOOGLE_SERVICE_ACCOUNT_JSON`

Blueprint dùng gói `starter` vì scheduler nằm trong tiến trình web và cần instance luôn hoạt động. Nếu đổi sang gói `free`, web service có thể sleep khi không có traffic và lịch nội bộ sẽ không chạy đúng giờ. Dữ liệu vẫn an toàn trên Google Sheets vì filesystem Render chỉ được dùng làm cache.

### Kiểm thử

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest tests -q
```

Chạy test để xác nhận vòng 1 không gọi XAH; vòng 2 crawl trực tiếp khi có URL, dùng dữ liệu XAH trực tiếp khi không có URL, và public search API không tồn tại.
