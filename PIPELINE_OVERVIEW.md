# MIO Pipeline hiện tại

Tài liệu này mô tả pipeline theo cách dễ đọc cho người làm low-code. Mục tiêu là biến một bài viết, tin tuyển dụng hoặc thông báo mời thầu thành dữ liệu có cấu trúc, được kiểm tra nguồn, chấm điểm và chỉ lưu các cơ hội phù hợp.

## 1. Bức tranh tổng thể

```text
Nguồn dữ liệu
    ↓
Fetch / Parse nội dung
    ↓
Chuẩn hóa URL + chống trùng theo URL
    ↓
Lọc nhanh theo keyword từ Google Sheets
    ↓
Gemini Extraction: đọc nội dung bài viết
    ↓
Company Enrichment:
  ├─ Có URL website chính thức → crawl sâu website đó
  └─ Chưa có URL → Gemini tạo truy vấn → XAH tìm URL chính thức
                         → crawl sâu website chính thức
    ↓
Gemini Profile: tổng hợp hồ sơ tổ chức và contact/evidence
    ↓
Gemini Scoring: chấm mức độ phù hợp với keyword/sản phẩm
    ↓
Score >= 40 → lưu Lead / Organization / Contact / Evidence
Score < 40  → bỏ qua lưu cơ hội bán hàng
```

Pipeline có hai phần chính:

1. **Round 1**: lấy và phân tích chính bài viết gốc.
2. **Company Enrichment**: tìm hiểu sâu tổ chức liên quan bằng website chính thức, sau đó tổng hợp lại thành một kết quả cuối cùng.

Kết quả cuối cùng không hiển thị riêng một bản “Crawl vòng 2”. Thông tin bổ sung được gộp vào hồ sơ tổ chức, contact, evidence và scoring của chính bài viết.

## 2. Các thành phần và vai trò

| Thành phần | Vai trò dễ hiểu |
|---|---|
| Source adapters | Lấy bài từ RSS, Google Sheets, URL đơn lẻ hoặc các nguồn được cấu hình |
| Fetch / parser | Tải HTML, lấy tiêu đề, nội dung, thời gian và URL |
| Keyword service | Đọc bộ keyword nghiệp vụ từ Google Sheets |
| Gemini Extraction | Trích xuất dữ liệu có cấu trúc từ bài viết |
| XAH Search | Chỉ dùng để tìm URL website chính thức khi cần enrichment |
| Crawl4AI | Tải nội dung các URL được chọn; có thể gặp timeout, DNS, 403 hoặc 406 |
| GenericWebsiteAdapter | Crawl nhiều trang con cùng domain bằng sitemap và liên kết HTML |
| Gemini Profile | Tổng hợp hồ sơ tổ chức, contact, dự án, công nghệ và minh chứng |
| Gemini Scoring | Đánh giá mức độ liên quan và đề xuất hành động bán hàng |
| SQLite | Cache và dữ liệu chạy cục bộ |
| Google Sheets | Nguồn keyword và nơi đồng bộ dữ liệu nghiệp vụ |

## 3. Round 1 — xử lý bài viết gốc

### Bước 1: lấy dữ liệu

Pipeline lấy bài từ nguồn đã cấu hình. Với mỗi bài, hệ thống giữ lại tối thiểu:

- URL nguồn.
- Tiêu đề.
- Nội dung hoặc phần text đã đọc được.
- Tên nguồn.
- Thời gian xuất bản nếu có.

### Bước 2: chuẩn hóa và chống trùng

URL được chuẩn hóa trước khi xử lý, ví dụ loại bỏ một số khác biệt không có ý nghĩa như fragment `#...` hoặc slash cuối.

Một bài được coi là trùng khi **canonical URL giống nhau**. Không dùng tiêu đề, tên công ty hoặc nội dung để xác định trùng trong nghiệp vụ hiện tại.

Điều này có nghĩa là:

- Cùng một URL xuất hiện nhiều lần → chỉ xử lý một lần.
- Hai bài khác URL nhưng nội dung giống nhau → vẫn có thể là hai bản ghi khác nhau.

### Luồng riêng của TopCV: search-crawl tuần tự

TopCV không gom toàn bộ kết quả của tất cả keyword rồi mới crawl. Với tối đa 3 keyword được bật trong Google Sheets, adapter thực hiện tuần tự:

```text
Keyword 1
  → crawl trang kết quả TopCV
  → lấy job card
  → crawl ngay từng URL chi tiết
  → parse và cache nội dung
  ↓
nghỉ ngẫu nhiên 10–12,5 giây
  ↓
Keyword 2 → lặp lại
```

