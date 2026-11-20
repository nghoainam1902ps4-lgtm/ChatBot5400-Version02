# Phase 12D3 — Báo cáo hồi quy

So sánh ba mốc trên **cùng môi trường Cloud** (Python 3.12.3, Docling 2.129.0, docling-core 2.96.0, content-core
2.0.7, Tesseract 5.3.4 có `vie`, `ssh-keygen`; **không** có Docker daemon, PowerShell, SurrealDB, Layout Heron /
TableFormer; Hugging Face và host bảng mã tiktoken bị proxy chặn):

| Mốc | Commit |
|---|---|
| v1.2.0 (baseline) | `f2fdf2714a7c0b5b196132f71cfc091928befc06` |
| Phase 12 trước remediation (HEAD đã audit) | `2ef007417eaca0ce41e7aba2e32a201fa243ebf1` |
| Phase 12D3 | `7c23329` (mã nguồn; các commit sau chỉ thêm tài liệu) |

Lệnh: `python -m pytest tests/ -p no:cacheprovider --timeout=120 -q -rfs` (pytest-timeout chỉ cài trong môi trường
kiểm thử, không phải dependency của dự án).

## 1. Backend — tổng số

| | v1.2.0 | Phase 12 (2ef0074) | Phase 12D3 |
|---|---|---|---|
| Thu thập | 1 866 | 2 200 | **2 502** |
| Passed | 1 789 | 2 122 | **2 424** |
| Failed | 13 | 13 | **13** (cùng 13 tên) |
| Skipped | 64 | 65 | 65 |
| xfail / xpass | 0 | 0 (nhánh audit: 17 xfail) | **0 / 0** |
| Thời gian | 8 ph 07 s | 8 ph 19 s | 16 ph 12 s |

Số test của Phase 12 trước remediation **không so sánh được về độ phủ** với Phase 12D3: 101 / 144 ca tham số hóa cũ
không khẳng định gì (T-03) và đã bị loại bỏ; bộ test normalizer và offline được viết lại.

## 2. Backend — so tên test lỗi

Tập test lỗi ở Phase 12D3 **trùng từng tên** với v1.2.0 và với Phase 12 trước remediation. Không có lỗi mới; không có
lỗi nào được "sửa" bằng skip hay xfail.

| # | Test | v1.2.0 | 2ef0074 | 12D3 | Nguyên nhân |
|---|---|---|---|---|---|
| 1 | `tests/test_chunking.py::TestChunkText::test_cjk_text_is_chunked_by_tokens` | FAIL | FAIL | FAIL | **môi trường**: tiktoken cần tải `o200k_base`, host bị proxy chặn, chờ tới timeout |
| 2 | `tests/test_chunking.py::TestChunkText::test_explicit_content_type_plain` | FAIL | FAIL | FAIL | như trên |
| 3 | `tests/test_chunking.py::TestChunkText::test_secondary_chunking_for_large_sections` | FAIL | FAIL | FAIL | như trên |
| 4 | `tests/test_domain.py::TestContentSettings::test_content_settings_defaults` | FAIL | FAIL | FAIL | lỗi nền có từ trước Phase 12 |
| 5–13 | `tests/test_models_api.py::TestModelsProviderAvailability::` `test_blank_anthropic_compatible_env_vars_are_unavailable`, `test_generic_env_var_enables_all_modes`, `test_mode_specific_env_vars_llm_embedding`, `test_no_env_vars_set`, `test_mixed_config_generic_and_mode_specific`, `test_individual_mode_llm_only`, `test_individual_mode_embedding_only`, `test_individual_mode_stt_only`, `test_individual_mode_tts_only` | FAIL | FAIL | FAIL | lỗi nền có từ trước Phase 12 |

Về 3 test `test_chunking` (yêu cầu của 12D3E):

- Bộ mã hóa dùng: `o200k_base` (`open_notebook/utils/token_utils.py::TIKTOKEN_ENCODING`).
- Đường dẫn cache: `TIKTOKEN_CACHE_DIR` (trong image: `/app/tiktoken-cache`, tạo lúc build — Dockerfile); tên file =
  SHA-1 của URL blob (`fb374d419588a4632f3f557e76b4b70aebbca790`), SHA-256 kỳ vọng
  `446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d`.
- Ở Cloud cache **không tồn tại** và không tải được ⇒ 3 test này vẫn FAIL như ở v1.2.0. Tôi **không** skip, không
  mock, không đánh dấu xfail chúng.
- Đã sửa trong sản phẩm: khi `OCR_OFFLINE=true` và thiếu file cache, `token_count` dùng ước lượng theo từ thay vì cố
  tải (`tests/test_token_utils_offline.py`, 4 test, PASS); inventory của gói kiểm file cache theo tên + SHA-256 và việc
  nạp khi `--network none`; health check của công cụ offline kiểm tách đoạn trong container mới.
