# Ghi chú phát hành — ChatBot5400 v1.1.0-rc.2 — Model Tesseract tùy biến và tự OCR toàn trang

Ngày phát hành: 2026-11-16 (Phase 10I) · Tag `v1.1.0-rc.2` · **GitHub Pre-release — không phải bản ổn định.**

| | |
|---|---|
| Phiên bản | `1.1.0-rc.2` (bản trước: `1.1.0-rc.1`; bản ổn định gần nhất: `1.0.8`) |
| Loại phát hành | **Pre-release** (Release Candidate) — không phải bản ổn định, không phải "Latest" |
| Nền | Open Notebook 1.14.0, Docling 2.129.0, Content Core 2.0.7 — **không đổi**; `uv.lock` và `Dockerfile` giống hệt rc.1 |
| Phát hành | **chỉ mã nguồn**; không kèm Docker image, cơ sở dữ liệu hay model (mục 7) |
| Cơ sở dữ liệu | không có migration |
| Triển khai | bản phát hành này **không** cập nhật hệ thống nào; cập nhật một nơi triển khai cần phê duyệt riêng |
| Nghiệm thu | [OCR_PHASE10H_REPORT.md](OCR_PHASE10H_REPORT.md) (tổng hợp), [OCR_PHASE10_REPORT.md](OCR_PHASE10_REPORT.md), [OCR_PHASE10G_REPORT.md](OCR_PHASE10G_REPORT.md) |

Đây là bản phát hành thử nghiệm để đánh giá. Mọi số đo chất lượng trong repository là trên tài liệu **tổng hợp**; bản
này **chưa** được thẩm định cho tài liệu nghiệp vụ thật. Gắn tag không cập nhật hệ thống nào: cập nhật một nơi triển
khai là việc riêng, theo [OCR_RC2_PRODUCTION_UPDATE_PLAN.md](OCR_RC2_PRODUCTION_UPDATE_PLAN.md).

## 1. Tính năng mới

1. **Custom Tesseract Model Manager.** Một model Tesseract tự fine-tune (`.traineddata`) được đưa vào hệ thống bằng
   lệnh quản trị chạy **trên máy chủ**; mỗi lần import là một **phiên bản** bất biến có manifest, kích thước và
   SHA-256 riêng. Không có chức năng upload model qua trình duyệt, không bao giờ tải model tùy biến từ Internet.
2. **Tesseract Vietnamese Agri** — lựa chọn thứ năm trong OCR Engine Manager, nhãn **Thử nghiệm**. Repository và
   image **không** chứa model: card ở trạng thái "Chưa cài đặt" cho tới khi quản trị viên import và kích hoạt một
   phiên bản.
3. **Quản lý phiên bản model:** `import` · `list` · `verify` · `activate` · `rollback` · `status` · `remove` bằng CLI;
   kích hoạt, rollback và kiểm tra cũng có trên card Agri (chỉ quản trị viên).
4. **Thay model không cần build lại image hay restart:** import và kích hoạt có hiệu lực cho tài liệu tiếp theo; tài
   liệu đang xử lý giữ phiên bản lúc nó bắt đầu. Model nằm trong thư mục dữ liệu nên giữ được qua restart, tạo lại
   container và nâng cấp image.
5. **Rollback model** về phiên bản trước bằng một lệnh hoặc một nút. Kết quả "Sẵn sàng offline" gắn với từng phiên
   bản (mã phiên bản + SHA-256), không dùng chung giữa các phiên bản.
6. **Tự OCR toàn trang cho PDF scan nằm dưới watermark chéo** — tính năng **opt-in**, mặc định **tắt**
   (`OCR_AUTO_FULL_PAGE_ON_WATERMARK`). Khi bật, một PDF scan mà Docling sẽ bỏ gần hết chữ OCR (do một dòng text hiển
   thị bị nghiêng phủ lên trang) được OCR ở chế độ toàn trang chính thức của Docling, **cho riêng tài liệu đó**, với
   cả năm engine. Tùy chọn Force Full Page đã lưu không bị thay đổi; tệp PDF không bị sửa.

## 2. Những gì không đổi

- **Engine mặc định vẫn là RapidOCR.** Engine đang chọn của một hệ thống không bị đổi khi nâng cấp; Agri không bao giờ
  được chọn tự động.
- Bốn lựa chọn cũ (RapidOCR, Tesseract Vietnamese Fast / Best, EasyOCR): cùng model, cùng checksum, cùng đường xử lý.
  Bộ benchmark pháp lý tổng hợp chạy lại cho 102 / 102 lượt giống hệt từng byte.
