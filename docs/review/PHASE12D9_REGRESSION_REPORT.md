# Phase 12D9 — Báo cáo hồi quy

Môi trường Cloud: Linux, Python 3.12.3 (`.venv` của repo), docling 2.129.0, docling-core 2.96.0, content-core 2.0.7,
pandas 3.0.0, surrealdb SDK 1.0.8 (engine nhúng cho test E2-04), Tesseract 5.3.4 với `vie` + `eng` + `osd`, DejaVu,
Node (frontend), Docker (daemon cục bộ, chỉ image thử `busybox:1.36` có sẵn — không kéo image). Bảng mã tiktoken **thật**
`o200k_base` qua `TIKTOKEN_CACHE_DIR` (SHA-256 `446a9538…cfb1a2d`, khớp giá trị chính thức) ⇒ **không test nào bị
deselect** (D8-09). **Không có:** Windows, PowerShell, model layout thật (Layout Heron, TableFormer), model Agri, model
embedding / provider LLM, Docker Desktop, image ứng dụng thật.

Mốc so sánh: báo cáo 12D7 (`c4ed2b3` / `4587eb7`): 3047 passed / 10 failed / 73 skipped / 3 deselected; 10 lỗi cũ:
`tests/test_domain.py::TestContentSettings::test_content_settings_defaults` và 9 ×
`tests/test_models_api.py::TestModelsProviderAvailability::*` (`test_blank_anthropic_compatible_env_vars_are_unavailable`,
`test_generic_env_var_enables_all_modes`, `test_individual_mode_embedding_only`, `test_individual_mode_llm_only`,
`test_individual_mode_stt_only`, `test_individual_mode_tts_only`, `test_mixed_config_generic_and_mode_specific`,
`test_mode_specific_env_vars_llm_embedding`, `test_no_env_vars_set`) — mock nhận 1 tham số, mã gọi 2; có từ trước, ngoài
phạm vi.

## 1. Backend `tests/` — hai lượt đầy đủ

Lệnh: `TIKTOKEN_CACHE_DIR=<cache> .venv/bin/python -m pytest tests/ -q -p no:cacheprovider -rfEsxX --timeout=900`.

| Lượt | Commit | Kết quả | So với mốc |
|---|---|---|---|
| 1 | `70f7325` | 3450 passed / **11 failed** / 67 skipped, 22 phút | 10 lỗi cũ cùng tên **+ 1 lỗi mới**: `tests/test_phase12d7_standard_parity.py::test_standard_differs_only_where_the_old_parser_rewrote_a_token` |
| 2 | `662c47e` | **3461 passed / 10 failed / 67 skipped**, 0 deselected, 0 xfailed, 0 xpassed, 23 phút | 10 lỗi **cùng tên** với mốc (so từng tên: giống hệt); không lỗi mới. Số test tăng (+414 so với 3047) là test mới của 12D8 / 12D9; skip giảm 73 → 67 và 3 test `test_chunking` trước đây bị deselect nay chạy và đạt (bảng mã thật) |

**Lỗi mới của lượt 1 — nguyên nhân và sửa.** Test parity của 12D7 đưa TSV **không có sidecar provenance** cho cổng
Standard; cổng v2 từ chối đúng thiết kế (D8-STD-03: bằng chứng không xác thực ⇒ mã 3). Test được sửa để ghi sidecar như
công cụ xuất (cùng crop, cùng model, SHA-256 model) — mọi khẳng định giữ nguyên, có chú thích `# was:` (`42ff481`). Không
phải lỗi của ứng dụng.

Sau lượt 2 chỉ có các commit không đổi mã ứng dụng: `520d3e3` (công cụ tiêm lỗi `fail-osd` + test), `1f32e48` (đổi tên
một biến trong oracle — không đổi hành vi; format 2 file test) và `4b3e1d1` (chỉ chú thích kiểu trong test). Các bộ liên
quan chạy lại trên commit cuối `4b3e1d1`: oracle / Legal / cổng Standard / parity / `test_chunking` **795 passed**; 6 file
sửa kiểu **292 passed**; E2-04 + chẩn đoán crop **29 passed**; công cụ tiêm lỗi **9 passed**; 3 test `test_chunking` từng
bị deselect (`TestChunkText::test_cjk_text_is_chunked_by_tokens`, `::test_explicit_content_type_plain`,
`::test_secondary_chunking_for_large_sections`) **PASSED**.

### Test bị skip (lượt 2)