Các trang listing và detail dùng cùng một phiên Crawl4AI/Playwright. Nếu một job detail lỗi, job đó được bỏ qua và pipeline tiếp tục job tiếp theo; lỗi không làm mất các keyword còn lại. Việc Gemini Extraction/Scoring và lưu Lead vẫn chạy theo vòng xử lý chuẩn của `CrawlerService` sau khi adapter hoàn tất discovery, nhưng không còn mở hàng loạt trang tìm kiếm trước khi crawl detail.

### Bước 3: lọc nhanh theo keyword

Keyword nghiệp vụ được đọc từ Google Sheets, không hard-code trong pipeline chính. Nhóm keyword có thể bao gồm các nhu cầu như:

- Chuyển đổi số.
- Xây dựng hệ thống thông tin.
- Phần mềm, dữ liệu, AI, tự động hóa.
- Hạ tầng CNTT, cloud, an toàn thông tin.
- Tuyển dụng các vị trí có tín hiệu về công nghệ hoặc chuyển đổi số.

Keyword chỉ là bộ lọc ban đầu. Bài vượt qua bước này vẫn phải được Gemini đọc và chấm điểm; không phải cứ chứa một từ khóa là trở thành cơ hội.

Nếu bài không có tín hiệu liên quan, pipeline có thể dừng sớm để tiết kiệm chi phí.

### Bước 4: Gemini Extraction

Gemini đọc bài viết và trả về JSON theo schema của hệ thống. Các nhóm thông tin chính gồm:

- Tổ chức, chủ đầu tư hoặc đơn vị tuyển dụng.
- Nhu cầu, dự án hoặc nội dung tuyển dụng.
- Công nghệ và giải pháp liên quan.
- Ngân sách hoặc giá trị công bố.
- Deadline.
- Người liên hệ, email, số điện thoại.
- Địa điểm triển khai hoặc địa chỉ liên hệ.
- Nhóm nhu cầu.
- Minh chứng trực tiếp và URL nguồn.

Gemini phải phân biệt rõ:

- **Nhu cầu mua giải pháp**: mời thầu phần mềm, license, hạ tầng, bảo mật, triển khai hệ thống...
- **Tín hiệu tiềm năng**: bài viết về chiến lược dữ liệu, AI, chuyển đổi số hoặc tuyển dụng vị trí công nghệ.
- **Nội dung không phù hợp**: cầu đường, công viên, vật tư không liên quan CNTT, tài sản thanh lý, webinar/sự kiện không có nhu cầu mua, tuyển dụng marketing thuần túy...

Gemini không được tự suy đoán ngân sách, contact, công nghệ hoặc dự án nếu bài không có căn cứ.

## 4. Company Enrichment — crawl website chính thức

Mục tiêu của phần này là lấy thêm thông tin đáng tin cậy về tổ chức, nhưng vẫn giữ nguồn rõ ràng.

### Nhánh A: bài đã có URL website chính thức

Nếu Round 1 đã xác định được website chính thức, pipeline dùng URL đó làm seed và crawl sâu cùng domain.

### Nhánh B: bài chưa có URL website chính thức

Pipeline thực hiện theo thứ tự:

1. Gemini tạo **một truy vấn duy nhất** để tìm website chính thức của tổ chức.
2. XAH Search nhận truy vấn đó.
3. Pipeline lấy các URL XAH trả về.
4. Chỉ ưu tiên URL được xác định là website chính thức của chính tổ chức.
5. Crawl URL seed và các trang con cùng domain.
6. Nếu URL bị lỗi hoặc không đọc được, gọi lại XAH để tìm URL khác.
7. Tối đa 5 lần thử. Sau 5 lần vẫn không có website crawl được thì bỏ qua enrichment bổ sung.

Prompt tìm kiếm website chính thức yêu cầu loại trừ:

- Báo chí, blog, diễn đàn, thư mục doanh nghiệp.
- Mạng xã hội và trang tuyển dụng.
- Cổng đấu thầu hoặc website bên thứ ba.
- Trang pháp luật, văn bản, tin tức nói về tổ chức.
- URL dự án hoặc URL của công ty khác.

XAH làm nhiệm vụ **tìm URL**, không phải nguồn chính để trích xuất toàn bộ hồ sơ. Gemini mới là thành phần đọc và tổng hợp nội dung sau khi backend crawl được trang.

### Retry XAH không phải bypass anti-bot

Retry giúp tìm URL khác khi URL trước đó sai, cũ hoặc không truy cập được. Retry không đảm bảo vượt được:

- DNS không phân giải được.
- Website trả HTTP 403/406.
- WAF/anti-bot.
- Website timeout hoặc chặn trình duyệt tự động.

Nếu website chính thức không crawl được sau tối đa 5 lần, trạng thái enrichment được ghi nhận là chưa hoàn chỉnh; không được dùng URL sai hoặc website bên thứ ba để thay thế.

## 5. Crawl toàn bộ website hoạt động như thế nào?

Pipeline không chỉ đọc trang chủ. `GenericWebsiteAdapter` tìm trang con bằng hai cách:

