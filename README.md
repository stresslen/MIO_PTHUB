# AI Lead Intelligence & Crawler System (B2B & B2G)

Hệ thống tự động tìm kiếm, thu thập, chuẩn hóa, trích xuất thông tin trọng tâm bằng AI và chấm điểm khách hàng tiềm năng B2B/B2G trong lĩnh vực **Chuyển đổi số & AI** (OCR, Voice AI, Computer Vision, LLM, Cloud/Data, Phần mềm).

Hệ thống được thiết kế và triển khai hoàn chỉnh theo tiêu chuẩn quốc tế (Clean Architecture, Modularity, Pydantic v2, FastAPI, SQLAlchemy 2.0, Modern UI).

---

## Kiến trúc hai tiến trình

MIO không chạy crawl trong FastAPI. Hai terminal trao đổi qua hàng đợi
`crawl_jobs` trong cùng database:

```text
Terminal FE/API ── POST /api/crawl/run ──> DB queue ──> Terminal crawl worker
     phản hồi 202 ngay                                  crawl → AI → Google Sheets
```

- **Terminal 1 — FE/API:** phục vụ dashboard và các lệnh người dùng; chỉ enqueue
  crawl job rồi trả ngay, không mở browser và không chạy scheduler.
- **Terminal 2 — crawl worker:** nhận job từ FE, chạy lịch tự động, crawl/browser,
  extraction/scoring AI và ghi kết quả sang Google Sheets.
- SQLite WAL hỗ trợ tốt hai tiến trình trên cùng máy. Khi triển khai API và worker
  trên hai máy/container không chia sẻ filesystem, phải dùng chung một
  `DATABASE_URL` PostgreSQL; không dùng hai file SQLite riêng.
- Worker có heartbeat, hàng đợi FIFO và tự đưa job `RUNNING` dở dang về
  `QUEUED` khi khởi động lại.

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
│   ├── crawl_worker.py      # Worker queue + scheduler + crawl + Google Sheets
│   ├── start.sh             # Terminal 1: FE/API
│   └── start_worker.sh      # Terminal 2: crawl worker
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
- Prompt chấm điểm và prompt kịch bản Sales được lưu riêng tại **gemini_scoring_prompt** và **gemini_sales_prompt** trong worksheet **Settings**.
- Trên dashboard, hai nút **Thiết lập chấm điểm** và **Thiết lập kịch bản Sales** cho phép chỉnh độc lập mà không cần sửa code.
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

### Chạy local bằng hai terminal (khuyến nghị)

```bash
# Terminal 1 — chỉ FE/API
./scripts/start.sh

# Terminal 2 — crawl, scheduler, AI pipeline và Google Sheets
./scripts/start_worker.sh
```

Mở dashboard tại http://127.0.0.1:8000. Nếu dashboard báo crawl worker chưa chạy,
giữ terminal 2 hoạt động.

### Chạy thủ công không dùng script

```bash
# Cài thư viện một lần
pip install -r requirements.txt

# Terminal 1
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2
python3 -m scripts.crawl_worker

# Chạy ngay một job toàn nguồn rồi tiếp tục lắng nghe queue
python3 -m scripts.crawl_worker --run-now --timeframe 1_week
```

Docker Compose cũng khởi động đúng hai service: api và crawl-worker.

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

### Cơ chế Lưu trữ Bền vững bằng SQLite Nội bộ

Dự án sử dụng SQLite (`leads.db`) làm **Cơ sở dữ liệu chính và duy nhất (Primary Durable Database)** trực tiếp trên máy chủ cục bộ:
- Sử dụng chế độ **SQLite WAL (Write-Ahead Logging)** cho phép API Web và Background Worker đọc/ghi dữ liệu đồng thời với tốc độ cao, không bao giờ bị nghẽn mạng hay chạm hạn mức (quota).
- Toàn bộ các bảng dữ liệu được lưu trữ tự động trong `leads.db`:
  - `leads`: Lưu trữ tất cả cơ hội B2B/B2G kèm điểm số, khuyến nghị, trích xuất nhu cầu.
  - `organizations`, `organization_contacts`, `organization_evidence`: Lưu trữ hồ sơ tổ chức vòng 2, người liên hệ và bằng chứng.
  - `crawler_sources`: Quản lý danh sách nguồn crawl, URL hạt giống, trạng thái và lỗi.
  - `keywords`: Quản lý danh sách từ khóa dùng cho lọc và tìm kiếm trực tiếp.
  - `system_settings`: Quản lý các prompt AI tùy chỉnh (`gemini_scoring_prompt`, `gemini_sales_prompt`) và cấu hình LinkedIn.
  - `scheduler_state`, `crawl_jobs`, `crawl_runs`: Điều phối hàng đợi và lịch cào tự động.
