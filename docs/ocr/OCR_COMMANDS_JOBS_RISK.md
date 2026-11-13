# Rủi ro có sẵn: `POST /api/commands/jobs` — **ĐÃ KHẮC PHỤC trong Phase 8A**

> Trạng thái: **đã khắc phục** (Phase 8A). Chi tiết biện pháp và test:
> [`docs/security/BACKGROUND_JOB_SECURITY.md`](../security/BACKGROUND_JOB_SECURITY.md).
> Phần dưới giữ nguyên phân tích ban đầu để truy vết.

Phát hiện trong quá trình review OCR Engine Manager. **Không do tính năng OCR tạo ra** và
**không sửa trong Phase 7** (ảnh hưởng kiến trúc Background Job ngoài phạm vi). Tài liệu này mô tả
mức độ, các command bị ảnh hưởng và phương án khắc phục riêng.

## 1. Mô tả

`api/routers/commands.py` đăng ký vào `api/main.py` **không** có `Depends(require_admin)`.
Middleware JWT chỉ yêu cầu *đăng nhập*. Do đó **mọi tài khoản đã đăng nhập (kể cả role `user`)** có thể:

| Endpoint | Hành vi | Frontend có dùng? |
|---|---|---|
| `POST /api/commands/jobs` | Submit **bất kỳ** command đã đăng ký với **input tuỳ ý** | **Không** |
| `GET /api/commands/jobs/{id}` | Đọc trạng thái + `result` của **bất kỳ** job | Có (`lib/api/insights.ts`, theo dõi insight) |
| `DELETE /api/commands/jobs/{id}` | Huỷ **bất kỳ** job | **Không** |

## 2. Command bị ảnh hưởng (đăng ký trong `commands/`)

| Command | Input nguy hiểm | Tác động nếu bị lạm dụng | Mức độ |
|---|---|---|---|
| `process_source` | `content_state.file_path`, `delete_source`, `url`, `source_id` | (a) **Đọc file tuỳ ý** trên server (worker chạy root) vào nội dung một source mà người tấn công xem được; (b) **xoá file tuỳ ý** (`delete_source=true` ⇒ `os.unlink(file_path)` sau khi trích xuất thành công, ví dụ `.env`); (c) **SSRF** — `url` không đi qua `validate_url()` của API; (d) ghi đè nội dung source của người khác (`source_id` bất kỳ) | **Cao** |
| `run_transformation` | `source_id`, `transformation_id` | Chạy LLM tốn chi phí trên source bất kỳ, tạo insight không được phép | Trung bình |
| `create_insight` | `source_id`, `content` | Chèn insight tuỳ ý vào source của người khác | Trung bình |
| `rebuild_embeddings` | `mode=all` | Tốn tài nguyên/chi phí embedding toàn hệ thống (DoS chi phí) | Trung bình |
| `embed_source` / `embed_note` / `embed_insight` | id bất kỳ | Tốn chi phí, đánh chỉ mục dữ liệu chưa duyệt (bỏ qua quy trình approval) | Thấp–Trung bình |
| `generate_podcast` | `content`, profile | Tốn chi phí LLM/TTS, vượt quyền tắt podcast của admin | Trung bình |
| `ocr_install_model` / `ocr_test_engine` | `engine_id`, `nonce` | **Đã tự bảo vệ**: nonce 256-bit do API admin ghi, so sánh hằng thời gian, dùng một lần ⇒ bị từ chối | Đã giảm thiểu |

Lớp OCR mới **không mở rộng** bề mặt này: `process_source` vốn đã đưa `file_path`/`url` vào Content
Core; lớp OCR nhận đúng các giá trị đó (URL được Content Core tải bằng cùng helper), không thêm đường
vào mới.

## 3. Phương án khắc phục (đề xuất, triển khai riêng trước production)

1. **Ngay (ít rủi ro):** gắn `dependencies=[Depends(require_admin)]` cho `POST /commands/jobs` và
   `DELETE /commands/jobs/{id}` (frontend không dùng). Hoặc xoá hẳn `POST` nếu không có client nào cần.
2. **GET trạng thái:** giới hạn theo quyền sở hữu — chỉ trả job do chính user tạo (lưu `context.user_id`
   khi submit qua các router chuyên biệt) hoặc admin; tối thiểu là che `result` với non-admin.
3. **Phòng thủ chiều sâu trong `process_source`:** chấp nhận `file_path` chỉ khi nằm dưới
   `UPLOADS_FOLDER` (dùng cùng kiểm tra containment như `tests/test_source_path_containment.py`) và
   chạy lại `validate_url()` cho `url` trong worker.
4. **Test:** non-admin ⇒ 403 cho POST/DELETE; GET job của người khác ⇒ 404; `file_path` ngoài uploads ⇒
   job lỗi; theo mẫu `tests/test_ocr_engine_manager.py::TestOcrApiRequiresAdmin`.

Khuyến nghị: **coi mục 1 và 3 là điều kiện bắt buộc trước khi đưa bản có tính năng này lên production**
(rủi ro có sẵn từ trước, nhưng mức độ Cao).

## 4. Trạng thái khắc phục (Phase 8A)

| Đề xuất | Trạng thái |
|---|---|
| 1. POST/DELETE chỉ admin | **Xong** — toàn bộ router admin-only; POST bị tắt bằng allow-list rỗng (deny by default) |
| 2. GET trạng thái giới hạn | **Xong** — admin-only (frontend chỉ admin dùng); danh sách job không lộ payload |
| 3. Phòng thủ tại worker | **Xong** — `file_path` trong `UPLOADS_FOLDER` (canonical, chống symlink), kiểm tra lại trước khi xoá; `validate_url()` + pre-check từng bước redirect (lần tải thật vẫn tự theo redirect — xem `BACKGROUND_JOB_SECURITY.md` §5); `content_state`/id ràng buộc với bản ghi source |
| 4. Test | **Xong** — `tests/test_background_job_security.py` (57) |
