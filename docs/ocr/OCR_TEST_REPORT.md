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

## 7. Phase 7 — Hardening & acceptance readiness

### 7.1 Phát hiện và xử lý

| # | Phát hiện | Mức | Xử lý | Bằng chứng |
|---|---|---|---|---|
| P7-1 | Container mới cài Docling **không theo lock**: hôm nay sẽ là Docling 2.150.0 / RapidOCR 3.10.0 / torch 2.15.0 thay vì 2.129.0 / 3.9.2 / 2.14.0 đã kiểm thử | Cao | Constraints xuất từ `uv.lock` (Dockerfile → entrypoint/CLI); extra `ocr-easyocr` khoá EasyOCR (D-14) | `uv pip compile` không/có `-c` (2.150.0 → 2.129.0); `test_entrypoint_installs_docling_with_constraints_and_keeps_cmd` chạy entrypoint thật với stub |
| P7-2 | Lớp OCR phụ thuộc API nội bộ Content Core/Docling, không có cảnh báo khi thay đổi | Cao | Guard phiên bản + dấu vân tay mã nguồn; lệch ⇒ `incompatible`, không âm thầm (D-14) | `tests/test_ocr_dependency_compat.py` (12) |
| P7-3 | Ảnh khi tắt OCR vẫn bị Docling OCR qua Auto ⇒ có thể chọn EasyOCR và tải trọng số | Trung bình | Ảnh luôn theo engine đã chọn (D-15) | `test_ocr_disabled_semantics` |
| P7-4 | Log metadata truy cập khoá trực tiếp (KeyError tiềm ẩn) | Thấp | `.get` | parity tests |
| P7-5 | Gỡ model khi job đang chạy với engine cũ | Trung bình | Chặn khi có job `running`/test chờ; fail-closed (D-17) | 3 test API |
| P7-6 | Khôi phục offline sau recreate cần mạng | Trung bình | `--offline` từ cache uv cho Docling/EasyOCR (D-18) | Kiểm chứng thật: mạng chặn, xoá easyocr ⇒ cài lại từ cache |
| P7-7 | RapidOCR trên máy GPU dùng CUDA (hành vi gốc) | Thông tin | Giữ mặc định; opt-in `OCR_RAPIDOCR_FORCE_CPU` (D-16) | `TestCpuMode` (3); EasyOCR `reader.device == "cpu"` thật |
| P7-8 | Docker acceptance cũ: ngắt mạng làm mất DB; "update" chỉ là đổi tag; chỉ dùng CLI | Cao (giá trị nghiệm thu) | Viết lại: mạng `internal`, build lại thật + kiểm tra image ID, nâng cấp từ `OLD_REF`, E2E qua API + worker | `bash -n` + ShellCheck sạch; driver kiểm thử với stub (5) |
| P7-9 | Test full pipeline cũ chỉ kiểm tên model + Markdown không rỗng | Cao (giá trị nghiệm thu) | 7 fixture có ground truth; kiểm nội dung, thứ tự, số liệu, bảng/hàng/cột/ô gộp, phân biệt OCR vs text layer; strict mode | `tests/test_ocr_integration.py` |
| P7-10 | `POST /api/commands/jobs` (có sẵn): đọc/xoá file tuỳ ý, SSRF qua `process_source` | **Cao** | Không sửa (ngoài phạm vi) — tài liệu + phương án | `OCR_COMMANDS_JOBS_RISK.md` |
| P7-11 | RapidOCR torch lưu trọng số trong venv ⇒ mất khi recreate (có sẵn) | Thông tin | Ghi nhận giới hạn, không đổi mặc định | `OCR_DOCKER_STORAGE.md` §5 |

### 7.2 Kết quả chạy trong Cloud

