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