- **Cổng Local**: trên máy có Internet 3 test này phải PASS (W-PIPE-03); tách đoạn khi mạng bị chặn thật (W-RAG-06).

## 3. Backend — skip

| Số test | File | Lý do |
|---|---|---|
| 39 | `tests/test_ocr_integration.py` | NOT VERIFIED: full pipeline not enabled (set OCR_FULL_PIPELINE=1 or OCR_ACCEPTANCE_STRICT=1) |
| 16 | `tests/test_ocr_auto_full_page_pipeline.py` | full pipeline not enabled (set OCR_FULL_PIPELINE=1) |
| 3 | `tests/test_ocr_integration.py` | NOT VERIFIED: tesseract_fast not ready here: OCR engine 'Tesseract Vietnamese Fast' is selected but its runtime is incompatible: TESSDATA_PREFIX=/tmp/pytest-of-root/pytest-44/test_build_options_pins_the_ve0/ocr/models/tesseract differs from the OCR models directory /home/user/ChatBot5400-Version02/data/ocr/models/tesseract. Unset it or set it to /home/user/ChatBot5400-Version02/data/ocr/models/tesseract. Open Settings → OCR Engine Manager. |
| 2 | `tests/test_ocr_integration.py` | NOT VERIFIED: easyocr not ready here: OCR engine 'EasyOCR Vietnamese' is selected but its model is not_installed. Reinstall it in Settings → OCR Engine Manager. |
| 2 | `tests/test_ocr_integration.py` | NOT VERIFIED: tesseract_best not ready here: OCR engine 'Tesseract Vietnamese Best' is selected but its runtime is incompatible: TESSDATA_PREFIX=/tmp/pytest-of-root/pytest-44/test_build_options_pins_the_ve0/ocr/models/tesseract differs from the OCR models directory /home/user/ChatBot5400-Version02/data/ocr/models/tesseract. Unset it or set it to /home/user/ChatBot5400-Version02/data/ocr/models/tesseract. Open Settings → OCR Engine Manager. |
| 1 | `tests/test_ocr_custom_models.py` | needs the tesseract executable and OCR_TEST_REAL_TRAINEDDATA=<lstm model> |
| 1 | `tests/test_ocr_phase12_scripts.py` | Vietnamese Tesseract data not installed |
| 1 | `tests/test_ocr_quality_prep.py` | Tesseract runtime / Vietnamese model not installed |
| **65** | | |

Không skip nào mới được thêm trong Phase 12D3 (65, bằng Phase 12 trước remediation). 64 skip là cổng "pipeline đầy
đủ" và engine chưa cài, có từ v1.2.0 (`OCR_FULL_PIPELINE` / `OCR_ACCEPTANCE_STRICT`): cần Layout Heron + TableFormer +
engine thật ⇒ nghiệm thu Local.

**Một skip phụ thuộc thứ tự chạy** (có từ Phase 12, không phải của 12D3):
`tests/test_ocr_phase12_scripts.py::test_direct_tesseract_layer_is_real` bị skip trong lượt chạy toàn bộ vì các test
OCR chạy trước nó đặt `TESSDATA_PREFIX` sang thư mục tạm, khiến `tesseract --list-langs` không còn thấy `vie`. Chạy
riêng file này thì test đó **chạy và đạt** (8 passed, 0 skipped). Vì vậy lớp "Tesseract trực tiếp" chỉ được coi là đã
kiểm ở lượt chạy riêng; nên sửa sự cô lập môi trường của bộ test OCR ở một thay đổi riêng (ngoài phạm vi 12D3).

## 4. Bộ test của Phase 12 / 12D3

| Bộ | Số test | Kết quả | Ghi chú |
|---|---|---|---|
| `tests/review_phase12d2/` (phản ví dụ của audit, giữ nguyên thân test và nguồn) | 32 | 32 passed, **0 xfail** | trước remediation: 18 failed / 14 passed với `--runxfail` |
| `tests/test_ocr_legal_normalizer.py` | 385 | passed | viết lại; oracle độc lập; 45 fixture |
| `tests/test_ocr_legal_pipeline.py` | 35 | passed | gồm `test_convert_file_standard_is_byte_identical` (giữ nguyên) |
| `tests/test_offline_package.py` | 172 | passed | Docker giả lập có trạng thái; git / tar / ssh-keygen thật; các test chữ ký **chạy**, không skip |
| `tests/test_ocr_phase12_scripts.py` | 8 | chạy riêng: 8 passed; trong lượt chạy toàn bộ: 7 passed + 1 skipped (xem §3) | gồm lớp Tesseract trực tiếp thật khi chạy riêng |
| `tests/test_token_utils_offline.py` | 4 | passed | |