- Layout Heron, TableFormer Accurate, tiền xử lý PDF, cổng OSD, Force Full Page OCR, số luồng CPU.
- Embedding, RAG, Chat, Transformation, podcast, phân quyền người dùng, URL ingestion (vẫn tắt mặc định).
- Chỉ dùng các lớp và tham số chính thức của Docling; không sửa Docling hay Content Core, không monkey patch.

## 3. Bảo mật

- Mọi thao tác quản lý model (xem, kích hoạt, rollback, kiểm tra) qua API chỉ dành cho **quản trị viên**: tài khoản
  thường nhận 403, không có token nhận 401 (kiểm tra trực tiếp trên stack thử nghiệm).
- File model chỉ vào hệ thống qua CLI trên máy chủ: kiểm tra đường dẫn nguồn (không symlink, đúng đuôi, đúng cấu trúc
  `traineddata`), mã phiên bản chỉ gồm chữ, số, `-`, `_`; file được nạp thử bằng Tesseract và kiểm tra pipeline trước
  khi được coi là dùng được; mỗi tài liệu được xử lý với file đã đối chiếu SHA-256 với manifest.
- Cơ chế tự OCR toàn trang chỉ đọc hình học và số đếm của PDF: không đọc nội dung chữ, không so khớp tên hay chuỗi
  watermark; log chỉ gồm số đo (không có tên tệp, không có nội dung).
- **File model không thể tự đặt tham số nguy hiểm cho Tesseract.** Thành phần `config` nhúng trong một file
  `.traineddata` được Tesseract áp dụng mỗi lần nạp model; chỉ tham số tinh chỉnh nhận dạng trong danh sách cho phép,
  với giá trị số / boolean, được chấp nhận — kiểm tra trước khi Tesseract nạp file và ở mọi lần xác minh.
- Kho model từ chối liên kết tượng trưng trên mọi cấp đường dẫn; manifest / registry hỏng hoặc bị sửa tay được xử lý
  theo hướng đóng; bước đo PDF của cơ chế tự OCR toàn trang có giới hạn về trang, đối tượng, ký tự và thời gian.
- Hai phiên review độc lập (bảo mật; tính đúng đắn) trên toàn bộ diff `v1.1.0-rc.1..`: **0 phát hiện mức Cao**; mọi
  phát hiện mức Trung bình đã được sửa kèm test — [OCR_PHASE10H_REPORT.md](OCR_PHASE10H_REPORT.md) mục 3.
- Lịch sử commit của bản phát hành (từ `v1.1.0-rc.1`) không chứa model, dữ liệu huấn luyện, tài liệu nội bộ, nội dung
  OCR hay watermark của tài liệu thật, credential, tệp `.env`, bản sao lưu, địa chỉ IP nội bộ, đường dẫn máy chủ hay tên
  tài khoản thật: nhánh phát triển được gộp thành lịch sử sạch và quét lại toàn bộ (commit, diff, thông điệp commit, đối
  tượng Git) trước khi đưa lên GitHub. Đường dẫn dạng `/srv/example/…` trong tài liệu là **minh họa**.
- **Bộ test không thể chạm vào một cơ sở dữ liệu thật.** Các biến `SURREAL_*` thông thường không bao giờ chọn cơ sở dữ
  liệu của bộ test; mặc định mọi kết nối đi tới một cổng đóng; cơ sở dữ liệu dùng tạm phải được chỉ định riêng và chứng
  minh được tính cô lập, nếu không bộ test dừng trước khi chạy (`tests/README.md`).

## 4. Thay đổi hành vi khi nâng cấp từ v1.1.0-rc.1

Không có thay đổi nào buộc người vận hành phải làm gì:

1. OCR Engine Manager có thêm card *Tesseract Vietnamese Agri* ("Chưa cài đặt", Thử nghiệm).
2. Trường cài đặt engine nhận thêm giá trị `tesseract_agri`. **Trước khi hạ cấp** về rc.1, chọn lại một engine khác
   nếu Agri đang được chọn; nếu quên, bản cũ lặng lẽ dùng RapidOCR ([OCR_ROLLBACK.md](OCR_ROLLBACK.md)).