### Cách 1: sitemap XML

Backend thử đọc các đường dẫn phổ biến như:

```text
/sitemap.xml
/sitemap_index.xml
```

Nếu có XML sitemap, hệ thống lấy các node `<loc>` để biết danh sách URL trong website.

### Cách 2: liên kết trong HTML/DOM

Backend đọc HTML đã tải, tìm các thẻ liên kết như:

```html
<a href="/ve-chung-toi">Về chúng tôi</a>
```

Các link được đưa vào hàng đợi crawl theo kiểu BFS: xử lý trang gần seed trước, sau đó đi sâu dần vào các trang con.

### Giới hạn an toàn hiện tại

Mặc định:

```text
COMPANY_PROFILE_MAX_PAGES=20
COMPANY_PROFILE_MAX_DEPTH=3
```

Do đó đây là crawl sâu có giới hạn, không phải crawl vô hạn toàn bộ Internet hay toàn bộ website không giới hạn.

Hệ thống chỉ giữ URL cùng domain, bỏ qua các loại file tĩnh và các đường dẫn thường không có giá trị hồ sơ như login, cart, checkout hoặc logout. URL của Google, Bing, Yahoo, DuckDuckGo và các công cụ tìm kiếm khác cũng bị loại khỏi seed website chính thức.

## 6. Gemini Profile — tổng hợp thông tin bổ sung

Sau khi crawl, backend gộp nội dung các trang thành `website_context` rồi gửi cho Gemini. Gemini có thể tổng hợp:

- Tên pháp lý và tên thương hiệu.
- Ngành nghề.
- Quy mô, địa điểm và thông tin giới thiệu.
- Công nghệ hoặc nền tảng được công bố.
- Ban lãnh đạo hoặc contact.
- Dự án, hoạt động và tín hiệu nhu cầu.
- Evidence trực tiếp cho từng kết luận.

Mỗi contact, project hoặc evidence quan trọng phải có nguồn URL thật. Nếu không có nguồn, Gemini phải để trống hoặc đánh dấu chưa xác minh, không bịa dữ liệu.

Kết quả Profile được gộp với kết quả Extraction của bài gốc thành một hồ sơ cuối cùng. FE không cần hiển thị một khối riêng tên “Hồ sơ tổ chức · Crawl vòng 2”.

Một số trạng thái có thể gặp:

| Trạng thái | Ý nghĩa |
|---|---|
| `COMPLETED` | Đã xử lý đủ các bước chính |
| `PROFILE_INCOMPLETE` | Có dữ liệu nhưng hồ sơ website chưa đủ hoặc có trang không đọc được |
| `WEBSITE_NOT_FOUND` | Không tìm được website chính thức phù hợp |
| `SECOND_CRAWL_BLOCKED` | Website bổ sung bị chặn hoặc không crawl được |
| `DISCOVERY_FAILED` | Không hoàn tất được bước tìm kiếm/crawl bổ sung |
| `INTERRUPTED` | Backend restart/reload khi crawl chưa hoàn tất; không phải kết quả crawl mới |
| `AI_EXTRACTION_FAILED` | Gemini không trả JSON hợp lệ hoặc không trích xuất được |
| `FILTERED_OUT` | Bị loại ở bước lọc hoặc scoring |

Lỗi crawl không nên được hiển thị như một hồ sơ tổ chức có các trường “Chưa cập nhật” nếu chưa có dữ liệu xác minh. FE nên hiển thị trạng thái ngắn gọn và cho phép xem log/evidence khi cần.

## Phụ lục A — Các prompt Gemini đang dùng

Phần này giải thích prompt theo đúng trách nhiệm của từng lần gọi Gemini. Gemini không dùng một prompt duy nhất cho toàn bộ pipeline; mỗi bước có mục tiêu và dữ liệu đầu vào riêng.

### A1. Prompt Extraction vòng 1

**Mục tiêu:** đọc đúng bài viết gốc và biến nội dung thành các trường nghiệp vụ có cấu trúc.

**Dữ liệu được đưa vào prompt:**

```text
NGUỒN CRAWLER: URL hoặc tên nguồn
KEYWORD KHỚP TỪ GOOGLE SHEETS: danh sách keyword đã khớp ở bước lọc nhanh
TIÊU ĐỀ: tiêu đề bài viết
NỘI DUNG GỐC: toàn bộ nội dung đã chuẩn hóa thành text
```

**Các yêu cầu chính trong prompt:**

