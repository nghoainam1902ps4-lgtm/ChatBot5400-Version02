# Checkpoint

- **Phase hiện tại:** 7 (hardening & acceptance readiness) hoàn tất trong Cloud; chờ nghiệm thu máy thật.
- **Repository:** nghoainam1902ps4-lgtm/ChatBot5400-Version02
- **Branch:** `claude/friendly-mendel-a2b6m5` (đã push; không merge main)
- **Commit gốc (rollback):** `5e042279439302d3ccf39bef4d1d8d402314d194`

## Commit của tính năng

1. `docs: audit existing OCR architecture and record OCR engine manager decisions`
2. `feat: configure native Docling OCR engines with on-demand model management`
3. `feat: implement OCR engine manager UI in settings`
4. `feat: support persistent and offline OCR installation`
5. `test: add OCR integration and regression coverage`
6. `docs: finalize OCR security, testing, benchmark and rollback guide`
7. (các commit sửa sau review — xem `git log`)

## File chỉnh sửa (đã có từ trước)

`open_notebook/domain/content_settings.py`, `open_notebook/graphs/source.py`, `api/models.py`,
`api/main.py`, `api/routers/settings.py`, `commands/__init__.py`, `pyproject.toml`, `Dockerfile`,
`scripts/docker-entrypoint.sh`, `docker-compose.yml`, `deploy/docker-compose.prod.yml`,
`.env.example`, `README.md`, `docs/7-DEVELOPMENT/decisions/README.md`, `tests/test_graphs.py`,
`frontend/src/app/(dashboard)/settings/page.tsx` (+test), `frontend/src/lib/types/api.ts`,
`frontend/src/lib/api/query-client.ts`, `frontend/src/lib/locales/{en-US,vi-VN}/index.ts`.

## Kết quả test gần nhất

Xem `OCR_TEST_REPORT.md` §1 và §6 (OCR backend 128 test PASS + 4 skip full-pipeline;
`test_graphs.py` 22/22; frontend 401/401; tsc/lint/build PASS; regression không lỗi mới).

## Review độc lập

11 phát hiện; 10 đã sửa kèm test, 1 giữ nguyên có lý do (`OCR_TEST_REPORT.md` §6).

## Vấn đề chưa giải quyết

- Full pipeline Docling + Docker acceptance: NOT VERIFIED trong Cloud (mạng). Chạy trên máy thật:
  `OCR_FULL_PIPELINE=1 pytest tests/test_ocr_integration.py`,
  `scripts/ocr/benchmark.py --mode pipeline`, `scripts/ocr/docker-acceptance.sh`.
- Lỗ hổng phân quyền có sẵn của `POST /api/commands/jobs` (ngoài phạm vi) — đề xuất xử lý riêng.

## Công việc tiếp theo (cho người vận hành)

1. Nghiệm thu Docker + full pipeline trên máy nội bộ.
2. Benchmark với tài liệu thật (không đưa lên GitHub) trước khi đổi engine trong Settings.

## Phase 7

- Phát hiện & sửa: xem `OCR_TEST_REPORT.md` §7.1 (P7-1 … P7-11).
- Hạng mục cần máy thật: full pipeline strict (`OCR_LOCAL_ACCEPTANCE.md` §4.3), Docker E2E/offline/
  rebuild/upgrade (§5), benchmark pipeline (§8).
- Điều kiện trước production: xử lý `OCR_COMMANDS_JOBS_RISK.md` (mục 1 và 3).

## Phase 8A

- Commit (trên `e32eae8`):
  - `2a1dd13` — bảo mật job nền;
  - `52bcba3` — prepare / readiness;
  - `2d3bc9e` — UI readiness;
  - `d87a9b3` — Docker acceptance online / offline;
  - `b27f87b` — test proxy độc lập harness;
  - `cbfb198` — fingerprint gồm cache Docling + trọng số RapidOCR;
  - commit tài liệu Phase 8A;
  - commit sửa theo review độc lập (R8-1 … R8-7, `OCR_TEST_REPORT.md` §8.4).