3. Trang đăng nhập hiển thị `1.1.0-rc.2`.
4. Không có biến môi trường bắt buộc mới. Các biến tùy chọn mới: `OCR_AUTO_FULL_PAGE_ON_WATERMARK` (mặc định tắt),
   `OCR_AUTO_FULL_PAGE_MIN_COVERAGE`, `OCR_AUTO_FULL_PAGE_TEXT_PAGE_CHARS`, `OCR_AUTO_FULL_PAGE_MIN_ANGLE`,
   `OCR_AGRI_WITH_ENGLISH` (mặc định tắt) — [OCR_CONFIGURATION.md](OCR_CONFIGURATION.md).
5. Publish một GitHub Release / Pre-release không còn khởi chạy việc build và push Docker image (mục 7).

## 5. Giới hạn đã biết

Tóm tắt:

- Tesseract Vietnamese Agri chỉ mang tính **thử nghiệm**.
- **Chưa chứng minh được** Agri tốt hơn Tesseract Vietnamese Best trên tài liệu nghiệp vụ thật.
- Tự OCR toàn trang (Auto Full Page) **mặc định tắt**.
- PDF hỗn hợp **chưa** được xử lý tự động hoàn toàn.
- Một số kiểu watermark **không** được phát hiện.
- OCR **không thay thế** việc đối chiếu tài liệu gốc.

Chi tiết của bản này:

- **Tesseract Vietnamese Agri là Thử nghiệm.** Trên văn bản pháp lý tổng hợp, chất lượng tổng thể tương đương
  Tesseract Vietnamese Best (CER pipeline 3,40% so với 3,51%); đọc số hiệu văn bản và chữ Đ tốt hơn nhưng đọc sai một
  phần giá trị phần trăm (20 / 28 so với 28 / 28). **Chưa** có số đo trên tài liệu nghiệp vụ thật, nên không có cơ sở
  để nói Agri tốt hơn Best. Lãi suất, tỷ lệ, số tiền phải được đối chiếu với bản gốc. Chất lượng phụ thuộc phiên bản
  model được import.
- **PDF hỗn hợp không được sửa tự động.** Tài liệu vừa có trang scan dưới watermark vừa có trang văn bản điện tử tốt
  giữ chế độ OCR đã cấu hình và ghi `WARNING` (Docling chỉ có một chế độ OCR cho cả tài liệu; ép toàn trang làm trang
  văn bản điện tử mất 1–2% số từ). Cách xử lý thủ công: bật Force Full Page OCR, xử lý lại riêng tệp đó, rồi tắt.
- Cơ chế tự OCR toàn trang **không** phát hiện watermark **ngang** cỡ lớn và khung bao nghiêng chiếm dưới 2% trang
  (còn mất khoảng 3 điểm phần trăm số từ), cũng như watermark được ghi mỗi ký tự một đối tượng text; các ngưỡng mới
  được hiệu chuẩn trên PDF tổng hợp và **một** tài liệu thật. Tài liệu vượt giới hạn đọc (2.000 trang; 20.000 đối
  tượng hoặc 100.000 ký tự trên một trang; 20 giây) giữ chế độ OCR đã cấu hình.
- Một model fine-tune mang tham số nhúng ngoài danh sách cho phép bị **từ chối import** cho tới khi tham số đó được
  xem xét (model của ngôn ngữ gốc `vie` đạt).
- Nghiệm thu trên tài liệu thật của cơ chế này là "nội dung tương đương Force Full Page thủ công" (chưa có ground
  truth để đo độ chính xác ký tự).
- Nguồn từ URL với cấu hình RapidOCR mặc định không đi qua cơ chế này (URL ingestion mặc định tắt).

Vẫn còn từ v1.1.0-rc.1 ([OCR_RELEASE_NOTES.md](OCR_RELEASE_NOTES.md) mục 5): chưa thẩm định chất lượng OCR trên tài
liệu nghiệp vụ thật; có thể sai dấu, sai chữ số, sai cấu trúc bảng; OCR không thay thế việc đối chiếu tài liệu gốc;
vận hành offline mới xác minh trên stack cô lập; EasyOCR chỉ mang tính thử nghiệm; CORS mở mặc định, container chạy
root, các route podcast mở cho mọi tài khoản.

## 6. Cài đặt, nâng cấp, vận hành, rollback

