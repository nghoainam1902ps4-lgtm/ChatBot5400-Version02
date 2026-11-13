# Progress

| Phase | Nhiệm vụ | Trạng thái |
|---|---|---|
| 0 | Khảo sát repo, phiên bản, luồng PDF, khả năng Content Core, khả năng Cloud | DONE |
| 0 | `OCR_ARCHITECTURE_AUDIT.md`, `OCR_IMPLEMENTATION_PLAN.md`, `DECISIONS.md` | DONE |
| 1 | Trường cấu hình OCR trong ContentSettings (không migration) | DONE |
| 1 | Ánh xạ engine → class Docling chính thức; RapidOCR ghim như Auto | DONE |
| 1 | Lớp tối thiểu truyền `ocr_options` + test parity Content Core | DONE |
| 1 | Tesseract Fast/Best (TESSDATA_PREFIX cố định, `configs/tsv`) | DONE |
| 1 | EasyOCR vi+en CPU, không tải khi xử lý | DONE |
| 1 | Lỗi rõ ràng, không fallback ngầm; worker đọc Settings mỗi job | DONE |
| 2 | Catalog ghim URL/sha256/size; installer staging/resume/lock/disk/smoke | DONE |
| 2 | Vòng đời trạng thái, chống tải trùng, phát hiện job chết | DONE |
| 2 | Gỡ model có bảo vệ (active, đang cài, osd dùng chung) | DONE |
| 3 | API admin `/api/ocr/*`, job worker + nonce | DONE |
| 3 | UI OCR Engine Manager (vi/en), test, screenshot | DONE |
| 4 | CLI quản trị, runtime install/ensure, offline bundle | DONE |
| 4 | Entrypoint, Dockerfile build arg, compose, `.env.example` | DONE |
| 5 | Unit / parity / routing / integration (OCR stage thật) | DONE |
| 5 | Benchmark OCR stage | DONE |
| 5 | Benchmark & integration full pipeline | BLOCKED (huggingface.co bị chặn) — script sẵn sàng |
| 5 | Docker test | BLOCKED (mạng Cloud) — `scripts/ocr/docker-acceptance.sh` |
| 5 | Regression backend + frontend | DONE (4 file cần tiktoken: BLOCKED do mạng) |
| 6 | Security review, tài liệu bàn giao, rollback | DONE |
| 6 | Review độc lập toàn bộ diff | DONE (xem CHECKPOINT) |
| 7 | Khoá dependency (constraints từ uv.lock, extra ocr-easyocr) + guard tương thích | DONE |
| 7 | Review & parity hành vi docling_extract với Content Core; sửa ảnh khi OCR tắt | DONE |
| 7 | Fixture nghiệm thu có ground truth + full pipeline strict mode | DONE (chạy thật: BLOCKED — HF) |
| 7 | Viết lại Docker acceptance (internal network, rebuild thật, upgrade, E2E API+worker) | DONE (chạy thật: BLOCKED — registry/apt) |
| 7 | CPU mode (RapidOCR opt-in CPU, EasyOCR device thật) | DONE |
| 7 | Security bổ sung + tài liệu `/api/commands/jobs` | DONE |
| 7 | `OCR_LOCAL_ACCEPTANCE.md` + kiểm tra cú pháp lệnh | DONE |
| 8A | Bảo mật job nền: commands chỉ admin, tắt submit tổng quát, guard trong worker, 57 test | DONE |
| 8A | Prepare online + readiness (`online`/`local_only`/`offline`, fingerprint, CLI, job, API) | DONE (chạy thật trong Cloud: `not_offline_ready` đúng vì HF bị chặn) |
| 8A | RapidOCR: warm-up mặc định, `OCR_RAPIDOCR_PERSISTENT` tuỳ chọn | DONE (onnx kiểm chứng; torch BLOCKED — modelscope) |
| 8A | UI trạng thái sẵn sàng + nút Chuẩn bị / Kiểm tra (vi/en); lỗi rõ khi thiếu model offline | DONE |
| 8A | Docker acceptance: cập nhật online → chuẩn bị → offline → restart offline → cập nhật online | DONE (chạy thật: BLOCKED — registry/apt) |
| 8A | Regression so với `e32eae8` | DONE (0 lỗi mới) |
| 8A | Tài liệu (`OCR_ONLINE_PREPARATION.md`, cập nhật bộ docs/ocr, `RELEASE_CANDIDATE.md`) | DONE |