| Bộ test | Kết quả |
|---|---|
| `test_ocr_engine_manager.py` | 99 passed |
| `test_ocr_bundle_cli.py` | 11 passed |
| `test_ocr_docling_parity.py` (gồm parity hành vi với `_extract_file`/`_extract_url`) | 24 passed |
| `test_ocr_source_graph.py` | 5 passed |
| `test_ocr_dependency_compat.py` | 12 passed |
| `test_ocr_acceptance_driver.py` (driver Docker E2E với stub HTTP — **không phải** nghiệm thu sản phẩm) | 5 passed |
| `test_ocr_doc_commands.py` (24 khối bash trong docs/ocr: `bash -n`) | 2 passed |
| `test_ocr_integration.py` — OCR stage engine thật | 9 passed |
| `test_ocr_integration.py` — full pipeline (4 engine × 7 fixture + nhận diện pipeline + attribution) | **39 NOT VERIFIED** (Hugging Face / modelscope bị chặn). Strict mode: 39 FAIL gắn nhãn "NOT VERIFIED", 0 PASS giả |
| `test_graphs.py` | 22 passed |
| Regression backend toàn bộ (offline harness như Phase 6) | 951 passed, 10 failed — **đúng 10 lỗi có sẵn ở commit gốc**, 0 lỗi mới |
| Frontend: tsc / lint / vitest / build | 0 lỗi / 0 error / 401 passed / PASS |
| mypy + ruff (mã thay đổi) | sạch |
| ShellCheck 0.11 (`docker-acceptance.sh`, entrypoint; khối lệnh trong tài liệu nghiệm thu, trừ SC2164 có chủ đích) | sạch |
| Docker build / E2E / offline / rebuild / upgrade | **NOT VERIFIED** — Docker Hub 429, ghcr blob 403, Debian apt 403; tải SurrealDB binary bị chặn bởi chính sách quyền của phiên |

## 8. Phase 8A — Bảo mật cuối, chuẩn bị online / vận hành offline

Môi trường như trên; ngày 2026-11-13; so sánh với `e32eae8` (Phase 7).

### 8.1 Kết quả chạy trong Cloud

| Bộ test / kiểm tra | Kết quả |
|---|---|
| `test_background_job_security.py` (mới: quyền router commands, tắt submit tổng quát, upload path / delete / URL redirect / record id, `process_source` binding, nonce OCR) | 57 passed |
| `test_ocr_readiness.py` (mới: trạng thái, lỗi thời theo fingerprint gồm cache Docling + trọng số RapidOCR, tiến trình con chặn mạng, prepare, lỗi offline, RapidOCR bền vững, API) | 39 passed |
| `test_ocr_acceptance_driver.py` (driver Docker với stub HTTP — **không phải** nghiệm thu runtime) | 9 passed |
| `test_ocr_engine_manager.py` / `test_ocr_docling_parity.py` / `test_ocr_dependency_compat.py` / `test_ocr_bundle_cli.py` / `test_ocr_source_graph.py` | 99 / 24 / 12 / 11 / 5 passed |
| `test_graphs.py` (uploads chuyển vào tmp vì guard mới) | 22 passed |
| `test_ocr_doc_commands.py` (khối bash trong docs/ocr, `bash -n`) | 2 passed |
| Regression backend toàn bộ (offline harness) | **1053 passed, 10 failed**; `e32eae8`: 951 passed, 10 failed — **cùng 10 lỗi có sẵn**, 0 lỗi mới |
| Frontend: tsc / lint / vitest / build | 0 lỗi / 0 error (7 warning có sẵn) / 404 passed / PASS |
| ruff + mypy (file thay đổi) | sạch |
| ShellCheck + `bash -n` (`docker-acceptance.sh`) | sạch |
| Hadolint (Dockerfile) | 0 error; DL3008 (tesseract không ghim phiên bản apt — theo quy ước có sẵn), DL3059 (info) |

### 8.2 Chạy thật (không mock)

| Kiểm tra | Kết quả |
|---|---|
| `cli prepare --engines tesseract_best` khi huggingface.co bị chặn | Đúng hành vi: model Tesseract đã có (checksum hợp lệ, không tải lại); chạy kiểm tra `online` rồi `local_only`, đều thất bại với `huggingface.co', port=443): Max retries exceeded with url: /api/models/docling-project/...`; trạng thái `not_offline_ready`, exit ≠ 0. **Không báo sẵn sàng sai** |
| Tiến trình con `local_only` thật | Proxy `127.0.0.1:9` ⇒ mọi lần tải lỗi ngay (`test_real_local_only_child_process`) |
| RapidOCR `Global.model_root_dir` (backend onnxruntime, overlay chỉ để test) khi mạng bị chặn | RapidOCR log `File exists and is valid: <OCR_DATA_DIR>/models/rapidocr/PP-OCRv6_det_small.onnx` (+ rec, cls) và OCR chạy; không tải |
| RapidOCR backend torch (production) với thư mục bền vững | **NOT VERIFIED** — modelscope.cn bị chặn |
| Full pipeline 4 engine | **NOT VERIFIED** — huggingface.co 403 |
| Docker: cập nhật online / chuẩn bị / offline / restart offline / cập nhật online | **NOT VERIFIED** — Docker Hub 429, ghcr 403, Debian apt 403 |
| API + worker E2E thật | **NOT VERIFIED** — tải SurrealDB binary bị chính sách quyền của phiên từ chối; không tìm cách vượt qua |

