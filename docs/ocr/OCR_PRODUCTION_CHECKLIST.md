# Checklist triển khai production — OCR Engine Manager RC1

Cập nhật: 2026-11-14 (Phase 9B/9C). Dùng cùng [OCR_PRODUCTION_DEPLOYMENT_PLAN.md](OCR_PRODUCTION_DEPLOYMENT_PLAN.md).
Người vận hành đánh dấu từng dòng. Một dòng "Bắt buộc" không đạt ⇒ dừng. Kết quả thực tế của đợt triển khai
được ghi trong `OCR_PHASE9C_REPORT.md`, không ghi vào file này (file công khai, không chứa đường dẫn sao lưu).

## A. Trước ngày triển khai

| # | Việc | Bắt buộc | Kết quả / người ký |
|---|---|---|---|
| A1 | PR đã merge vào `claude/practical-wozniak-9s1t6z`; chủ dự án phê duyệt kế hoạch và commit merge | Có | |
| A2 | Benchmark tài liệu nghiệp vụ thật do người vận hành thực hiện tại chỗ, có biên bản số liệu tổng hợp — **hoặc** chủ dự án phê duyệt rõ phạm vi thí điểm phi nghiệp vụ (engine đang dùng vẫn là RapidOCR cho tới khi có biên bản) | Có | |
| A3 | Chấp nhận các giới hạn đã biết: KL-1 (tiêu đề in đậm), lỗi dấu ở tiêu đề/nhãn trên holdout, RapidOCR mất dấu, EasyOCR thử nghiệm, Tesseract Fast chưa đạt chuẩn nghiệp vụ | Có | |
| A4 | Quyết định cấu hình URL ingestion: **tắt** (hoặc biện pháp bổ sung được phê duyệt nếu bật) | Có | |
| A5 | Cửa sổ bảo trì đã thông báo cho người dùng | Có | |
| A6 | Dung lượng đĩa đủ (kế hoạch §2.5) | Có | |
| A7 | Người thực hiện và người giám sát đã đọc kế hoạch và `OCR_ROLLBACK.md` | Có | |
| A8 | Đánh giá các hạn chế dev-default cho môi trường đích (kế hoạch §13): khóa, xác thực, tài khoản DB, CORS, cổng, người dùng chạy container | Có | |
| A9 | Biện pháp kiểm soát URL ingestion và phân quyền khi phải rollback về bản cũ (kế hoạch §10) đã được phê duyệt | Có | |
| A10 | Có tài khoản kiểm thử (quản trị viên + người dùng thường) cho smoke test | Có | |
| A11 | Image RC đã dựng sẵn ở thư mục riêng, tag riêng, có Tesseract (kế hoạch §3) | Có | |

## B. Backup và restore

| # | Việc | Bắt buộc | Kết quả |
|---|---|---|---|
| B1 | Ghi commit, `git status`, diff cục bộ, image ID hiện tại | Có | |
| B2 | Gắn tag riêng cho image hiện tại `chatbot5400:rollback-pre-ocr-<ts>`; ghi ID image ứng dụng và image DB | Có | |
| B3 | Ghi số bản ghi trước khi dừng; `docker compose stop` (không `down`, không `-v`); tar `notebook_data` và `surreal_data` bằng container root mount chỉ đọc; `SHA256SUMS`; kiểm tra đọc được archive; thư mục sao lưu quyền `700` | Có | |
| B4 | Sao lưu `.env` / bí mật theo quy định riêng | Có | |
| B5 | Kiểm tra restore trên stack cô lập (mạng internal, không cổng, không Internet): `/health` 200, xác thực bật, số bản ghi bằng production, credential giải mã được; diễn tập khởi động image RC trên bản sao | Có | |
| B6 | Dọn stack restore-test (không `-v`) | Có | |

## C. Cập nhật