1. Chỉ lấy thông tin xuất hiện trực tiếp trong bài gốc; vòng 1 không search và không suy đoán.
2. Keyword từ Google Sheets chỉ là tín hiệu định hướng, không phải bằng chứng đủ để kết luận có cơ hội.
3. Xác định đúng tổ chức có nhu cầu, chủ đầu tư, bên mời thầu hoặc đơn vị đang tuyển dụng.
4. Với tin tuyển dụng, nhận diện các vị trí/nhiệm vụ liên quan CNTT, chuyển đổi số, AI, ERP, CRM, cloud, dữ liệu hoặc hạ tầng.
5. Thiếu bằng chứng thì trả `null` hoặc `[]`; không trả các giá trị giả như “Đang cập nhật”.
6. `organization_website` chỉ được lấy khi URL/domain xuất hiện trực tiếp trong bài; không đoán website theo tên tổ chức.
7. Chỉ điền ngân sách khi bài có giá gói thầu, ngân sách hoặc mức lương/ngân sách tuyển dụng rõ ràng.
8. `deadline` chỉ là hạn nộp hồ sơ, đóng thầu hoặc ứng tuyển; không lấy ngày đăng bài thay cho deadline.
9. `evidence` phải là minh chứng trực tiếp cho tổ chức, nhu cầu, công nghệ, ngân sách/deadline hoặc contact.

**Output bắt buộc:** một JSON object duy nhất, gồm các trường:

```json
{
  "organization_name": null,
  "organization_type": null,
  "organization_website": null,
  "organization_tax_code": null,
  "need_summary": null,
  "need_categories": [],
  "budget_value": null,
  "budget_text": null,
  "location": null,
  "contact_name": null,
  "contact_email": null,
  "contact_phone": null,
  "deadline": null,
  "relevance": 0.0,
  "evidence": [],
  "missing_information": []
}
```

Sau khi Gemini trả kết quả, backend còn kiểm tra lại website: nếu domain không xuất hiện trong text bài gốc thì xóa `organization_website`. Đây là lớp bảo vệ bổ sung ngoài prompt.

### A2. Prompt tìm website chính thức cho XAH

**Mục tiêu:** khi Extraction chưa có website, yêu cầu Gemini tạo truy vấn để XAH tìm đúng website chính thức.

**Dữ liệu được đưa vào:**

```text
Tổ chức cần tìm: tên tổ chức
Mã số thuế: nếu có
Địa điểm: nếu có
```

**Prompt bắt Gemini phải làm:**

- Chỉ tìm trang chủ hoặc domain do chính tổ chức sở hữu/vận hành.
- Dùng mã số thuế và địa điểm để phân biệt tổ chức trùng tên khi có.
- Không tìm thông tin ngành, doanh thu, dự án, tin tức, việc làm hoặc contact ở bước này.
- Không trả URL báo chí, blog, danh bạ, mạng xã hội, trang tuyển dụng, cổng đấu thầu, website pháp luật hoặc bên thứ ba.
- Không tự đoán domain.
- Chỉ trả đúng một truy vấn trong JSON.

**Output bắt buộc:**

```json
{"queries": ["website chính thức <tên tổ chức>"]}
```

Backend giới hạn kết quả còn một query trước khi gọi XAH. Vì vậy Gemini ở bước này không được phép tạo nhiều nhánh tìm kiếm kiểu “doanh thu”, “tuyển dụng”, “dự án”, “tin tức”.

### A3. Prompt Company Profile

**Mục tiêu:** hợp nhất dữ liệu bài gốc và toàn bộ nội dung crawl website chính thức thành một hồ sơ tổ chức cuối cùng.

**Dữ liệu được đưa vào prompt:**

```text
Tổ chức vòng 1
Loại tổ chức và mã số thuế vòng 1
Website đã xác định
Dữ liệu đã trích xuất ở vòng 1
DỮ LIỆU CRAWL WEBSITE CHÍNH THỨC: các trang con đã crawl
Kết quả crawl bổ sung có URL nguồn (nếu có)
```

**Quy tắc quan trọng:**

- Chỉ trả một JSON kết quả cuối cùng; không trả báo cáo riêng cho crawl vòng 1 và crawl bổ sung.
- Không tạo tên người, chức danh, email, điện thoại, doanh thu, công nghệ hoặc dự án nếu không có bằng chứng.
- Bắt buộc đọc cả header, footer, nav, aside, form và marker `[Email: ...]`, `[SĐT: ...]`; nếu chỉ có contact cấp tổ chức mà không có tên cá nhân thì vẫn có thể trả `full_name: null`, `raw_title: "Hotline"` hoặc `"Văn phòng"`, `role_group: "other"`.
- Không suy diễn email theo mẫu.
- Mỗi contact và dữ liệu quan trọng phải có `source_url` thật xuất hiện trong prompt và `evidence_text` trực tiếp.
- `official_url` chỉ được lấy từ URL xuất hiện nguyên văn trong prompt.
- Chỉ xếp hạng người thực sự tìm thấy; `role_group` thuộc `economic_buyer`, `technical_buyer`, `process_buyer`, `champion` hoặc `other`.
- Không trích xuất lịch sử tương tác nội bộ từ website.

**Các nhóm field Gemini phải trả:**

