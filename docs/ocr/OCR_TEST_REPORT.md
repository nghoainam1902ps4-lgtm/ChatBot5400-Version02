# OCR Engine Manager — Test Report

Môi trường: Claude Code Cloud, 4 vCPU / 15 GiB, Python 3.12 (uv venv `uv sync --extra docling`),
Docling 2.129.0, content-core 2.0.7, Tesseract 5.3.4 (apt), easyocr 1.7.2. Ngày 2026-11-12.

## 1. Tổng hợp

| Nhóm | Lệnh | Kết quả |
|---|---|---|
| Unit OCR (catalog, paths, settings, routing, store, installer, delete, lifecycle, probes, nonce, API, quyền admin) | `uv run pytest tests/test_ocr_engine_manager.py` | **PASS** 93/93 |
| Bundle + CLI | `uv run pytest tests/test_ocr_bundle_cli.py` | **PASS** 11/11 |
| Parity với Content Core (`extract_docling`) | `uv run pytest tests/test_ocr_docling_parity.py` | **PASS** 11/11 |
| Routing source graph | `uv run pytest tests/test_ocr_source_graph.py` | **PASS** 5/5 |
| Tích hợp engine thật (OCR stage, Docling OCR class thật) | `OCR_TEST_DATA_DIR=<data> uv run pytest tests/test_ocr_integration.py` | **PASS** 8/8; **SKIP** 4 (full pipeline cần model HF) |
| Regression backend (toàn bộ `tests/`, trừ 4 file cần tải tiktoken) | xem §3 | **Không lỗi mới**: 897 passed / 12 failed trên branch; commit gốc 793 passed / 10 failed; 10 lỗi chung có sẵn ở commit gốc; 2 lỗi mới đã sửa (§3) |
| Frontend lint | `npm run lint` | **PASS** 0 error (7 warning có sẵn, không ở file mới) |
| Frontend typecheck | `npx tsc --noEmit` | **PASS** |
| Frontend test | `npx vitest run` | **PASS** 62 files / 401 tests (gồm 11 test `OcrEngineManager`, test parity/unused-key locale) |
| Frontend build | `npm run build` | **PASS** |
| Ruff / mypy (mã mới) | `ruff check`, `mypy open_notebook/ocr api/ocr_service.py …` | **PASS** |
| Cài model thật từ nguồn chính thức | `installer.install_models` ×3 | **PASS** (§2.1) |
| Offline bundle thật, mạng bị chặn | CLI `bundle create/verify/install`, `runtime ensure --offline` | **PASS** (§2.2) |
| Benchmark | `scripts/ocr/benchmark.py --mode ocr-stage` | Hoàn thành — `OCR_BENCHMARK.md` |
| Full pipeline Docling (Layout+Table+OCR) | `OCR_FULL_PIPELINE=1 pytest …`, `benchmark --mode pipeline` | **NOT VERIFIED** — huggingface.co bị chặn |
| Docker build/run | `scripts/ocr/docker-acceptance.sh` | **NOT VERIFIED** — §4 |

## 2. Bằng chứng chính

### 2.1 Cài model thật (GitHub chính thức)

- tesseract_fast: 3 tệp `download`, smoke check "recognised 195 characters" — 7.2 s.
- tesseract_best: vie/eng `download`, **osd `existing`** (dùng chung) — 2.8 s.
- easyocr: 2 zip tải + giải nén + kiểm tra sha256, smoke check EasyOCR Reader OK — 10.5 s.
- Cài lại tesseract_best: mọi tệp `existing`, 0.4 s ⇒ **không tải lại model hợp lệ**.
- Status sau cài: 4/4 `ready`.

### 2.2 Offline

1. Gỡ `easyocr` + 6 phụ thuộc khỏi venv, `apt-get remove tesseract-ocr`.
2. `bundle create --engines tesseract_fast tesseract_best easyocr` (online): 15 tệp, 211 MB,
   7 wheel (đúng tập uv báo thiếu), 1 `.deb`.