| Việc | Tài liệu |
|---|---|
| Cài đặt mới | [README](../../README.md) (Quick Start) → [OCR_ONLINE_PREPARATION.md](OCR_ONLINE_PREPARATION.md) (chuẩn bị engine) |
| Nâng cấp một hệ thống đang chạy lên rc.2 | [OCR_RC2_PRODUCTION_UPDATE_PLAN.md](OCR_RC2_PRODUCTION_UPDATE_PLAN.md) (riêng cho bản này) + [OCR_PRODUCTION_DEPLOYMENT_PLAN.md](OCR_PRODUCTION_DEPLOYMENT_PLAN.md) (sao lưu lạnh, kiểm tra restore) |
| Import, kích hoạt, thay và rollback model Agri | [OCR_AGRI_MODEL_GUIDE.md](OCR_AGRI_MODEL_GUIDE.md); thiết kế: [OCR_CUSTOM_MODEL_MANAGER.md](OCR_CUSTOM_MODEL_MANAGER.md) |
| Bật / tắt tự OCR toàn trang, đọc dòng log `OCR mode:` | [OCR_OPERATOR_GUIDE.md](OCR_OPERATOR_GUIDE.md), Phụ lục Phase 10G |
| Vận hành hằng ngày, chế độ bảo trì | [OCR_OPERATOR_GUIDE.md](OCR_OPERATOR_GUIDE.md) |
| Biến môi trường | [OCR_CONFIGURATION.md](OCR_CONFIGURATION.md) |
| Rollback (model, cờ, image) | [OCR_ROLLBACK.md](OCR_ROLLBACK.md), ghi chú Phase 10 và Phase 10G |

Thứ tự rollback, từ nhẹ tới nặng — không bước nào đụng tới dữ liệu:
(1) tắt cờ `OCR_AUTO_FULL_PAGE_ON_WATERMARK`; (2) `ocr custom rollback` hoặc chọn lại engine cũ trong OCR Engine
Manager; (3) hạ image về rc.1 (chọn engine khác Agri trước).

## 7. Phát hành và Docker image

Bản phát hành này là **mã nguồn**. Từ bản này, workflow *Build and Release* có một chốt chặn: trong repository này mọi
job build / push bị **bỏ qua** trừ khi (a) workflow được chạy tay (`workflow_dispatch`) **và** (b) biến repository
`CB5400_PUBLISH_IMAGES` bằng `true` (mặc định không tồn tại). Publish một Release hay Pre-release vì thế chỉ tạo ra
một lượt chạy có mọi job ở trạng thái "skipped": không build, không push, không lỗi.

Người phát hành cần biết:

- Chốt chặn nằm trong file workflow **của commit được gắn tag**. Tag `v1.1.0-rc.2` được tạo trên commit sau khi
  nhánh này đã merge. Một Release tạo trên commit cũ hơn vẫn chạy workflow cũ (trước đây: chạy và thất bại ở bước
  push, không phát hành được image nào).
- Kiểm tra sau khi publish: `gh run list --workflow build-and-release.yml --limit 1` — lượt chạy mới nhất phải có
  kết luận `skipped`.
- Muốn chắc chắn hơn nữa, có thể tạm tắt workflow trước khi publish (`gh workflow disable "Build and Release"`); đây
  là thao tác trên GitHub do chủ dự án thực hiện, không bắt buộc.
- Nếu sau này muốn phát hành image: tên image trong workflow vẫn là của dự án gốc và **phải** được đổi trước khi bật
  biến; đó là một thay đổi riêng, cần quyết định riêng.

## 8. Số liệu nghiệm thu tóm tắt

Chi tiết và nguồn số liệu: [OCR_PHASE10H_REPORT.md](OCR_PHASE10H_REPORT.md).

| Hạng mục | Kết quả |
|---|---|
| Tài liệu thật 5 trang (scan + watermark chéo), cờ bật | Agri 974 → 10.606 ký tự; Best 975 → 10.636; giống hệt từng byte Force Full Page thủ công |
| PDF thường khi cờ bật | 17 PDF tổng hợp + 7 fixture nghiệm thu giống hệt từng byte; benchmark pháp lý 102 / 102 lượt giống hệt |
| Thay model / rollback / nâng cấp image / hạ về rc.1 trên stack thử nghiệm | đạt ([OCR_PHASE10_REPORT.md](OCR_PHASE10_REPORT.md)) |
| Docker acceptance (nâng cấp từ rc.1, online → offline → restart → update) | 53 PASS / 0 FAIL |
| Hồi quy backend / frontend (chạy lại trên commit phát hành) | backend: 1.792 đạt · 10 lỗi · 64 bỏ qua — chỉ còn đúng 10 lỗi có sẵn của `v1.1.0-rc.1`; frontend 423 test đạt |
| Cô lập cơ sở dữ liệu của bộ test | 59 regression test; lượt chạy cuối không mở kết nối nào tới cổng cơ sở dữ liệu mặc định |
