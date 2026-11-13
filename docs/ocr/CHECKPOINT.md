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