3. Bundle sửa 1 byte ⇒ `bundle verify` exit 1, `bundle install` exit 1, không tạo `models/`.
4. Với `HTTPS_PROXY/HTTP_PROXY=http://127.0.0.1:9`, `UV_OFFLINE=1`, `OCR_OFFLINE=true`, data dir
   mới: `bundle install` ⇒ model nguồn `bundle`; `runtime ensure --offline` ⇒ `dpkg -i` tesseract,
   `uv pip install --offline --no-index --find-links` 7 wheel ⇒ 4/4 `ready`.

### 2.3 Engine thực tế do Docling dùng

`tests/test_ocr_integration.py` khẳng định class do factory chính thức của Docling tạo:
`TesseractOcrCliModel` (lang `fast/vie,fast/eng` hoặc `best/vie,best/eng`), `EasyOcrModel`
(`use_gpu=False`, `download_enabled=False`), và CER < 5% (Tesseract) / < 15% (EasyOCR) trên
mẫu tiếng Việt, số hiệu `1234/2024` đọc đúng. Chạy song song Fast+Best trong 2 thread: mỗi
engine dùng đúng trọng số của mình (không xung đột biến môi trường). Trang xoay: word recall
≥ 0.9 với Tesseract Best.

Lỗi thật phát hiện nhờ chạy class Docling thật (đã sửa): Docling gọi `tesseract … stdout tsv`
và Tesseract tìm `configs/tsv` trong `TESSDATA_PREFIX` ⇒ mã tự tạo tệp cấu hình chuẩn này.

### 2.4 Layout/Table không đổi

`test_ocr_docling_parity.py`: với 4 engine × 2 bộ cờ, `model_dump()` của options ChatBot5400
chỉ khác Content Core ở `ocr_options` (và `accelerator_options` khi đặt luồng); `layout_options`
(Heron) và `table_structure_options` (TableFormer accurate) **bằng nhau**. Probe Docling báo
`layout_heron` / `docling_tableformer (accurate)`.

## 3. Regression — so sánh với commit gốc

Chạy cùng điều kiện (mạng bị chặn để test cần mạng thất bại nhanh) trên branch và trên
worktree của `5e04227`. Bỏ qua cả hai bên: `test_chunking.py`, `test_context_endpoint_characterization.py`,
`test_embedding.py`, `test_utils.py` — treo khi tải encoding tiktoken (`openaipublic.blob.core.windows.net`
không truy cập được; image Docker nướng sẵn encoding này) ⇒ **NOT VERIFIED trong Cloud**.

- Lỗi chung cả hai bên (có sẵn, không liên quan): `test_domain.py::TestContentSettings::test_content_settings_defaults`
  (mong đợi `auto`, mặc định là `docling` từ migration 28) và 9 test
  `test_models_api.py::TestModelsProviderAvailability::*`.
- Lỗi chỉ trên branch (đã xử lý): `test_graphs.py::TestContentProcessDeleteSource::*` (2) —
  venv dev có cài EasyOCR nên theo D-03 cấu hình mặc định đi lớp Docling ghim RapidOCR thay vì
  Auto của Content Core; test (mock `extract_content`, PDF giả) phụ thuộc môi trường. Thêm
  fixture cố định giả định "cài đặt chuẩn" — không đổi điều test khẳng định. Sau sửa:
  `test_graphs.py` 22/22 PASS.

## 4. Docker — NOT VERIFIED (giới hạn mạng của Cloud)