### 8.3 Phát hiện và xử lý trong Phase 8A

| # | Phát hiện | Xử lý |
|---|---|---|
| P8-1 | `/api/commands/jobs` cho user thường chạy command tuỳ ý (đọc / xoá file, SSRF) | Chỉ admin + tắt submit tổng quát + guard trong worker (D-19) |
| P8-2 | Không có cách chứng minh "chạy được offline" | Readiness bằng pipeline thật, có ba mức (D-20) |
| P8-3 | Kết quả sẵn sàng có thể bị dùng lại sau khi recreate làm mất trọng số RapidOCR / cache HF | Fingerprint gồm snapshot Docling + trọng số RapidOCR ⇒ kết quả lỗi thời |
| P8-4 | Thiếu model khi offline ⇒ job retry nhiều lần với lỗi khó hiểu | `ValueError` + hướng dẫn (D-22) |
| P8-5 | Test proxy phụ thuộc biến môi trường của harness | Test tự đặt proxy, độc lập môi trường |

### 8.4 Review độc lập diff Phase 8A (agent riêng, chỉ đọc mã) và xử lý

| # | Mức | Phát hiện | Xử lý | Test |
|---|---|---|---|---|
| R8-1 | **Cao** | Đường tạo nguồn **sync** (`async_processing=false`, mặc định của API/JSON) không lưu `asset`. Do đó guard `_bind_content_to_source` từ chối mọi nguồn upload / link: job lỗi, API trả 500. UI luôn dùng async nên không thấy | Helper `_source_asset` dùng chung cho hai đường | `TestSyncSourceAssetPersistence` (2; fail trước khi sửa, pass sau) |
| R8-2 | Trung bình–Cao | Kiểm tra `offline` chạy với mạng thật. Nếu probe Internet báo sai (DNS chậm, chỉ bị chặn 4 host, mirror HF), model có thể được tải mà vẫn ghi `offline_verified` | Chặn mạng tiến trình con cho mọi mode trừ `online` | `test_network_blocked_for_every_no_download_check` (3) |
| R8-3 | Trung bình | Worker bị kill giữa chừng ⇒ marker prepare / check không bao giờ được xoá: nút bị khoá, frontend poll mãi | `*_queued_at` + timeout `READINESS_MARKER_STALE_SECONDS` | `test_dead_marker_is_cleared_after_timeout` |
| R8-4 | Trung bình | Prepare tải model trong khi `job_id` còn là của lần install cũ ⇒ `_reconcile_job` đánh dấu FAILED giữa chừng | Bỏ qua reconcile install khi đang prepare; prepare chết thì timeout của store vẫn áp dụng | `test_prepare_download_not_failed_by_install_reconcile` |
| R8-5 | Trung bình | Kiểm tra offline pass cũ che lần kiểm tra mới hơn bị thất bại | Lấy lần kiểm tra no-network còn hiệu lực **mới nhất** | `test_newer_failed_check_wins_over_older_offline_pass` |
| R8-6 | Thấp–Trung bình | Kiểm tra redirect chỉ là pre-check; lần tải thật của content-core tự theo redirect | Sửa docstring và tài liệu cho đúng (rủi ro còn lại, `BACKGROUND_JOB_SECURITY.md` §5); không đổi hành vi content-core | – |
| R8-7 | Thấp | Fingerprint không thấy blob HF bị dọn (symlink snapshot bị treo) | Signature gồm từng file + kích thước (`-1` khi treo) | `test_pruned_docling_blobs_make_verdict_stale` |
| R8-8 | Thấp (không chắc) | Kiểm tra readiness không đọc `ContentSettings` | **Giữ nguyên:** `num_threads` / `force_full_page` không đổi model nào được nạp, mà readiness chỉ chứng minh model có sẵn; tiến trình con không phụ thuộc DB | – |

