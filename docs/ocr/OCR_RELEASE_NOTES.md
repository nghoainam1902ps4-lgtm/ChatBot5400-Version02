# Ghi chú phát hành — OCR Engine Manager

Cập nhật: 2026-11-14 · Branch phát hành: `release/ocr-engine-manager-rc1` → `claude/practical-wozniak-9s1t6z`

Chưa gắn số phiên bản và chưa tạo tag / GitHub Release: quy ước đánh số cho bản này do chủ dự án quyết định.
Số liệu nghiệm thu: [OCR_PHASE9B_REPORT.md](OCR_PHASE9B_REPORT.md). Mọi số đo chất lượng là trên tài liệu
**tổng hợp**.

## 1. Tính năng

- **OCR Engine Manager** trong *Cài đặt* (chỉ quản trị viên): cài, chuẩn bị, kiểm tra, chọn và gỡ engine OCR
  cho tài liệu scan; hiển thị riêng ba trạng thái *Sẵn sàng*, *Đã xác minh offline*, *Chất lượng*.
- **Bốn lựa chọn trên ba engine**, đều chạy CPU:

  | Lựa chọn | Phân loại | Ghi chú |
  |---|---|---|
  | Tesseract Vietnamese Best | Khuyến nghị cho tiếng Việt | `vie` + `eng` (tessdata_best) |
  | Tesseract Vietnamese Fast | Ưu tiên tốc độ | chưa đạt chuẩn nghiệp vụ |
  | RapidOCR – PaddleOCR | Mặc định, tương thích ngược | model và cấu hình không đổi |
  | EasyOCR Vietnamese | Thử nghiệm | hỏi xác nhận trước khi bật |

- **Chất lượng tiếng Việt với Tesseract:** lọc kết quả dò hướng độ tin cậy thấp, tự sửa trang scan nằm ngang
  hoặc lộn ngược, độ phân giải OCR theo độ phân giải scan.
- **Chuẩn bị online, vận hành offline:** "Chuẩn bị" tải phần còn thiếu khi có Internet rồi chạy lại toàn bộ
  pipeline với mạng bị chặn; chỉ khi đó mới báo `offline_ready`. Xử lý tài liệu (OCR, Layout Heron,
  TableFormer, xuất Markdown) chạy được khi không có Internet, kể cả sau restart.
- **Lưu trữ bền:** model OCR (kiểm SHA-256) và cache Docling nằm trên thư mục dữ liệu, không tải lại sau
  restart, tạo lại container hay cập nhật.
- **Công cụ benchmark cục bộ** cho tài liệu của đơn vị, chỉ xuất số liệu tổng hợp.

## 2. Kiến trúc

- Chỉ dùng các lớp OCR chính thức của Docling 2.129.0 (`RapidOcrOptions`, `TesseractCliOcrOptions`,
  `EasyOcrOptions`); không adapter tự viết, không sửa Docling hay Content Core 2.0.7, không monkey patch.
- Layout Heron, TableFormer accurate, PDF backend giữ nguyên.
- Phiên bản phụ thuộc khóa theo `uv.lock`; lệch phiên bản ⇒ engine khác RapidOCR báo `incompatible`, đường mặc
  định vẫn chạy.
- Cấu hình mặc định (RapidOCR, không tinh chỉnh) vẫn đi nguyên đường Content Core như trước.
- Không có migration cơ sở dữ liệu.

## 3. Bảo mật

- **Thêm nguồn từ URL mặc định bị tắt** (`OPEN_NOTEBOOK_ENABLE_URL_INGESTION`), thực thi ở API, worker, graph
  và lớp OCR, cho mọi vai trò. Đây là giảm thiểu rủi ro SSRF bằng cách vô hiệu hóa chức năng, **không** phải
  bản vá toàn diện cho bộ tải HTTP; bật lại thì rủi ro còn lại xuất hiện trở lại.
