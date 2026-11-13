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
| 8B | Nghiệm thu máy thật — lộ trình nhanh (§3, §4.1–4.3, §5) | §4.3 **FAIL** (4, OSD Tesseract); §5 **40/40 PASS** sau 3 bản sửa |
| 8B | Nghiệm thu máy thật — đầy đủ 4 engine (§4.3, §4.4, §5 từ production `5e04227`) | §4.3 33/48; §4.4 PASS; §5 53/55 (2 FAIL nội dung OCR) |
| 8B | Sửa P8B-1 (script), P8B-2 (readiness ProxyError — chặn), P8B-3 (treo 16 phút khi mất mạng — chặn, D-24) | DONE, có test hồi quy |
| 8B | Sửa P8B-8 (`OCR_RAPIDOCR_PERSISTENT=true` lỗi với backend torch) | DONE, có test hồi quy |
| 8B | Regression / frontend / lint / bảo mật trực tiếp / review độc lập | DONE (0 lỗi mới; 16/16; 0 High/Medium) |
| 8B | Benchmark full pipeline (`OCR_BENCHMARK.md` §6) | DONE |
| 8B | P8B-4 (OSD Tesseract), P8B-5 (ngưỡng EasyOCR) | **OPEN — cần quyết định** (`RELEASE_CANDIDATE.md` §6) |
| 8C | Preflight, bundle, bảo toàn commit 8B; lưu phần làm dở của phiên trước | DONE |
| 8C | Phân tích nguyên nhân gốc 15 bài (`OCR_FAILURE_ANALYSIS.md`) | DONE |
| 8C | Tesseract: gate OSD, chuẩn hóa hướng trang, scale theo DPI scan (D-25) | DONE — cần xác nhận ranh giới gate |
| 8C | EasyOCR ngưỡng 0,2 (D-26); RapidOCR tái dùng chuẩn hóa hướng trang | DONE |
| 8C | Holdout 13 tài liệu, so sánh trước/sau (`OCR_QUALITY_BENCHMARK.md`) | DONE, không regression |
| 8C | Full pipeline 48 bài | 38 PASS / 10 FAIL (8B: 33/15); còn lại là giới hạn model |
| 8C | Docker 4 engine online → offline → restart → update | 72 PASS / 1 FAIL (nội dung EasyOCR) |
| 8C | Regression / frontend / bảo mật trực tiếp / review độc lập | DONE (cùng 10 lỗi của `main`; 404/404; 16/16; 0 High, 3 Medium đã sửa) |
| 8C | Điều kiện merge §3.1 (`FAIL == 0` lộ trình nhanh) | **OPEN — 3 FAIL do giới hạn model; cần quyết định** (`OCR_PHASE8C_REPORT.md` §9) |
| 8D | Tiêu chí phát hành có điều kiện (`release_criteria.py`), xác minh KL-1 | DONE — Best: lỗi tiêu đề là duy nhất (3/3); Fast: không (thêm nhãn bảng) |
| 8D | Review `tesseract_gate.py` (11 điều kiện), `pdf_prep.py`; chốt chặn đệ quy/timeout | DONE |
| 8D | Phân loại chất lượng 4 lựa chọn: catalog, API, giao diện vi/en, tài liệu vi/en; cảnh báo EasyOCR | DONE |
| 8D | Trạng thái hướng trang trung thực; readiness theo cấu hình chất lượng | DONE |
| 8D | Bộ gốc 48 bài | 38 PASS / 10 FAIL (không đổi) |
| 8D | Docker: quick, 4 engine, RapidOCR persistent torch, image không Tesseract | DONE — xem `OCR_PHASE8D_REPORT.md` §7–8 |
| 8D | Regression / frontend / bảo mật | DONE — cùng 10 lỗi của `main`; 408/408; 16/16 |
| 8D | SSRF qua redirect | **OPEN — chặn production**, cần biện pháp được duyệt (D-28) |
| 8D | Trạng thái | READY FOR MERGE (có điều kiện) · READY FOR CONDITIONAL RELEASE · NOT READY FOR PRODUCTION |
