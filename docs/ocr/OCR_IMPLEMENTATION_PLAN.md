# OCR Implementation Plan (Phase 0 output, cập nhật theo thực tế)

## 1. Cơ chế tích hợp tối thiểu

1. `ContentSettings` + 4 trường OCR có mặc định (không migration).
2. `open_notebook/graphs/source.py::content_process`: nạp Settings mới mỗi job; nếu file
   PDF/ảnh đi Docling **và** cấu hình OCR khác mặc định ⇒ `open_notebook/ocr/docling_extract.py`;
   còn lại giữ nguyên `content_core.extract_content`.
3. `docling_extract.py`: cùng `PdfPipelineOptions` như Content Core + `ocr_options`
   (+ `accelerator_options` khi đặt số luồng); test parity bảo vệ.
4. Engine catalog ghim cứng; installer model (job worker); runtime qua build arg/entrypoint/CLI.
5. API admin `/api/ocr/*`; UI trong trang Settings.

## 2. File sửa / tạo

| Loại | File |
|---|---|
| Sửa (backend) | `open_notebook/domain/content_settings.py`, `open_notebook/graphs/source.py`, `api/models.py`, `api/main.py`, `api/routers/settings.py`, `commands/__init__.py`, `pyproject.toml` (package-data) |
| Mới (backend) | `open_notebook/ocr/*`, `api/ocr_service.py`, `api/routers/ocr.py`, `commands/ocr_commands.py` |
| Sửa (frontend) | `settings/page.tsx`, `settings/page.test.tsx`, `lib/types/api.ts`, `lib/api/query-client.ts`, `lib/locales/{en-US,vi-VN}/index.ts` |
| Mới (frontend) | `settings/components/OcrEngineManager.tsx` (+ test), `lib/api/ocr.ts`, `lib/hooks/use-ocr.ts` |
| Hạ tầng | `Dockerfile`, `scripts/docker-entrypoint.sh`, `docker-compose.yml`, `deploy/docker-compose.prod.yml`, `.env.example` |
| Script | `scripts/ocr/generate_samples.py`, `scripts/ocr/benchmark.py`, `scripts/ocr/docker-acceptance.sh` |
| Test | `tests/test_ocr_engine_manager.py`, `test_ocr_bundle_cli.py`, `test_ocr_docling_parity.py`, `test_ocr_source_graph.py`, `test_ocr_integration.py` |

## 3. Kế hoạch kiểm thử

Unit (không mạng) → parity Content Core → routing source graph → tích hợp engine thật (OCR
stage) → offline bundle thật (mạng bị chặn) → frontend unit/lint/tsc/build → regression toàn bộ
backend so với commit gốc → Docker (nếu Cloud cho phép) → benchmark. Kết quả:
`OCR_TEST_REPORT.md`.

## 4. Rủi ro & phương án

| Rủi ro | Phương án |
|---|---|
| Content Core nâng cấp đổi options | Test parity fail ⇒ căn chỉnh hoặc bỏ lớp D-02 |
| Docling nâng cấp đổi Auto/API | Test thứ tự Auto + probe API ⇒ trạng thái `incompatible` |
| VPS cài Docling phiên bản khác lock | Probe lúc chạy, báo rõ |
| Cài EasyOCR làm Auto đổi engine | Ghim RapidOCR (D-03) |
| Mất runtime khi recreate | Build arg / entrypoint / bundle staged |
| Rollback | `OCR_ROLLBACK.md` |