Bằng chứng RED trước khi sửa (lưu trong repository):

| File | Nội dung |
|---|---|
| `docs/review/phase12d3/red_audit_tests_before_fix.txt` | test phản ví dụ của audit chạy với `--runxfail` trên mã chưa sửa: 18 failed, 14 passed |
| `docs/review/phase12d3/red_new_oracle_before_fix.txt` | bộ test oracle mới trên implementation v1.0.0: 83 failed, 297 passed |
| `docs/review/phase12d3/oracle_before_remediation.json` | số đo của oracle mới trên v1.0.0 |
| `docs/review/phase12d3/oracle_after_remediation.json` | số đo trên v1.1.0 |

## 5. Frontend

| | v1.2.0 | Phase 12 (2ef0074) | Phase 12D3 |
|---|---|---|---|
| `npm run test` (vitest) | 63 file / 423 test passed | 63 / 430 passed | **64 file / 437 test passed** |
| `npx tsc --noEmit` | 0 lỗi | 0 lỗi | 0 lỗi |
| `npm run lint` | 0 lỗi, 7 cảnh báo | 0 lỗi, 7 cảnh báo | 0 lỗi, 7 cảnh báo (cùng 7 cảnh báo có từ trước) |

Kiểm thử frontend chạy trên jsdom; hiển thị trên trình duyệt thật là cổng Local (W-LEG-17).

## 6. Kiểm tra tĩnh trên file đã đổi

| Công cụ | Phạm vi | Kết quả |
|---|---|---|
| `ruff check` | 22 file Python đã đổi / thêm trong 12D3 | sạch (lỗi I001 ở `tests/test_auth.py` là lỗi nền, không thuộc 12D3) |
| `ruff format --check` | cùng 22 file | 21 sạch; `open_notebook/domain/notebook.py` chưa format **từ v1.2.0** — không format lại để giữ diff tối thiểu (chỉ thêm trường `extraction`) |
| `mypy` | `open_notebook/ocr/legal_normalizer.py`, `open_notebook/ocr/docling_extract.py`, `open_notebook/utils/token_utils.py`, `open_notebook/domain/notebook.py`, `open_notebook/graphs/source.py`, `api/models.py`, `api/routers/sources.py`, `scripts/offline/offline_package.py`, `scripts/ocr/phase12_benchmark.py`, `scripts/ocr/phase12_metrics.py` | 0 lỗi |
| `shellcheck`, `bash -n` | `scripts/offline/*.sh` | sạch |
| `bandit -ll` | `scripts/offline/offline_package.py` | 0 High, 1 Medium (B608, hằng số — xem báo cáo an toàn §7) |
| PowerShell | `build-package.ps1`, `phase12-test.ps1` | **không chạy được ở Cloud** — chỉ kiểm tĩnh thứ tự lệnh của `build-package.ps1` |

## 7. Bất biến đã kiểm lại

| Bất biến | Cách kiểm | Kết quả |
|---|---|---|
| Standard giống v1.2.0 từng byte | `test_convert_file_standard_is_byte_identical`, `test_default_config_standard_keeps_content_core` | đạt |
| Source Standard lưu giống v1.2.0 (không có khóa mới) | `test_asset_record_round_trip_and_v120_compatibility`, `test_convert_file_standard_never_carries_a_record` | đạt (tầng model; SurrealDB thật: cổng Local) |
| Không migration | `test_source_table_needs_no_migration_for_the_record`; `git diff f2fdf27 -- open_notebook/database/migrations` rỗng | đạt — schema 33 |
| Không đổi dependency | `git diff f2fdf27 -- pyproject.toml uv.lock frontend/package.json frontend/package-lock.json` rỗng | đạt |
| `VERSION` = 1.2.0 | `test_version_rule_on_the_real_repository` | đạt |
| Legal mặc định OFF, hai công tắc | `test_settings_default_is_standard`, `test_settings_legal_needs_the_gate`, `test_api_refuses_legal_without_gate`, `test_deployment_gate` | đạt |
| Không gọi mạng trong normalizer | `test_no_network_calls` | đạt |
| Công cụ offline không gọi lệnh phá hủy | `_assert_safe_calls` trên mọi luồng; `test_tool_source_has_no_destructive_or_wildcard_commands` | đạt (mock) |

## 8. Chưa chạy — không được coi là đã xác minh

Docker build thật · `docker save` / `load` thật · Docker Compose thật · PowerShell · Layout Heron · TableFormer ·
RapidOCR / Tesseract fast-best / EasyOCR / Agri trong pipeline đầy đủ · SurrealDB thật · trình duyệt thật · nâng cấp và
rollback offline thật · chặn mạng thật · Python 3.8 / 3.10 cho công cụ offline.