| Số test | Vị trí | Lý do |
|---|---|---|
| 16 | `tests/test_ocr_auto_full_page_pipeline.py` | pipeline đầy đủ chưa bật (`OCR_FULL_PIPELINE=1`) |
| 39 | `tests/test_ocr_integration.py:347, 364, 453` | pipeline đầy đủ chưa bật (`OCR_FULL_PIPELINE=1` / `OCR_ACCEPTANCE_STRICT=1`) |
| 7 | `tests/test_ocr_integration.py:41` | model Tesseract Fast / Best / EasyOCR của **ứng dụng** chưa cài trong thư mục model ở Cloud (Tesseract hệ thống có `vie`) |
| 1 | `tests/test_ocr_custom_models.py:1758` | cần `OCR_TEST_REAL_TRAINEDDATA` (model LSTM thật) |
| 1 | `tests/test_ocr_quality_prep.py:662` | model tiếng Việt của ứng dụng chưa cài |
| 3 | `tests/test_offline_real_docker.py`, `tests/test_offline_manual_fallback_real_docker.py` | cần `CB5400_REAL_DOCKER=1` — chạy riêng ở §3 |
| **67** | | |

## 2. Bộ test mới / sửa của 12D9

| Bộ | Kết quả | RED trên `4587eb7` |
|---|---|---|
| `tests/test_phase12d9_text_preservation.py` (D8-03, D8-02, bảo vệ, nơi áp dụng) | 63 passed | 44 failed + 11 errors / 8 passed (control) |
| `tests/test_phase12d9_ocr_failure_safety.py` (E2-04, Tesseract thật + SurrealDB thật) | 25 passed | 23 failed / 1 passed (24 test lúc đó) |
| `tests/test_phase12d9_standard_gate.py` (cổng v2 trên OCR thật) | 25 passed | — (công cụ mới) |
| `tests/test_phase12d9_tesseract_fault.py` (công cụ tiêm lỗi cho cổng Windows) | 9 passed | — |
| `tests/test_phase12d9_crop_diagnose.py` (E2-01 / E2-02, metadata-only) | 4 passed | — |
| `tests/review_phase12d8/` (bộ audit 12D8: 204 passed / 71 xfailed strict lúc nhập) | **275 passed, 0 xfailed** trên commit cuối (= 204 + 71: mọi xfail strict nay là test đạt; D8-08 giữ test control) | xfail của finding đã sửa được gỡ, mỗi chỗ `# was:` |
| benchmark 92 fixture (Legal 1.3.1, oracle đã vá) | khớp file đã commit (`tests/review_phase12d8/test_oracle_d8.py`) | — |

## 3. Docker thật (diễn tập offline)

`CB5400_REAL_DOCKER=1 pytest tests/test_offline_real_docker.py tests/test_offline_manual_fallback_real_docker.py` (Docker 29.10.0, daemon cục bộ của container Cloud, image thử `busybox:1.36` đã có sẵn): **3 passed** (295 s). Danh sách image, container, volume **trước = sau** (so file); không kéo image nào.

## 4. Frontend (`frontend/`)

12D9 không đổi frontend.

| Lệnh | Kết quả |
|---|---|
| `npm run test -- --run` | 64 file, **438 / 438** |
| `npx tsc --noEmit` | sạch |
| `npm run lint` | 0 lỗi, 7 cảnh báo cũ trong file không đổi |
| `npm run build` | đạt (không thay đổi file nào được theo dõi) |

## 5. Lint và kiểu

| Lệnh | Kết quả |
|---|---|
| `ruff check` trên 38 file Python 12D9 thêm / sửa | sạch |
| `ruff check .` | 2 lỗi — đều có từ trước, file 12D9 không đổi (`tests/test_auth.py` I001, `tests/test_url_ingestion_switch.py` F811) |
| `ruff format --check` | file mới / sửa của 12D9 đã format; `tests/test_offline_package.py`, `tests/test_offline_real_docker.py`, `scripts/offline/offline_package.py` không format lại toàn file (đã không format từ trước, tránh diff lớn) |
| `mypy` trên 15 file nguồn 12D9 sửa | **sạch** (2 lỗi mới do 12D9 ở `phase12_oracle.py` — tên biến dùng lại — đã sửa ở `1f32e48`; mypy của công cụ xuất sửa ở `662c47e`) |
| `python -m mypy .` | **81 lỗi** trong 18 file — **bằng mốc 12D7 (81)**, không lỗi mới. Lượt đầu 104: 23 lỗi kiểu trong file test của 12D9 và bộ audit 12D8 nhập vào ⇒ sửa **chỉ chú thích kiểu** ở `4b3e1d1` (post-processor nhận `LayoutPostprocessorOptions` — đúng kiểu và cùng giá trị mà stage của Docling truyền), 6 file chạy lại 292 passed |
| `mypy --platform win32 scripts/offline/offline_package.py` | 5 lỗi `geteuid` — **giống mốc**, chỉ ở các hàm máy chủ Ubuntu, không thuộc đường build |
| `offline_package.py` | parse được với cú pháp Python 3.8 |

## 6. Không chạy, nên không được xác minh

Windows, PowerShell 5.1 / 7, Docker Desktop, image ứng dụng thật, pipeline OCR đầy đủ trên PDF thật (Layout Heron,
TableFormer, Agri), model embedding, trình duyệt thật, script vận hành production. Danh sách cổng:
[PHASE12D9_LOCAL_ACCEPTANCE_CHECKLIST.md](PHASE12D9_LOCAL_ACCEPTANCE_CHECKLIST.md).