Agent review cũng xác nhận các phần sau là sạch:

- router commands, path guard (kể cả trường hợp `/uploads-evil`);
- mọi chỗ gọi `submit_command` với `require_record_id`;
- luồng async upload / link / text và retry;
- nonce OCR (trong một tiến trình API);
- polling frontend;
- mặc định RapidOCR;
- không có `pip` / `apt` từ HTTP.

Giới hạn ghi nhận: lock nonce là theo tiến trình (chạy nhiều uvicorn worker không được bảo đảm, như các
job OCR trước đây).

## 9. Phase 8B — Nghiệm thu trên máy thật

Ngày 2026-11-13. Chạy theo `OCR_LOCAL_ACCEPTANCE.md`, lộ trình nhanh trước, sau đó lộ trình đầy đủ.

**Môi trường:**

- Máy: Ubuntu 26.04, x86_64, 8 CPU, 30 GB RAM, CPU-only.
- Docker 29.8.2, Compose v5.6.0; Python 3.12.16, uv 0.13.8.
- Tesseract 5.5.0, cùng bản với image Docker. Không có sudo nên cài ở user-space:
  `apt-get download` + `dpkg -x` + wrapper; không đổi hệ thống.
- Mã: branch `local/ocr-phase8b` = `45e2254` + các commit sửa ở §9.3.

**An toàn:**

- Deployment đang chạy (`chatbot5400-version02`, commit `5e04227`) **không bị dừng, sửa hay xoá**.
  Volume và DB của nó không bị đụng tới.
- Mọi lần chạy Docker dùng compose project, mạng và thư mục riêng, không publish cổng.

### 9.1 Kết quả