- API job nền tổng quát bị khóa; worker kiểm tra lại đường dẫn file, URL và id bản ghi.
- **Phân quyền ở backend** cho credential nhà cung cấp, model, transformation, embed / dựng lại embedding, xóa
  insight: chỉ quản trị viên. Người không phải quản trị viên không còn tạo được nguồn từ một file đã nằm sẵn
  trên máy chủ.
- Model tải về: HTTPS, URL cố định, kiểm host ở từng bước redirect, ghim kích thước và SHA-256.

## 4. Thay đổi hành vi khi nâng cấp — cần đọc

1. Thêm nguồn từ URL (kể cả YouTube) bị từ chối cho tới khi đặt `OPEN_NOTEBOOK_ENABLE_URL_INGESTION=true`.
   Nguồn URL cũ vẫn đọc, tìm kiếm, chat được; không xử lý lại được.
2. Tài khoản không phải quản trị viên gọi trực tiếp các API quản lý credential / model / transformation /
   embedding nhận 403 (giao diện vốn đã ẩn các trang này).
3. `POST /api/commands/jobs` luôn bị từ chối.
4. Lần khởi động đầu của image mới phải có Internet (cài Docling đúng phiên bản đã khóa).
5. Sau nâng cấp, chạy "Chuẩn bị" một lần cho engine đang dùng.

## 5. Giới hạn đã biết

- Bộ nghiệm thu gốc 48 bài: **38 PASS / 10 FAIL** (không phải 48/48). Tesseract Best: 6/9 ở bộ gốc; đạt tiêu
  chí phát hành có điều kiện 7/7 với ngoại lệ duy nhất đã được chấp nhận: mất dấu ở tiêu đề in đậm
  `BẢNG KÊ CHI TIẾT KHOẢN MỤC MẪU`. Ngoại lệ không áp dụng cho số tiền, ngày, số hiệu, giá trị và nhãn dòng
  bảng, nội dung nghiệp vụ.
- Trên tập holdout, lỗi dấu ở tiêu đề / nhãn in đậm xuất hiện ở 4/13 tài liệu với Tesseract Best.
- Tesseract Fast: có thể sai dấu ở nhãn dòng bảng. RapidOCR: mất dấu tiếng Việt trên trang scan. EasyOCR: sai
  chữ số và dấu ở scan 150 DPI — không dùng cho tài liệu tài chính.
- Số liệu OCR từ tài liệu scan phải được đối chiếu với bản gốc trước khi dùng cho nghiệp vụ.
- Chưa có số đo trên tài liệu nghiệp vụ thật trong repository (do người vận hành thực hiện tại chỗ).
- Dò hướng trang: tối đa 200 trang scan và 600 giây mỗi tài liệu; phần còn lại giữ nguyên hướng.
- RapidOCR lưu bền (`OCR_RAPIDOCR_PERSISTENT=true`): sau khi tạo lại container vẫn cần "Chuẩn bị" một lần khi
  có Internet (file từ điển của RapidOCR nằm trong container).
- Cài runtime online ghim phiên bản nhưng không ghim hash.
- LLM / embedding offline phụ thuộc nhà cung cấp; cài đặt và cập nhật luôn cần Internet.
- Hạn chế có sẵn, không đổi: CORS mở mặc định, container chạy root, các route podcast mở cho mọi tài khoản.

## 6. Nâng cấp và rollback

- Nâng cấp: [OCR_PRODUCTION_DEPLOYMENT_PLAN.md](OCR_PRODUCTION_DEPLOYMENT_PLAN.md) (sao lưu lạnh, kiểm tra
  restore, cập nhật, chuẩn bị, smoke test) và [OCR_PRODUCTION_CHECKLIST.md](OCR_PRODUCTION_CHECKLIST.md).
- Vận hành: [OCR_OPERATOR_GUIDE.md](OCR_OPERATOR_GUIDE.md).
- Rollback: [OCR_ROLLBACK.md](OCR_ROLLBACK.md). Rollback nhanh không đổi mã: chọn lại RapidOCR. Rollback mã về
  bản trước giữ nguyên dữ liệu, nhưng URL ingestion hoạt động trở lại và mất các bản vá phân quyền.