```text
legal_name, aliases, official_url, tax_code
industry, size, locations, revenue, employee_count
technologies
projects[]
news[]
jobs[]
tenders[]
contacts[]
evidence[]
missing_information[]
search_queries[]
```

Trong đó các phần tử quan trọng như `projects[]`, `contacts[]` và `evidence[]` phải gắn URL nguồn. Backend tiếp tục lọc bỏ các evidence có URL không nằm trong danh sách URL đã thật sự đưa cho Gemini.

### A3.1. Dữ liệu trung gian sau crawl, trước khi gọi Gemini

Sau khi `GenericWebsiteAdapter` crawl xong, backend chưa tự hiểu hay tự gắn nhãn ngành nghề/contact/dự án. Backend chỉ tạo một chuỗi context có cấu trúc để Gemini đọc.

**Nguồn URL được đưa vào context:**

- URL seed website chính thức.
- URL lấy từ `sitemap.xml` hoặc sitemap index.
- URL tìm thấy trong các thẻ link HTML/DOM.
- Chỉ giữ các URL cùng domain với website chính thức.
- Tối đa `COMPANY_PROFILE_MAX_PAGES` trang và độ sâu tối đa `COMPANY_PROFILE_MAX_DEPTH`.

**Mỗi trang HTML được rút thành block:**

```text
URL: https://example.com/trang-con
Tiêu đề: Tiêu đề trang
Nội dung: toàn bộ text hiển thị đã parse và làm sạch
```

Các vùng hiển thị như `header`, `footer`, `nav`, `aside` và `form` được giữ lại. Parser chỉ loại payload kỹ thuật không phải nội dung đọc được như `script`, `style`, `noscript`, `template`, `svg`, `canvas`. Giá trị link `mailto:` và `tel:` cũng được chuyển thành text `[Email: ...]` và `[SĐT: ...]`. Trang rỗng hoàn toàn mới bị bỏ qua.

**PDF công khai được phát hiện từ link trong HTML** cũng được xử lý riêng, tối đa 10 URL PDF:

```text
URL: https://example.com/tai-lieu.pdf
Tiêu đề: tên tài liệu
Nội dung PDF: toàn bộ text đọc được từ PDF
```

Các block được nối bằng dấu phân cách:

```text
[block trang 1]

---

[block trang 2]

---

[block PDF nếu có]
```

Application không còn đặt giới hạn ký tự/token để cắt `website_context`; toàn bộ text của các trang đã crawl được đưa vào prompt. Giới hạn còn lại là context window và giới hạn request của model/gateway, nằm ngoài khả năng kiểm soát của application.

**Ví dụ dữ liệu thật ở ngay trước prompt Profile:**

```text
DỮ LIỆU CRAWL WEBSITE CHÍNH THỨC:
URL: https://example.com/ve-chung-toi
Tiêu đề: Về chúng tôi
Nội dung: ...

---

URL: https://example.com/cong-nghe
Tiêu đề: Công nghệ
Nội dung: ...
```

Sau đó chuỗi này được chèn nguyên vào phần `DỮ LIỆU CRAWL WEBSITE CHÍNH THỨC` của prompt Profile, cùng với dữ liệu vòng 1 và metadata tổ chức.

**Khác nhau giữa hai nhánh crawl vòng 2:**

| Nhánh | Dữ liệu gửi tiếp cho Gemini |
|---|---|
| Vòng 1 đã có website hợp lệ | `website_context` của toàn bộ website chính thức; nếu Profile còn thiếu, có thể gọi XAH bổ sung và gửi thêm `_candidate_context` gồm URL, tiêu đề, snippet XAH và text backend tải được |
| Vòng 1 chưa có website | Gemini tạo một query → XAH chọn URL seed → backend crawl sâu cùng domain → gửi `website_context` của website đã crawl cho Profile |

Ở nhánh chưa có website, snippet/answer của XAH chủ yếu dùng để chọn URL và ghi nhận nguồn; nội dung chính mà Gemini Profile đọc là text do backend crawl từ website chính thức. XAH không tự biến kết quả tìm kiếm thành hồ sơ tổ chức.

### A4. Prompt Scoring

**Mục tiêu:** đánh giá mức độ liên quan của cơ hội với sản phẩm và keyword, từ 0 đến 100.

Prompt scoring mặc định được lưu trong code nhưng có thể được ghi đè bằng Google Sheets, key:

```text
gemini_scoring_prompt
```

**Dữ liệu động được đưa vào prompt:**

```text
Tiêu đề
Nhu cầu
Nhóm nhu cầu
Ngân sách
Địa bàn
Email và số điện thoại công khai
Ngày đăng và hạn chót
Mức độ phù hợp vòng 1
Keyword khớp ở vòng lọc
Tối đa 8 minh chứng
```

**Cổng liên quan bắt buộc:**