| Hạng mục (mục trong `OCR_LOCAL_ACCEPTANCE.md`) | Kết quả |
|---|---|
| §3 Khoá dependency | **PASS** — content-core 2.0.7, docling 2.129.0, rapidocr 3.9.2, easyocr 1.7.2, torch 2.14.0, khớp `compat.py` |
| §4.1 Runtime + model | **PASS** — cả 4 engine `state=ready`; smoke test của từng model đọc 187–195 ký tự |
| §4.2 Model Docling | **PASS** — `layout_heron`, `docling_tableformer`, `accurate`; RapidOCR torch tải trọng số từ modelscope.cn |
| §4.3 Lộ trình nhanh (`-k tesseract_best`, strict) | **FAIL** — 5 PASS / 4 FAIL / 0 NOT VERIFIED |
| §4.3 Đầy đủ (4 engine × 7 fixture, strict) | **FAIL** — 33 PASS / 15 FAIL / 0 NOT VERIFIED. RapidOCR 1, Tesseract Fast 5, Tesseract Best 4, EasyOCR 5 (§9.3: P8B-4 … P8B-7) |
| §4.4 Prepare + readiness (ngoài Docker) | Lần 1: **FAIL** — cả 4 engine `not_offline_ready` (P8B-2). Sau khi sửa: **PASS** — 4 engine `offline_ready`, `local_only_verified=True` |
| `offline_verified` ngoài Docker | **NOT VERIFIED** — không ngắt mạng máy chủ vì sẽ ảnh hưởng deployment đang chạy; `unshare -rn` bị AppArmor chặn. Đã nghiệm thu bằng container bị ngắt mạng thật (§5) |
| §5 Docker lộ trình nhanh (`tesseract_best`, `OLD_REF=e32eae8`) | Lần 1: script lỗi (P8B-1). Lần 2: `prepare` FAIL (P8B-2). Lần 3: job đầu tiên khi offline treo 16 phút (P8B-3). **Lần 4 (đủ bản sửa): 40/40 PASS, exit 0** |
| §5 Docker đầy đủ (4 engine, `OLD_REF=5e04227` = production thật) | **FAIL — 53 PASS / 2 FAIL / 0 NOT VERIFIED, exit 1.** Mọi bước hạ tầng PASS: nâng cấp từ production (giữ settings + dữ liệu); 4 engine `offline_ready`; offline thật (`offline_verified`); restart offline; rebuild + recreate; offline lại. Hai FAIL là E2E nội dung: Tesseract Fast thiếu `1234/2024/QĐ-MẪU` (P8B-7); EasyOCR thiếu 2/2 câu kỳ vọng (P8B-5). Tài liệu vẫn xử lý xong và đúng engine. Script loại engine FAIL khỏi các bước offline ⇒ **vận hành offline của Tesseract Fast và EasyOCR chưa được nghiệm thu E2E**; RapidOCR (mặc định) và Tesseract Best: offline E2E PASS ở cả 3 vòng |
| §5 RapidOCR `OCR_RAPIDOCR_PERSISTENT=true` (`SCENARIOS=rapidocr`) | Lần 1: **FAIL** — `prepare` lỗi `TypeError` ngay ở kiểm tra online (P8B-8). Sau khi sửa (`d9652c0`): **36/36 PASS, exit 0** — trọng số `.pth` được giữ qua rebuild + recreate (checksum không đổi), offline E2E PASS ở cả 3 vòng |
| Kiểm tra bảo mật trực tiếp trên stack nghiệm thu | **PASS 16/16**. Ẩn danh ⇒ 401. Admin gửi `/api/commands/jobs` (`process_source` với `/etc/passwd`; 3 command OCR với nonce giả) ⇒ 403 "Generic command submission is disabled". User thường ⇒ 403 trên commands, users, install / prepare / activate / config OCR |
| Test bảo mật + readiness + Hub timeout | 102 passed (thêm 1 test RapidOCR ở `d9652c0`) |
| Regression backend (mã cuối, sau `d9652c0`) | **1166 passed, 10 failed, 44 skipped**. `main` (`5e04227`, worktree riêng): 894 passed, 10 failed — **cùng đúng 10 lỗi** (`test_models_api` ×9, `test_domain` ×1); 0 lỗi mới |
| ruff / mypy | ruff: 1 lỗi có sẵn (`tests/test_auth.py`, import order); mypy: 33 lỗi có sẵn, **bằng baseline `45e2254`**; file thay đổi sạch |
| Frontend (node 22 trong container) | lint 0 error (7 warning có sẵn); tsc 0 lỗi; vitest 404/404; build PASS |
| §8 Benchmark | Có số đo `--mode ocr-stage` và `--mode pipeline` cho 4 engine (`OCR_BENCHMARK.md` §6) |
| Review độc lập diff 8B (agent riêng, chỉ đọc) | 0 High, 0 Medium; 2 Low, đã xử lý (§9.4) |

### 9.2 Bằng chứng

Trên máy nghiệm thu (không commit), trong thư mục `$ACCEPT_DIR`:

- `ocr-acceptance-quick.json`, `logs/ocr-acceptance.run1.json`;
- `readiness.json` và `logs/readiness.run1-proxyerror.json`;
- `docker-acceptance-quick.log`, `docker-acceptance.log`, `docker-acceptance-rapidocr-persistent.log`,
  các lần chạy lỗi trong `logs/`, log app của
  lần treo trong `logs/docker-quick-run3-offline-hang.app.log`;
- `bench-ocr-stage.json`, `bench-pipeline.json`;
- `logs/pytest-full-{branch,main}.txt`, `logs/frontend.txt`, `logs/security-live.json`.

### 9.3 Phát hiện và xử lý

