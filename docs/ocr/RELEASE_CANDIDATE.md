# Release Candidate — OCR Engine Manager (Phase 0 → 8A)

- **Branch:** `claude/friendly-mendel-a2b6m5`.
- **Gốc so sánh:** `5e04227` (trước tính năng) và `e32eae8` (Phase 7).
- **Không merge main, không triển khai production** trong phiên phát triển.

Trạng thái: **RELEASE CANDIDATE — CHƯA ĐỦ ĐIỀU KIỆN PRODUCTION.** Mã, test và tài liệu đã hoàn tất,
nhưng nghiệm thu runtime trên máy thật (mục 3) chưa chạy vì Cloud chặn mạng. Không được coi test mô
phỏng (mock / stub) là nghiệm thu runtime.

## 1. Đã xác nhận (có bằng chứng thực tế)

| Hạng mục | Bằng chứng |
|---|---|
| 3 engine / 4 lựa chọn, chỉ dùng class OCR chính thức của Docling; Layout Heron / TableFormer không đổi; RapidOCR mặc định không đổi | `ACCEPTANCE_CHECKLIST.md` |
| OCR tiếng Việt thật qua Docling (OCR stage): Tesseract Fast / Best, EasyOCR trên CPU | `OCR_TEST_REPORT.md` §2.3; `OCR_BENCHMARK.md` |
| Cài model theo nhu cầu, ghim checksum, lưu bền vững, offline bundle (máy air-gapped) | §2.1–2.2 Test Report |
| Khoá dependency theo `uv.lock` + guard tương thích | D-14; 12 test |
| Bảo mật job nền: `/api/commands/*` chỉ admin, tắt submit tổng quát, worker kiểm tra lại đầu vào | ADR-014, D-19; 57 test với file canary |
| Readiness không bao giờ dựa vào file; kết quả lỗi thời khi phiên bản / cache / trọng số đổi | D-20; 32 test; chạy thật: `prepare` trả `not_offline_ready` đúng khi HF bị chặn |
| RapidOCR lưu bền vững qua `Global.model_root_dir` | Chạy thật với onnxruntime khi mạng bị chặn |
| Regression | 1044 passed / 10 failed so với 951 / 10 ở `e32eae8`: cùng 10 lỗi có sẵn, 0 lỗi mới |
| Frontend | tsc 0 lỗi, lint 0 error, vitest 404 passed, build PASS |
| Tài liệu | `OCR_ONLINE_PREPARATION.md`, `OCR_LOCAL_ACCEPTANCE.md` (lệnh qua `bash -n`); ShellCheck sạch |

## 2. NOT VERIFIED (chưa chạy thật — lý do: mạng Cloud)

| Hạng mục | Chặn bởi | Cách nghiệm thu |
|---|---|---|
| Full pipeline Docling (Heron + TableFormer + OCR) với cả 4 engine, 7 fixture có ground truth | huggingface.co 403 | `OCR_LOCAL_ACCEPTANCE.md` §4.3 |
| Prepare online → `offline_ready` → `offline_verified` | huggingface.co, modelscope.cn 403 | §4.4 |
| RapidOCR backend torch (production), mặc định và `OCR_RAPIDOCR_PERSISTENT=true` | modelscope.cn 403 | §4.4, §5 |
| Docker: cập nhật online từ bản đang chạy → chuẩn bị → offline (mọi engine) → restart offline → cập nhật online + rebuild thật | Docker Hub 429, ghcr 403, Debian apt 403 | §5 |
| API + worker E2E thật (upload → xử lý → Markdown) | tải SurrealDB binary bị chính sách phiên từ chối | §5 (chạy cùng script) |
| Benchmark full pipeline | huggingface.co | §8 |

## 3. Điều kiện trước khi merge `main`

1. Chạy `OCR_LOCAL_ACCEPTANCE.md` lộ trình **nhanh** (Tesseract Best). Kết quả bắt buộc:
   - §4.3: `FAIL == 0`;
   - §5: không có dòng `FAIL`.
2. Đọc lại diff `e32eae8..HEAD`, đặc biệt `api/routers/commands.py` và `open_notebook/utils/job_input_guard.py`.
   Thay đổi ở commands là **thay đổi hành vi**: script ngoài nào gọi `POST /api/commands/jobs` sẽ bị từ chối.
3. Xác nhận lại trên máy thật: 10 lỗi test có sẵn (`test_models_api` ×9, `test_domain` ×1) đều có ở
   `main`, không phải do branch này.

## 4. Điều kiện trước khi triển khai production

1. Lộ trình nghiệm thu **đầy đủ**: 4 engine; Docker §5 với `OLD_REF` = commit production thật. Mọi bước
   PASS, không có NOT VERIFIED ngoài engine cố ý bỏ qua.
2. Benchmark trên tài liệu thật **làm cục bộ**, không đưa lên GitHub. Chọn engine trong Settings dựa trên
   kết quả benchmark.
3. Backup trước khi cập nhật: `notebook_data` và `surreal_data`. **Không** dùng `docker compose down -v`.
4. Quy trình vận hành:
   - cập nhật khi online;
   - `prepare` cho engine dùng thật;
   - chờ trạng thái `offline_ready`;
   - ngắt Internet;
   - `readiness --check` ⇒ `offline_verified`.

   Chi tiết: `OCR_ONLINE_PREPARATION.md`.
5. Nếu container có thể bị recreate trong lúc offline: đặt `OCR_OFFLINE=true`. Nếu dùng RapidOCR, chạy
   `prepare` lại sau mỗi lần recreate khi có mạng, hoặc bật `OCR_RAPIDOCR_PERSISTENT=true` sau khi đã nghiệm
   thu chế độ này (backend torch).
6. Hạn chế đã biết (dev defaults, không đổi trong phạm vi này): CORS mở, auth mật khẩu đơn giản, image
   chạy root.
7. Kế hoạch rollback đã đọc: `OCR_ROLLBACK.md`. Volume giữ nguyên; bản cũ bỏ qua dữ liệu OCR.

## 5. Phạm vi không hứa

- LLM / embedding offline: phụ thuộc nhà cung cấp mô hình.
- Cài đặt / cập nhật hoàn toàn offline: không bắt buộc. Offline bundle chỉ giữ cho máy air-gapped.
- GPU: mọi engine được cấu hình và kiểm thử trên CPU.
