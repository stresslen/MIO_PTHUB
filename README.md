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
│   ├── sources.yaml         # Cấu hình nguồn cào, seed URLs, timeouts, rate limits
│   ├── keywords.yaml        # Danh mục từ khóa mục tiêu (OCR, CV, Voice, LLM, CĐS...)
│   └── scoring.yaml         # Trọng số chấm điểm & ngưỡng phân loại hành động
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
- **Trích xuất thực thể AI (AI Extractor)**: Trích xuất có cấu trúc: Tên đơn vị, loại hình tổ chức (Government/Enterprise), tóm tắt nhu cầu (1-3 câu), ngân sách, địa bàn, người liên hệ, email, số điện thoại, hạn nộp hồ sơ, minh chứng trích dẫn (`evidence`). Hỗ trợ cả LLM (OpenAI/Gemini) và bộ NLP Rule-based thông minh chạy offline 100%.

### 3. Bộ Chấm Điểm Lead Linh Hoạt (Scoring Engine)
Tách biệt hoàn toàn trong `configs/scoring.yaml`, Sales có thể chỉnh trọng số mà không sửa code:
- `+25 điểm`: Có dự án/gói thầu cụ thể liên quan AI/CĐS.
- `+20 điểm`: Ngân sách lớn (>= 3 tỷ VNĐ).
- `+5 điểm thưởng`: Ngân sách đặc biệt lớn (>= 5 tỷ VNĐ).
- `+10 điểm`: Địa bàn chiến lược (Hà Nội, TP.HCM, Đà Nẵng, Quảng Ninh...).
- `+15 điểm`: Trùng khớp năng lực AI lõi (OCR, Computer Vision, Voice AI, LLM).
- `+10 điểm`: Có email / số điện thoại liên hệ công khai.
- `+5 điểm`: Tin tức mới xuất bản trong vòng 3 ngày.
- `+10 điểm`: Còn >= 5 ngày trước hạn đóng thầu.
- `-15 điểm`: Chỉ là tin chính sách chung, chưa có nhu cầu mua sắm cụ thể.
- `-30 điểm`: Đã quá hạn tiếp cận.

**Phân luồng hành động:**
- 🔴 `90 - 100 điểm` ➔ **CALL** (Hot Lead - Ưu tiên gọi điện tiếp cận ngay).
- 🔵 `80 - 89 điểm` ➔ **EMAIL** (Qualified - Chuẩn bị thư chào giải pháp).
- ⚪ `0 - 79 điểm` ➔ **NURTURE** (Marketing nuôi dưỡng & theo dõi thêm).

### 4. Giao Diện Web Dashboard Hiện Đại
- Thiết kế theo chuẩn quốc tế: Trực quan, tinh tế, responsive.
- Thẻ chỉ số KPI thời gian thực: Hot Leads, Qualified Leads, Nurture Leads, Tổng số cơ hội, Tổng ngân sách dự án.
- Bộ lọc đa chiều: Tìm kiếm tức thì, lọc theo Hành động (CALL/EMAIL/NURTURE), lọc theo Nguồn, sắp xếp theo Điểm/Ngày/Ngân sách.
- Drawer chi tiết Lead: Xem toàn bộ minh chứng trích xuất từ văn bản gốc và bảng chi tiết từng lý do cộng/trừ điểm.
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
python3 -m scripts.run_crawler --all --max 15

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

### Luồng Gemini → XAH nội bộ

XAH không có trang chatbot và không được mở thành public search API. Trong lúc bóc tách một bài crawl, Gemini trả thêm ba trường điều khiển nội bộ: `needs_web_search`, `missing_information` và `search_query`.

1. Gemini xử lý nội dung gốc trước.
2. Nếu Gemini xác định thiếu thông tin quan trọng cho việc đánh giá lead, backend gọi `POST https://api.xah.io/v1/search` với `model=search`, `search_type=web`, `max_results=5`, `country=Vietnam`, `language=Vietnam`.
3. Kết quả XAH và URL nguồn được đưa vào lượt Gemini thứ hai.
4. Gemini hoàn thiện dữ liệu; URL XAH được lưu trong `evidence` để kiểm tra nguồn.
5. Nếu XAH lỗi hoặc không có dữ liệu, pipeline giữ kết quả Gemini ban đầu và tiếp tục, không làm hỏng phiên crawl.

Ngày đăng luôn ưu tiên metadata đáng tin cậy từ trang nguồn. Nếu trang không cung cấp ngày đăng, hệ thống dùng chính thời điểm crawl làm ngày đăng; ngày xuất hiện trong tiêu đề/nội dung (hạn nộp, hạn hoàn thành, ngày sự kiện) không được dùng thay thế.

API key chỉ đọc từ `XAH_API_KEY` trên backend. File `.env` được loại khỏi Git và Docker build context.

### Google Sheets làm database bền vững

Google Sheets là nguồn lưu bền vững; SQLite chỉ là cache truy vấn cục bộ để giữ nguyên các bộ lọc/dashboard SQL đang có. Khi khởi động, backend hợp nhất hai chiều: nạp dữ liệu từ Sheets vào cache rồi chuyển các lead cục bộ còn thiếu lên Sheets. Mỗi lead mới và thay đổi trạng thái tiếp tục được ghi lên Sheets; nguồn XAH bổ sung nằm trong trường `evidence`.

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
```

Backend ghi lead trực tiếp vào tab `gid=0`, đồng thời tự tạo worksheet `Settings` và header khi kết nối lần đầu. Để chuyển dữ liệu hiện có ngay, chạy `.venv/bin/python -m scripts.migrate_to_google_sheets`. Kiểm tra trạng thái an toàn tại `GET /api/storage/status`; endpoint này không bao giờ trả credential.

Sau khi `GOOGLE_SERVICE_ACCOUNT_JSON` được cấu hình, mỗi lead mới, lead chờ AI, lead xử lý lại và thay đổi trạng thái trên dashboard đều được upsert ngay vào Google Sheets. Không cần mở Sheet hoặc chạy thao tác dán dữ liệu thủ công.

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

Chạy test để xác nhận XAH chỉ được gọi khi Gemini đánh dấu thiếu thông tin và public search API không tồn tại.
