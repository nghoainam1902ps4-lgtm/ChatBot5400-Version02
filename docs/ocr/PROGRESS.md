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