- File mới:
  - `open_notebook/utils/job_input_guard.py`, `open_notebook/ocr/readiness.py`;
  - `tests/test_background_job_security.py`, `tests/test_ocr_readiness.py`;
  - `docs/security/BACKGROUND_JOB_SECURITY.md`;
  - `docs/ocr/OCR_ONLINE_PREPARATION.md`, `docs/ocr/RELEASE_CANDIDATE.md`.
- `/api/commands/jobs` đã sửa; điều kiện production cũ (#24) đã đóng.
- Còn NOT VERIFIED (cần máy thật, `OCR_LOCAL_ACCEPTANCE.md`):
  - full pipeline 4 engine (§4.3–4.4);
  - Docker online → chuẩn bị → offline → restart offline → cập nhật (§5);
  - API + worker E2E;
  - RapidOCR torch với `OCR_RAPIDOCR_PERSISTENT=true`.
- Trạng thái phát hành: `RELEASE_CANDIDATE.md`.

## Phase 8B

- Nghiệm thu trên máy thật theo `OCR_LOCAL_ACCEPTANCE.md`. Kết quả: `OCR_TEST_REPORT.md` §9; đối chiếu
  điều kiện: `RELEASE_CANDIDATE.md` §6.
- Commit (cục bộ, trên `45e2254`, chưa push):
  - `5e6522e` — sửa script nghiệm thu (P8B-1);
  - `5cbcb37` — readiness local-only (P8B-2);
  - `a8a30c0` — mypy cho test;
  - `4a0b00f` — timeout cho request HF Hub (P8B-3, D-24);
  - `2128587` — xử lý review độc lập;
  - `d9652c0` — RapidOCR persistent với backend torch (P8B-8);
  - commit tài liệu Phase 8B.
- File mới: `open_notebook/ocr/hub_http.py`, `tests/test_ocr_hub_http.py`.
- Vấn đề còn mở: P8B-4 (OSD Tesseract trên crop), P8B-5 (ngưỡng confidence EasyOCR), P8B-6/7 (giới
  hạn đã biết, cần quyết định về ngưỡng test).
- Trạng thái: chưa đủ điều kiện merge `main` hay production.

## Phase 8C

- Branch `local/ocr-phase8c` (từ `local/ocr-phase8b` @ `f172645`); backup `phase8b-backup.bundle` đã verify.
- Commit: `e6f2bbb` (chất lượng OCR), `755b637` (sửa theo review), `6f1c811` (test), + tài liệu.
- File mới: `open_notebook/ocr/pdf_prep.py`, `open_notebook/ocr/tesseract_gate.py`,
  `scripts/ocr/quality_eval.py`, `scripts/ocr/generate_holdout_fixtures.py`, `tests/test_ocr_quality_prep.py`.
- Quyết định: D-25 (Tesseract), D-26 (EasyOCR).
- Kết quả: full pipeline 38/48 (8B: 33/48); Docker 4 engine 72 PASS / 1 FAIL; holdout Tesseract Best
  CER 0,394 → 0,023; regression không lỗi mới.
- Còn mở (cần chủ dự án): tiêu chí §3.1 với 3 FAIL do giới hạn model; ranh giới `tesseract_gate.py`;
  tự xoay trang cho RapidOCR/EasyOCR; vị trí của EasyOCR. Xem `OCR_PHASE8C_REPORT.md` §9.
- Bằng chứng: `/home/admin/cb5400-ocr-accept/evidence/phase8c/`.
- Trạng thái: chưa merge, chưa push, chưa triển khai.

## Phase 8D

- Branch `local/ocr-phase8c` (không tạo branch mới; kế thừa đủ 8B + 8C).
- Commit: `09231ee` (phân loại chất lượng, trạng thái hướng trang, tiêu chí phát hành), `c5162df` (sửa race
  của script Docker), + tài liệu.
- File mới: `scripts/ocr/release_criteria.py`, `tests/test_ocr_release_criteria.py`.
- Quyết định: D-27 (phân loại + tiêu chí có điều kiện + chấp nhận gate / pdf_prep), D-28 (SSRF còn lại).
- Kết quả: bộ gốc 38/48 (không đổi); có điều kiện — Tesseract Best 7/7; Docker full 74 PASS / 1 FAIL;
  RapidOCR persistent 42/0; regression không lỗi mới.
- Trạng thái: READY FOR MERGE (có điều kiện, chờ xác nhận) · READY FOR CONDITIONAL RELEASE (Tesseract Best,
  RapidOCR) · NOT READY FOR PRODUCTION (SSRF qua redirect, benchmark tài liệu thật).
- Còn mở: `OCR_PHASE8D_REPORT.md` §11 F và §15.
- Bằng chứng: `/home/admin/cb5400-ocr-accept/evidence/phase8d/`. Chưa push, chưa merge, chưa triển khai.

## Phase 9A

- Branch làm việc `local/ocr-phase8c`; branch phát hành `release/ocr-engine-manager-rc1` (cùng commit).
- Commit: `3288a73` (công tắc URL ingestion), `d671218` (sửa theo review cuối, benchmark cục bộ, tài liệu
  triển khai), + commit tài liệu cuối của phase.
- File mới: `open_notebook/utils/url_ingestion.py`, `scripts/ocr/local_document_benchmark.py`,
  `tests/test_url_ingestion_switch.py`, `tests/test_ocr_local_benchmark.py`, `OCR_PHASE9A_REPORT.md`,
  `OCR_PRODUCTION_DEPLOYMENT_PLAN.md`, `OCR_PRODUCTION_CHECKLIST.md`, `OCR_REAL_DOCUMENT_BENCHMARK.md`.
- Quyết định: D-29 (`OPEN_NOTEBOOK_ENABLE_URL_INGESTION`, mặc định tắt).
- Kết quả: backend 1288 / 10 (cùng 10 lỗi của `main`); frontend 411/411; review cuối 0 High / 0 Medium;
  bộ OCR gốc không đổi (38/48).
- Trạng thái: READY FOR MERGE · READY FOR CONDITIONAL RELEASE (URL ingestion tắt) · NOT READY FOR PRODUCTION.
- Còn thiếu trước production: benchmark tài liệu thật, backup + restore, kiểm tra môi trường đích, phê duyệt.
- Push: xem `OCR_PHASE9A_REPORT.md` §K.
- Bằng chứng: `/home/admin/cb5400-ocr-accept/evidence/phase9a/`. Chưa merge, chưa triển khai.

## Phase 9B (cập nhật 2026-11-14)

- Branch làm việc và phát hành: `release/ocr-engine-manager-rc1` (kế thừa đủ Phase 0 → 9A, `76b63b5`).
- Phase 9A đã xác minh: RC trên GitHub `76b63b5`, nhánh chính thức `claude/practical-wozniak-9s1t6z` @ `5e04227`,
  37 trước / 0 sau; `phase9a-backup.bundle` hợp lệ.
- Review độc lập (3 agent + 1 agent rà lại phần sửa): 2 Cao + 6 Trung bình, phần lớn có sẵn từ trước tính năng
  OCR. Đã sửa: `d4b5f81` (phân quyền quản trị viên — D-31), `d28300e` (ngân sách thời gian dò hướng — D-30; D-32),
  `6f6b424` (các điểm Thấp từ review lại, script kiểm tra sức khỏe, CHANGELOG).
- Mã được nghiệm thu: `6f6b424`. Chuỗi nghiệm thu: `evidence/phase9b/runs/run-chain-9b.sh` (tiến trình tách rời;
  tiến độ ở `chain.progress`, kết thúc khi có `docker-chain.done`).
- Kết quả nghiệm thu cuối: backend 1435 / 10 (cùng 10 lỗi có sẵn); frontend 411/411; bộ gốc 38/48; Tesseract Best
  có điều kiện 7/7; Docker quick 42/0, full 74/1, persistent 42/0, không Tesseract 50/1 (FAIL: nội dung EasyOCR).
- Pull Request #42 (`release/ocr-engine-manager-rc1` → `claude/practical-wozniak-9s1t6z`): **MERGED** bằng merge
  commit `3819c2a7068916bf7cd2d5bc9c71cfe73b76dfbc` (2026-11-13 18:57 UTC). Bundle: `phase9b-backup.bundle`. **PHASE 9B: COMPLETED.**
- Phase 9C: kiểm tra chỉ đọc production đã xong — xem `OCR_PRODUCTION_DEPLOYMENT_PLAN.md` §1.1, §13 và
  `evidence/phase9c/preflight/`. Phát hiện chính: container production **không có Docling** từ 2026-11-12
  (`UV_OFFLINE=1` trong override). Công cụ đã sẵn: `evidence/phase9c/tools/db_counts.py` (số đếm),
  `make_restore_compose.py` (stack restore cô lập). Số đếm gốc: `preflight/production-counts-preflight.json`.
- Image triển khai đã dựng ở `/home/admin/cb5400-rc1-build` từ commit merge: `chatbot5400:rc1-20261114` =
  `sha256:240bb692922101385c8a4fcb0aaf15451f4ba345ae027e232265e37005d58f56`; đã xác minh trên stack cô lập 42/0 (online → chuẩn bị → offline → restart offline).
- Script triển khai từng bước (chưa chạy): `evidence/phase9c/exec/deploy-9c.sh` — thứ tự `pre stop backup
  restore-old restore-rc restore-down update start verify`.
- **Chưa** dừng, sao lưu hay thay đổi production. Trạng thái: **READY FOR DEPLOYMENT APPROVAL** — chờ chủ dự án
  phê duyệt kế hoạch (cổng phê duyệt 17 mục) và benchmark tài liệu thật hoặc phạm vi thí điểm phi nghiệp vụ.

## Phase 9C (cập nhật 2026-11-14)

- Chủ dự án phê duyệt triển khai **thí điểm phi nghiệp vụ** kèm điều kiện: RapidOCR giữ làm engine được chọn; hệ
  thống chỉ mở lại sau khi kiểm tra bảo mật bắt buộc đạt; rollback chỉ ở chế độ cô lập; giữ nguyên route podcast.
- Đã làm trên production: sao lưu lạnh (dữ liệu, image, cấu hình; checksum + manifest) → restore trên stack cô lập
  với image cũ và image triển khai (đạt) → fast-forward mã tới `3ca6428` (5 file cục bộ giữ nguyên) → sửa override
  (bỏ 3 biến offline; URL ingestion tắt; runtime Tesseract) → khởi động **chế độ bảo trì** (cổng chỉ nghe loopback).
  DB: cùng container, cùng image. Ứng dụng ngừng hoàn toàn 4 phút 02 giây.
- Kết quả: Docling 2.129.0 cài được; Tesseract Vietnamese Best cài + `offline_ready` + test đạt; RapidOCR
  `offline_ready`; smoke test A 23/23 · B 29/29 · C 68/68 · D 15/15; dữ liệu trước / sau bằng nhau; hai tài khoản tạm
  và mọi dữ liệu thử đã xóa; RapidOCR là engine được chọn.
- Offline: stack cô lập bằng image triển khai — Tesseract Best 42/0, RapidOCR 42/0. Production: `offline_ready`;
  `offline_verified` chưa (không ngắt Internet máy chủ).
- **Còn lại:** (1) trạng thái truy cập và điều kiện mở cho người dùng: xem báo cáo vận hành riêng trên máy chủ (không
  ghi trong repository); (2) benchmark tài liệu thật do chủ dự án thực hiện —
  **OCR REAL-DOCUMENT QUALIFICATION: PENDING**; (3) theo dõi 24 giờ; (4) phê duyệt danh sách dọn tài nguyên nghiệm thu.
- Báo cáo: `OCR_PHASE9C_REPORT.md` (công khai), báo cáo vận hành riêng và bằng chứng ở `evidence/phase9c/` (ngoài
  repository).