- Trước khi cộng điểm, Gemini phải xác định nội dung có nhu cầu/dự án/mua sắm/tuyển dụng thực tế hay không.
- Nhu cầu đó phải liên quan trực tiếp đến ít nhất một keyword đã khớp từ Google Sheets.
- Keyword xuất hiện tình cờ, trong phần giới thiệu chung, tin chính sách hoặc tên sản phẩm không liên quan không được tính là cơ hội.
- Nếu không chứng minh được quan hệ trực tiếp, bắt buộc trả `total_score = 0`, `recommended_action = "NURTURE"` và không đề xuất Sales theo đuổi.
- Tin tuyển dụng chỉ được coi là liên quan khi vị trí và nhiệm vụ gắn với CNTT, chuyển đổi số, dữ liệu, AI, phần mềm, hạ tầng hoặc triển khai hệ thống.

**Các tiêu chí điểm trong prompt mặc định:**

| Tiêu chí | Điểm tối đa |
|---|---:|
| Nhu cầu và mức phù hợp giải pháp | 25 |
| Ý định triển khai/tín hiệu mua sắm | 20 |
| Ngân sách và khả năng chi trả có bằng chứng | 20 |
| Thời điểm, deadline và độ mới | 15 |
| Mức phù hợp của tổ chức và địa bàn | 10 |
| Chất lượng contact công khai | 10 |

Prompt cũng hướng dẫn rằng tuyển dụng vị trí CĐS/IT/AI có nhiệm vụ công nghệ rõ ràng có thể là tín hiệu B2B thực tế; ngược lại nội dung lý thuyết chung chung không có nhu cầu thực tế phải dưới 40.

**Output scoring bắt buộc:**

```json
{
  "total_score": 0,
  "recommended_action": "CALL|EMAIL|NURTURE",
  "score_reasons": [],
  "breakdown": [
    {"rule_name": "tên tiêu chí", "points": 0, "reason": "lý do có bằng chứng"}
  ],
  "sales_strategy_suggestion": "..."
}
```

Backend yêu cầu JSON hợp lệ và giới hạn điểm trong 0–100. Nếu Gemini lỗi hoặc trả sai schema, pipeline không tự tạo điểm giả và không lưu lead chưa hoàn chỉnh.

### A5. Prompt Sales

**Mục tiêu:** tạo kịch bản tiếp cận phù hợp với action `CALL`, `EMAIL` hoặc `NURTURE` mà Gemini đã chọn.

Prompt mặc định có thể ghi đè trong Google Sheets, key:

```text
gemini_sales_prompt
```

Kịch bản phải có các phần:

- Đối tượng nên tiếp cận.
- Kênh ưu tiên và lý do.
- Mục tiêu tiếp cận.
- Cách mở đầu 1–2 câu.
- Thông điệp giá trị.
- 3–5 câu hỏi khám phá.
- Bước tiếp theo/CTA.
- Điều cần tránh.

Prompt Sales đặc biệt yêu cầu:

- Không quảng cáo chung chung.
- Không bịa tên, chức danh, ngân sách, sản phẩm, giá, cam kết hoặc kinh nghiệm triển khai.
- Thiếu email, số điện thoại hoặc người liên hệ thì phải hướng dẫn xác minh, không tự tạo.
- Với tin tuyển dụng công nghệ, có thể tiếp cận bài toán mà vị trí đang tuyển cần giải quyết, nhưng phải dựa trên thông tin thật trong bài.

### A6. Quan hệ giữa keyword, prompt và scoring

```text
Google Sheets Keywords
        ↓
Prefilter: tìm keyword xuất hiện đúng theo ranh giới từ
        ↓
Gemini Extraction: kiểm tra keyword có đúng ngữ cảnh nhu cầu không
        ↓
Gemini Profile: bổ sung dữ liệu tổ chức có nguồn chính thức
        ↓
Gemini Scoring: chạy Relevance Gate trước khi cộng điểm
        ↓
Gemini Sales: chỉ tạo kịch bản theo action đã chọn
```

Điểm cần nhớ:

- Keyword không phải điểm số và không tự biến bài thành lead.
- XAH không chấm điểm và không quyết định bài có liên quan hay không.
- Gemini scoring là nơi quyết định điểm cuối cùng.
- Google Sheets chứa keyword và có thể chứa prompt scoring/Sales tùy cấu hình.
- Prompt Extraction, prompt tìm website và prompt Profile hiện nằm trong code; khi thay đổi cần cập nhật code và test lại pipeline.
- Mọi kết luận quan trọng phải quay về nội dung nguồn và URL minh chứng.

## 7. Gemini Scoring — chấm điểm cơ hội

Scoring do Gemini phụ trách, không phải XAH. XAH chỉ hỗ trợ tìm kiếm URL.

Gemini nhận các dữ liệu đã thu thập:

- Keyword nghiệp vụ hiện tại.
- Nội dung bài viết gốc.
- Kết quả Extraction.
- Hồ sơ tổ chức và website context nếu crawl được.
- Contact, project và evidence có nguồn.

Gemini phải chấm dựa trên mức độ liên quan thật với sản phẩm/keyword, không chấm chỉ vì tên doanh nghiệp lớn hoặc có từ khóa chung chung.

Các tín hiệu điểm cao thường là:

- Có mời thầu, RFQ hoặc nhu cầu mua rõ ràng.
- Có sản phẩm CNTT, phần mềm, license, cloud, dữ liệu, AI, bảo mật hoặc triển khai hệ thống.
- Có ngân sách, deadline và contact xác thực.
- Có bài tuyển dụng cho thấy nhu cầu công nghệ/chuyển đổi số cụ thể.

Các tín hiệu điểm thấp hoặc loại bỏ:

- Dự án cầu, đường, công viên không có hạng mục CNTT.
- Vật tư, van, chống sét, vật liệu hoặc tài sản không liên quan.
- Webinar/sự kiện chỉ mang tính tham dự, không có nhu cầu mua giải pháp.
- Tuyển dụng marketing thuần túy.
- Tin tức chung chung không cho thấy nhu cầu có thể tiếp cận.

Output scoring gồm điểm 0–100, nhóm ưu tiên và lý do. Backend kiểm tra JSON và giới hạn điểm 0–100; không tự thay thế điểm bằng luật hard-code.

Ngưỡng lưu nghiệp vụ hiện tại:

```text
score >= 40 → lưu Lead và dữ liệu liên quan
score < 40  → không lưu như cơ hội bán hàng
```

Một bài tin tức về AI/chuyển đổi số có thể vẫn được giữ làm tín hiệu nuôi dưỡng (`NURTURE`) dù chưa đủ điều kiện thành lead nóng. Điểm phải phản ánh đúng bằng chứng, không biến tin tức thành yêu cầu mua hàng.

## 8. Lưu dữ liệu và đồng bộ Google Sheets

Google Sheets là nơi lưu dữ liệu nghiệp vụ và keyword. SQLite chủ yếu phục vụ cache/chạy cục bộ.

Các tab nghiệp vụ chính gồm:

- `Leads`: cơ hội đã qua ngưỡng.
- `Keywords`: keyword và nhóm nhu cầu.
- `Sources`: nguồn crawl.
- `Organizations`: hồ sơ tổ chức.
- `Contacts`: người liên hệ.
- `Organization_Evidence`: minh chứng có URL.
- `Projects`: dự án hoặc nhu cầu.
- `News`, `Jobs`, `Tenders`: phân loại nội dung.
- `Interactions`: lịch sử tiếp cận.
- `Settings`: cấu hình nghiệp vụ.

Khi đồng bộ, URL tiếp tục được canonicalize. Vì vậy kiểm tra trùng trong Sheets cũng dựa trên URL, phù hợp với logic pipeline.

## 9. Cấu hình model và giới hạn

Các model hiện tại:

```text
Gemini extraction/profile/scoring:
GEMINI_MODEL=levuphong2909/gemini-3.7-flash-high

XAH Search:
XAH_SEARCH_MODEL=dungcsnd113/gpt-5.6-terra

XAH Search endpoint:
XAH_SEARCH_URL=https://api.xah.io/v1/search
```

Biến môi trường liên quan enrichment:

```text
COMPANY_XAH_RETRY_ATTEMPTS=5
COMPANY_PROFILE_MAX_PAGES=20
COMPANY_PROFILE_MAX_DEPTH=3
```

Không đưa API key vào tài liệu, log hoặc commit. API key chỉ nằm trong `.env` cục bộ.

## 10. File code chính

| File | Trách nhiệm |
|---|---|
| `app/services/crawler_service.py` | Điều phối pipeline chính |
| `app/services/gemini_service.py` | Gọi Gemini và xử lý output |
| `app/services/xah_search_service.py` | Gọi XAH và chuẩn hóa danh sách URL |
| `app/services/company_enrichment_service.py` | Tìm website chính thức, retry, crawl sâu, profile |
| `app/services/generic_website_adapter.py` | Crawl sitemap và link HTML cùng domain |
| `app/services/keyword_service.py` | Đọc keyword từ Google Sheets |
| `app/pipeline/dedup.py` | Chuẩn hóa và hash URL để chống trùng |
| `app/config.py` | Định nghĩa cấu hình từ environment |
| `tests/test_company_enrichment.py` | Test enrichment/retry/deep crawl |

## 11. Cách đọc một output test

Khi kiểm tra file JSON, đọc theo thứ tự:

1. `input.url`: URL bài đầu vào.
2. `pipeline_status`: pipeline có chạy đến cuối không.
3. `gemini_extraction`: Gemini hiểu bài gốc như thế nào.
4. `company_enrichment`: website nào được chọn, đã crawl bao nhiêu URL, có contact/evidence gì.
5. `scoring`: điểm, nhóm ưu tiên và lý do.
6. `persisted`: có được lưu vào Sheets/SQLite hay bị loại.

Các dấu hiệu cần kiểm tra:

- XAH trả website bên thứ ba → lỗi discovery/prompt hoặc parser.
- `source_urls` không cùng domain → lỗi kiểm soát domain.
- Có contact/evidence nhưng không có URL → output không đạt yêu cầu minh chứng.
- `score` cao nhưng bài chỉ là tin tức chung chung → cần xem lại prompt scoring.
- `PROFILE_INCOMPLETE` nhưng vẫn có nhiều `source_urls` chính thức → crawl đã chạy, chỉ có một phần trang không đủ nội dung.
- `xah_trace.crawl_attempts=0` trong một wrapper test không nhất thiết nghĩa là không crawl; test wrapper có thể chỉ bắt hàm search cũ. Hãy kiểm tra `company_enrichment.source_urls` và log Crawl4AI.

## 12. Test một URL đơn lẻ

Để test an toàn, dùng pipeline một URL thay vì chạy toàn bộ nguồn. Mục tiêu của test là kiểm tra đủ chuỗi:

```text
URL bài viết
→ extraction
→ tìm website chính thức nếu cần
→ crawl sitemap/link con
→ profile
→ scoring
→ JSON output
```

File output nên lưu trong:

```text
data/test_outputs/
```

Sau mỗi lần test, cần kiểm tra cả log và JSON. Đặc biệt xác nhận:

- URL XAH trả về có phải website chính thức không.
- Các URL crawl sâu có cùng domain không.
- Nội dung profile có lấy từ website thật không.
- Gemini có giữ lại đúng loại nhu cầu hay nhầm sang dự án không liên quan.
- Điểm có phù hợp với bằng chứng không.

## 13. Tóm tắt trách nhiệm từng model

| Model/dịch vụ | Làm gì | Không làm gì |
|---|---|---|
| XAH Search | Tìm URL website chính thức theo truy vấn | Không thay Gemini crawl và phân tích toàn bộ hồ sơ |
| Gemini Extraction | Đọc bài viết gốc, trích xuất trường nghiệp vụ | Không tự tạo bằng chứng không có trong bài |
| Gemini Profile | Đọc `website_context`, tổng hợp tổ chức/contact/project/evidence | Không được coi website bên thứ ba là website chính thức |
| Gemini Scoring | Chấm độ liên quan, ưu tiên và lý do | Không được nâng điểm chỉ vì có keyword chung chung |
| Crawl4AI / adapter | Tải trang, sitemap, link con và cung cấp text cho Gemini | Không tự hiểu nhu cầu kinh doanh hay tự chấm điểm |

## 14. Kết luận nghiệp vụ

Pipeline hiện tại đi theo nguyên tắc:

```text
Tìm đúng nguồn → crawl có kiểm soát → Gemini đọc đủ ngữ cảnh
→ giữ minh chứng → chấm đúng mức liên quan → chỉ lưu cơ hội đạt ngưỡng
```

Vì website có thể chặn crawler hoặc không có HTML tĩnh, “không lấy được dữ liệu” không đồng nghĩa tổ chức không có thông tin. Hệ thống phải giữ trạng thái chưa hoàn chỉnh, tránh bịa dữ liệu và không dùng các trang không chính thức để lấp chỗ trống.

## Phụ lục B — Ưu tiên request từ FE

Các request thao tác trực tiếp từ FE được bọc trong `fe_priority_context`. Khi context này hoạt động:

- Background scheduler và queue worker không mở bước crawl nặng mới.
- Background nhường trước lần `BrowserCrawlService.fetch()` kế tiếp.
- Nếu navigation background đang chạy dở khi FE acquire priority, chỉ navigation con bị hủy; crawl/enrichment cha không bị hủy toàn bộ và sẽ chờ để tiếp tục.
- Tác vụ FE dùng executor ưu tiên riêng cho các thao tác blocking như HTTP, Gemini và lưu dữ liệu.
- Middleware tự động áp dụng priority cho mọi HTTP request dưới `/api/*`; các endpoint mới không thể vô tình bỏ qua cơ chế này.
- Các endpoint crawl/import/probe vẫn có context tường minh ở tầng service để bảo vệ cả khi được gọi nội bộ.

Navigation Crawl4AI background đang chạy dở sẽ được preempt có kiểm soát khi FE acquire priority. Log có thể xuất hiện lỗi tạm dừng ở URL hiện tại; đây không phải lỗi nghiệp vụ cuối cùng. Sau khi FE hoàn tất, background tiếp tục ở boundary kế tiếp và không retry nóng cùng URL trong lúc FE đang bận.
