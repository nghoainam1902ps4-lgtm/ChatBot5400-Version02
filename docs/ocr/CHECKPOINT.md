# Checkpoint

- **Phase hiện tại:** 6 hoàn tất (review độc lập đã xử lý — xem dưới).
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

Xem `OCR_TEST_REPORT.md` §1 (OCR 114 test PASS + 4 skip full-pipeline; frontend 399 PASS; build
PASS; regression không lỗi mới).

## Vấn đề chưa giải quyết

- Full pipeline Docling + Docker acceptance: NOT VERIFIED trong Cloud (mạng). Chạy trên máy thật:
  `OCR_FULL_PIPELINE=1 pytest tests/test_ocr_integration.py`,
  `scripts/ocr/benchmark.py --mode pipeline`, `scripts/ocr/docker-acceptance.sh`.
- Lỗ hổng phân quyền có sẵn của `POST /api/commands/jobs` (ngoài phạm vi) — đề xuất xử lý riêng.

## Công việc tiếp theo (cho người vận hành)

1. Nghiệm thu Docker + full pipeline trên máy nội bộ.
2. Benchmark với tài liệu thật (không đưa lên GitHub) trước khi đổi engine trong Settings.