| # | Mức | Phát hiện | Nguyên nhân gốc (đã kiểm chứng) | Xử lý |
|---|---|---|---|---|
| P8B-1 | Trung bình (công cụ nghiệm thu) | `docker-acceptance.sh` FAIL ngay bước 0; container nghiệm thu bị bỏ lại | `APP_IMAGE=x dc up` chỉ đặt biến cho một lệnh. Các lệnh `dc ps/restart/down` sau đó không parse được compose file (Compose v5.6: "service app has neither an image…") | `5e6522e`: export `APP_IMAGE`; test hồi quy |
| P8B-2 | **Chặn** | `prepare` / `readiness --check` không bao giờ đạt `offline_ready` / `offline_verified` trên máy thật, cả trong và ngoài Docker, với cả 4 engine | huggingface_hub 0.36 **ném lại `ProxyError`** thay vì dùng cache (`_snapshot_download.py:166`). Proxy chết `127.0.0.1:9` vì vậy không tương đương rút mạng (mất mạng thật cho `ConnectionError` ⇒ dùng cache). Test cũ đều mock nên không thấy | `5cbcb37`: tiến trình con đặt thêm `HF_ENDPOINT` vào cổng chết (nằm trong `NO_PROXY`) ⇒ connection refused ⇒ dùng cache. Thiếu model vẫn FAIL (`LocalEntryNotFoundError`, đã thử với cache rỗng). Có test ghim hành vi của Hub |
| P8B-3 | **Chặn** | Sau khi mất Internet, job OCR đầu tiên của worker treo ~16 phút; xử lý tài liệu tiếp theo treo lần nữa | `snapshot_download` gọi `repo_info()` **không có timeout**, trên kết nối keep-alive tới CDN của HF còn sót từ pha online. Worker giữ socket `ESTABLISHED` tới `3.162.66.59:443` với 322 byte chưa ACK. Request chờ TCP bỏ cuộc (`tcp_retries2=15`) | `4a0b00f`: timeout có giới hạn cho request Hub (D-24). Test dùng socket thật nhận kết nối mà không trả lời; không có bản sửa thì test treo. Docker lộ trình nhanh lần 4: bước 3–5 PASS, không treo |
| P8B-4 | **Cao — CHƯA SỬA** | Tesseract (Fast/Best): bảng scan và trang xoay ra chữ lộn ngược; recall 0.00–0.33 trên `bang_gop_scan`, `nhieu_trang_scan`, `vb_xoay_scan` | Docling chạy OSD (`--psm 0`) trên **từng vùng crop**, rồi xoay theo kết quả **bất kể độ tin cậy**. Trên crop sát mép, OSD trả 180° với độ tin cậy 0.16 cho bảng thẳng đứng, và 90° (0.02) cho trang cần 270°. Tesseract 5.5.0 trong image Docker cho kết quả y hệt | Cần quyết định thiết kế (vá hành vi nội bộ Docling). Thử nghiệm what-if (chỉ trong scratch): thêm lề trắng 60 px trước OSD ⇒ `vb_xoay_scan` recall 0.00 → 1.00, bảng 0.00 → 0.75–0.83. Phần còn lại là lỗi đọc số trong ô bảng |
| P8B-5 | **Cao — CHƯA SỬA** | EasyOCR mất phần lớn nội dung ở fixture 150 DPI (`vb_scan` CER 0.848); E2E Docker thiếu văn bản kỳ vọng | Docling bỏ dòng có `confidence < 0.5` (mặc định `EasyOcrOptions`). Dòng tiếng Việt của latin_g2 có confidence 0.23–0.45 | Cần quyết định + benchmark. What-if với ngưỡng 0.0: CER 0.848 → 0.160, nhưng recall trường khoá vẫn chỉ 0.33–0.50 |
| P8B-6 | Trung bình — giới hạn đã biết | RapidOCR: `vb_xoay_scan` recall 0.33 < 0.8 | RapidOCR mặc định không xử lý trang xoay 90° (hành vi gốc, không đổi) | Ghi nhận; không đổi ngưỡng test |
| P8B-7 | Trung bình | Tesseract Fast đọc sai `1234/2024/QĐ-MẪU` ở 150 DPI (recall 0.83 < 0.9; Docker E2E FAIL). Cả hai Tesseract đọc `371.250.000` thành `371250000` trong `hon_hop` | Giới hạn chất lượng model ở độ phân giải này | Ghi nhận số đo; **không** hạ ngưỡng (`OCR_LOCAL_ACCEPTANCE.md` §4.4: ghi số đo trước khi đổi ngưỡng) |

Bổ sung sau review:

| # | Mức | Phát hiện | Nguyên nhân gốc (đã kiểm chứng) | Xử lý |
|---|---|---|---|---|
| P8B-8 | Cao (chế độ tuỳ chọn) | `OCR_RAPIDOCR_PERSISTENT=true` không bao giờ chuẩn bị được: mọi kiểm tra pipeline lỗi `TypeError: unsupported operand type(s) for /: 'str' and 'str'` | Loader pytorch của RapidOCR 3.9.2 (`networks/main.py:40`) tính `cfg.model_root_dir / name` mà không bọc `Path()`. Backend onnxruntime có bọc, nên kiểm chứng Phase 8A (overlay onnx) không thấy lỗi. Test cũ ghim đúng giá trị `str` gây lỗi | `d9652c0`: truyền `Path`. Chạy thật: trọng số `.pth` nằm trong `<OCR_DATA_DIR>/models/rapidocr`, OCR chạy. Test ghim `Path` + tripwire trên loader. Chế độ mặc định (tắt) không bị ảnh hưởng, nên kết quả Docker đầy đủ (build trước `d9652c0`) vẫn có giá trị |

### 9.4 Review độc lập diff 8B

Agent riêng, chỉ đọc mã và chạy test.

- Xác nhận sạch:
  - `HF_ENDPOINT` không gây pass giả hay fail giả: đã thử cả repo có cache và repo không có cache;
  - wrapper session đúng với mọi cách huggingface_hub gọi `Session.request`;
  - mọi đường xử lý tài liệu đã được phủ;
  - `APP_IMAGE` trong script dùng đúng image ở mọi bước;
  - test mới FAIL khi không có bản sửa.
- Low (đã xử lý ở `2128587`):
  - test Hub timeout phụ thuộc biến proxy / `HF_HUB_OFFLINE` của môi trường ⇒ test tự đặt môi trường;
  - D-24 cần nói rõ phạm vi toàn tiến trình ⇒ đã bổ sung.

## 10. Phase 8C — Chất lượng OCR (2026-11-13)

Báo cáo đầy đủ: [OCR_PHASE8C_REPORT.md](OCR_PHASE8C_REPORT.md). Tóm tắt kết quả kiểm thử:

| Kiểm thử | Kết quả |
|---|---|
| `tests/test_ocr_quality_prep.py` (mới, không cần engine) | 45 passed |
| `tests/test_ocr_integration.py`, strict, 4 engine | 38 PASS / 10 FAIL / 0 NOT VERIFIED (8B: 33 / 15) |
| `tests/test_ocr_integration.py -k tesseract_best` | 6 PASS / 3 FAIL (8B: 5 / 4) |
| `scripts/ocr/docker-acceptance.sh`, 4 engine, `OLD_REF=5e04227` | 72 PASS / 1 FAIL / 0 NOT VERIFIED |
| `pytest tests/` | 1211 passed / 10 failed / 44 skipped — cùng 10 lỗi của `main` |
| Frontend | lint 0 error (7 warning có sẵn), tsc 0, vitest 404/404, build OK |
| Bảo mật trực tiếp (stack nghiệm thu cô lập) | 16/16 |
| mypy / ruff | 33 / 1 — đều có sẵn |

- 10 bài FAIL còn lại và nguyên nhân: `OCR_PHASE8C_REPORT.md` §2. Bài #8 của Phase 8B
  (tesseract_best – hon_hop, recall) không tái hiện được khi đo lại baseline (`OCR_FAILURE_ANALYSIS.md` §5.4).
- Bài full pipeline giờ gọi `convert_document` (điểm vào mà worker chạy) thay cho `converter.convert`,
  để các bước của D-25 nằm trong phạm vi nghiệm thu. Ngưỡng, fixture, ground truth không đổi.
- Một unit test ghim nội dung config `tsv` được cập nhật theo D-25 (`tests/test_ocr_bundle_cli.py`).
- Script Docker: engine chỉ FAIL về nội dung vẫn đi tiếp các bước offline; ở đó văn bản phải trùng lúc
  online (so SHA-256). Lỗi nội dung vẫn được ghi FAIL một lần.

## 11. Phase 8D — Kiểm tra phát hành cuối (2026-11-13)

Báo cáo đầy đủ: [OCR_PHASE8D_REPORT.md](OCR_PHASE8D_REPORT.md).