Docker daemon khởi động được, nhưng build image sản phẩm bị chặn bởi chính sách mạng: blob
`ghcr.io` (`pkg-containers.githubusercontent.com` 403), Docker Hub 429 (rate limit), proxy không
cho HTTP thường (405) và chặn `deb.debian.org` qua HTTPS (403). Đã thử Dockerfile bản sao chỉ để
test (thêm CA của proxy) — vẫn bị chặn ở apt Debian. Không sửa Dockerfile sản phẩm để né.
`scripts/ocr/docker-acceptance.sh` (8 kịch bản, project/volume tạm riêng, không `down -v`) cần
chạy trên máy triển khai. Cú pháp entrypoint đã kiểm tra (`sh -n`).

## 5. Screenshot

`docs/ocr/images/ocr-manager-vi-VN.png`, `ocr-manager-en-US.png`: bản build production của
frontend, dữ liệu `/api/ocr/engines` là JSON **thật** do mã backend tính từ data dir Cloud (4
engine `ready`, Docling 2.129.0, `layout_heron`, `docling_tableformer (accurate)`); các API khác
(đăng nhập, settings) được Playwright trả lời giả lập vì Cloud không có SurrealDB.

## 6. Review độc lập (Phase 8) và sửa lỗi

Một agent review độc lập toàn bộ diff (không sửa file) báo 11 phát hiện; đã xử lý:

| # | Phát hiện | Xử lý | Test |
|---|---|---|---|
| 1 | Smoke check thất bại nhưng tệp hợp lệ vẫn hiện `ready` và kích hoạt được | Manifest `failed`/job chết ⇒ luôn `failed`; UI cho Thử lại | `test_failed_smoke_with_verified_files_is_not_ready`, UI test |
| 2 | Cài Fast+Best đồng thời: lock osd không chờ ⇒ kẹt "downloading" | Lock dùng chung có chờ (timeout); `LockBusy` ghi `failed` | `test_shared_lock_waits_instead_of_failing`, `test_lock_busy_job_records_retryable_failure` |
| 3 | PDF/ảnh lấy từ URL đi Auto của Content Core (có thể đổi sang EasyOCR và tải model) | D-11 | `test_url_scans_follow_selected_engine`, `test_url_scan_uses_selected_engine` |
| 4 | Ảnh nhận cờ formulas/vision (Content Core không áp dụng cho ảnh) | D-12 | `test_images_keep_docling_defaults_except_ocr` |
| 5 | Hai nơi sửa `docling_ocr`, form Settings có thể ghi đè | SettingsForm đồng bộ lại khi không có thay đổi chưa lưu | frontend suite |
| 6 | Polling 2 s ghi đè ô cấu hình đang nhập | Chỉ đồng bộ khi cấu hình server đổi | frontend suite |
| 7 | Nút Cài đặt hiện khi runtime không tương thích | Ẩn | `no install button when the runtime is incompatible` |
| 8 | Job bị mất ⇒ "pending" 6 giờ | API đối chiếu trạng thái job surreal-commands, job đã kết thúc ⇒ `failed` | `test_lost_job_is_reconciled_to_failed`, `test_running_job_not_reconciled` |
| 9 | osd có thể bị xoá khi engine kia `corrupted`/đang cài | Giữ osd khi engine kia có bất kỳ tệp nào hoặc đang cài; xoá dưới lock dùng chung | `test_osd_kept_while_other_variant_*` |
| 10 | Gói staged tin theo checksum nằm trên volume ⇒ ghi volume = cài gói root | D-13 (digest ghim ngoài volume); kiểm chứng thật offline | `test_staged_package_verification` |
| 11 | `TESSDATA_PREFIX` khác bị coi là không tương thích | **Giữ nguyên có chủ đích**: Docling chạy `--list-langs`/OSD không kèm `--tessdata-dir`, nên prefix khác thật sự làm hỏng; trạng thái báo rõ cách sửa | – |

Sau sửa: OCR backend 93+11+11+5+8 PASS (4 skip full pipeline), `test_graphs.py` 22/22, frontend
401/401, tsc/lint/build PASS; integration engine thật PASS; khôi phục runtime offline có/không
digest ghim đã kiểm chứng thật.