- Không còn phụ thuộc vào Google Sheets API (loại bỏ hoàn toàn lỗi 429 Quota Exceeded và 400 Bad Request).
- Khởi động hệ thống tức thì (< 0.5s).

Toàn bộ nguồn và seed URL được lưu trong bảng `crawler_sources` trên SQLite; `configs/sources.yaml` chỉ seed các nguồn ban đầu nếu database còn trống. Nút **Thêm URL** lưu website mới trực tiếp vào SQLite. Nguồn không crawl được vẫn được lưu với trạng thái `NEEDS_ADAPTER` và thông báo cần cập nhật sau.

Trên trang **Nguồn dữ liệu**, nút **Từ khóa** cho phép nhập TXT/CSV, chuỗi phân cách bằng `,` hoặc `;`, và danh sách xuống dòng. Keyword mới được ghi thẳng vào bảng `keywords` trong SQLite, chống trùng không phân biệt chữ hoa/thường và có hiệu lực ngay lập tức. Chỉ lead đã qua AI xử lý hợp lệ mới được lưu vào cơ sở dữ liệu `leads`.

### LinkedIn qua Apify

Nguồn **LinkedIn Posts (Apify)** dùng Actor `harvestapi/linkedin-post-search`. Mỗi lần lịch hằng ngày chạy, Actor tìm tối đa 1.000 bài cho **mỗi keyword Search trực tiếp đang bật** trong cơ sở dữ liệu `keywords`. Khoảng ngày vẫn theo cấu hình chung 1 ngày, 1 tuần hoặc 1 tháng; bình luận và reaction không được crawl.

```env
APIFY_API_TOKEN=<token backend>
APIFY_LINKEDIN_MAX_POSTS_PER_KEYWORD=1000
APIFY_LINKEDIN_CONTENT_TYPE=jobs
APIFY_LINKEDIN_SORT_BY=relevance
```

Không chạy Actor thử với dữ liệu thật nếu chưa kiểm tra chi phí: số bài tối đa của một phiên bằng `1.000 × số keyword đang bật`. Token chỉ đặt trong backend, không commit vào Git.

### Cào thủ công và đặt lịch

- Nút **Cào lại dữ liệu** cho phép chọn đúng 1 ngày, 1 tuần hoặc 1 tháng trước.
- Nút **Đặt lịch cào dữ liệu** chỉ cần chọn giờ chạy hàng ngày theo múi giờ `Asia/Ho_Chi_Minh`.
- API lưu cấu hình lịch vào bảng `scheduler_state` trong SQLite; crawl worker nhận diện cấu hình và tự động thực thi đúng giờ.
- Chỉ chạy một crawl worker chủ động; cơ chế claim nguyên tử ngăn chặn hai worker nhận cùng một job.

### Vận hành Trực tiếp trên Máy chủ (Local Server)

Hệ thống được thiết kế để chạy trực tiếp trên máy chủ này mà không cần deploy lên Render:
- Chạy bằng 2 terminal:
  - Terminal 1: `./scripts/start.sh` (FastAPI Web Dashboard & REST API)
  - Terminal 2: `./scripts/start_worker.sh` (Crawl Worker, AI Pipeline, Auto Scheduler)
- Hai tiến trình dùng chung file database SQLite `leads.db` qua chế độ WAL mode cực nhanh và ổn định.

### Kiểm thử

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest tests -q
```

Chạy test để xác nhận vòng 1 không gọi XAH; vòng 2 crawl trực tiếp khi có URL, dùng dữ liệu XAH trực tiếp khi không có URL, và public search API không tồn tại.