| Kiểm thử | Kết quả |
|---|---|
| `tests/test_ocr_integration.py`, strict, 4 engine (bộ gốc) | 38 PASS / 10 FAIL / 0 NOT VERIFIED — không đổi |
| `-k tesseract_best` (bộ gốc) | 6 PASS / 3 FAIL — không đổi |
| `scripts/ocr/release_criteria.py` (bổ sung) | Best 7/7 (3 kèm KL-1) · Fast 5/7 · RapidOCR 7/7 · EasyOCR 2/7; critical 7/7 · 7/7 · 7/7 · 2/7 |
| `tests/test_ocr_release_criteria.py` | 13 passed |
| `tests/test_ocr_quality_prep.py` | 60 passed (15 mới) |
| Docker quick (Tesseract Best) | 42 PASS / 0 FAIL (lượt đầu 41 / 1: lỗi script P8D-1) |
| Docker 4 engine | 74 PASS / 1 FAIL (nội dung EasyOCR) / 0 NOT VERIFIED |
| Docker RapidOCR persistent (torch) | 42 PASS / 0 FAIL |
| Docker image không có Tesseract (RapidOCR, EasyOCR) | 50 PASS / 1 FAIL (nội dung EasyOCR) / 0 NOT VERIFIED |
| `pytest tests/` | 1239 passed / 10 failed / 44 skipped — cùng 10 lỗi của `main` |
| Frontend | lint 0 error, tsc 0, vitest 408/408, build OK |
| Bảo mật | 142 passed; trực tiếp 16/16 |

- **P8D-1 (script nghiệm thu, đã sửa `c5162df`):** `docker logs | grep -q` dưới `pipefail` báo FAIL sai ở
  bước "worker log shows …". Lượt quick đầu: 41 PASS / 1 FAIL do lỗi này; dòng log có thật trong container.
- Lượt Docker full đầu bị ngắt giữa chừng khi phiên làm việc kết thúc (`docker-full-8d.run1-interrupted.log`);
  script đã tự dọn container. Chạy lại bằng tiến trình tách rời.
- Xác minh KL-1: với Tesseract Best, assertion tiêu đề là assertion **duy nhất** thất bại ở cả 3 bài. Với
  Tesseract Fast còn thêm `table_rows` (nhãn `Tổng cộng`), nên ngoại lệ không áp dụng.

## 12. Phase 9A — Cổng bảo mật cuối (2026-11-13)

Báo cáo đầy đủ: [OCR_PHASE9A_REPORT.md](OCR_PHASE9A_REPORT.md).

| Kiểm thử | Kết quả |
|---|---|
| `tests/test_url_ingestion_switch.py` (mới) | 43 passed |
| `tests/test_ocr_local_benchmark.py` (mới) | 4 passed |
| `tests/test_ocr_quality_prep.py` | 62 passed (2 mới: khóa pdfium, bọc lỗi Hub timeout) |
| `pytest tests/` | 1288 passed / 10 failed / 44 skipped — cùng 10 lỗi của `main` |
| Test bảo mật (`-k security/guard/commands/auth/url`) | 185 passed |
| Frontend | lint 0 error, tsc 0, vitest 411/411 (3 mới), build OK |
| Bộ gốc 48 bài, strict (chạy lại) | 38 PASS / 10 FAIL / 0 NOT VERIFIED |
| `-k tesseract_best` (chạy lại) | 6 PASS / 3 FAIL |
| `scripts/ocr/release_criteria.py` (chạy lại) | Best 7/7 (3 kèm KL-1) · Fast 5/7 · RapidOCR 7/7 · EasyOCR 2/7; critical 7/7 · 7/7 · 7/7 · 2/7 |
| Docker quick (Tesseract Best), URL ingestion tắt | 42 PASS / 0 FAIL |
| Trực tiếp trên stack cô lập: công tắc URL / bảo mật / đồng thời | 7/7 PASS · 16/16 · 6/6 |

- 13 test có sẵn kiểm tra hành vi khi URL được bật; 6 module đó giờ bật công tắc tường minh bằng fixture.
  Không test nào bị xóa, skip hay nới lỏng.
- Bộ test mới bắt được thiếu sót của bản vá đầu (hàm tải của lớp OCR chưa có chốt chặn): fixture chặn mạng
  ghi nhận một lần thử phân giải DNS; đã sửa trước khi commit.
- Sai sót thao tác đã hoàn tác: một lệnh `ruff format tests` định dạng lại 40 file test không liên quan; đã
  `git checkout` toàn bộ rồi chỉ áp lại thay đổi có chủ đích. `tests/test_ocr_integration.py` và fixture
  không đổi.