| # | Việc | Bắt buộc | Kết quả |
|---|---|---|---|
| C1 | Máy chủ có Internet | Có | |
| C2 | Cập nhật mã bằng `git merge --ff-only <commit merge>`; thay đổi cục bộ giữ bằng `git stash` / `git stash pop`; không `reset --hard` | Có | |
| C3 | Cấu hình: `OPEN_NOTEBOOK_ENABLE_URL_INGESTION=false`; Docling bật; bỏ `UV_OFFLINE`, `UV_EXCLUDE_NEWER`, `HF_HUB_OFFLINE` khỏi override; `OCR_INSTALL_TESSERACT=true` trong `.env` | Có | |
| C4 | Không bật `OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR` | Có | |
| C5 | Gắn image RC đã dựng sẵn thành `chatbot5400:local` (image cũ còn dưới tag rollback) | Có | |
| C6 | `docker compose start surrealdb` (cùng container, cùng image) rồi `docker compose up -d --no-deps --no-build open_notebook`; `/health` 200; không restart lặp; số bản ghi không đổi | Có | |
| C7 | OCR Engine Manager không báo "phiên bản phụ thuộc khác bộ đã kiểm chứng" | Có | |

## D. Chuẩn bị OCR

| # | Việc | Bắt buộc | Kết quả |
|---|---|---|---|
| D1 | Tesseract Vietnamese Best: Cài đặt → "Sẵn sàng" | Có | |
| D2 | Chuẩn bị → `offline_ready` | Có | |
| D3 | Kiểm tra (Test) thành công, model thực tế `TesseractOcrCliModel` | Có | |
| D4 | "Tự sửa hướng trang scan": Khả dụng | Không | |
| D5 | Chọn "Sử dụng" Tesseract Vietnamese Best | Theo quyết định A2 | |
| D6 | Xác minh offline trên stack cô lập bằng image triển khai. Trên production: chỉ khi quy trình ngắt mạng được phê duyệt → Kiểm tra offline → `offline_verified` | Stack cô lập: Có · Production: nếu được duyệt | |
| D7 | Nếu offline + RapidOCR + có thể recreate: `OCR_RAPIDOCR_PERSISTENT=true` trước D2 | Nếu áp dụng | |

## E. Smoke test (tài liệu không nhạy cảm)

| # | Việc | Bắt buộc | Kết quả |
|---|---|---|---|
| E1 | Đăng nhập admin và người dùng thường | Có | |
| E2 | Dữ liệu cũ hiển thị đủ | Có | |
| E3 | Upload PDF có text layer | Có | |
| E4 | Upload PDF scan tiếng Việt: số hiệu và số tiền đúng; log ghi đúng engine | Có | |
| E5 | Upload PDF scan có bảng: đủ dòng, số tiền và ngày đúng | Có | |
| E6 | Upload trang scan nằm ngang | Không | |
| E7 | Nhập văn bản thủ công | Có | |
| E8 | "Thêm URL" bị vô hiệu hóa; API trực tiếp trả 403 | Có | |
| E9 | Embedding + tìm kiếm trên tài liệu mới | Có | |
| E10 | Chat / RAG có trích dẫn nguồn | Có | |
| E11 | Người dùng thường bị 403 ở API OCR / commands / ghi credential / ghi model | Có | |
| E12 | Log 15 phút không có lỗi lặp lại | Có | |
| E13 | Xóa tài liệu thử | Có | |

## F. Tiêu chí dừng và rollback

| # | Điều kiện | Hành động |
|---|---|---|
| F1 | B3 hoặc B5 không đạt | Dừng, không triển khai |
| F2 | C6 không đạt trong 15 phút | Rollback mã |
| F3 | E1, E2, E3, E7, E9, E10 hoặc E11 không đạt | Rollback mã |
| F4 | E8 không đạt (URL vẫn thêm được) | Rollback mã |
| F5 | C7 không đạt | Rollback mã |
| F6 | Chỉ E4–E6 không đạt | Chuyển lại RapidOCR, ghi nhận, không bắt buộc rollback |
| F7 | Dữ liệu hỏng | Rollback dữ liệu — cần chủ dự án quyết định |

## G. Sau triển khai

| # | Việc | Kết quả |
|---|---|---|
| G1 | Theo dõi 24 giờ: `scripts/ocr/production_health_check.sh`, log, thời gian xử lý, RAM | |
| G2 | Giữ backup và image rollback ≥ 30 ngày | |
| G3 | Ghi commit, image ID, kết quả smoke test vào `CHECKPOINT.md` | |
| G4 | Dọn tài nguyên nghiệm thu sau khi được phê duyệt | |
