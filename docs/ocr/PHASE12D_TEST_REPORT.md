# Phase 12D — Báo cáo kiểm thử và regression (Cloud)

Môi trường: Claude Code Cloud, Python 3.12 + `uv sync --all-extras` theo `uv.lock` (docling 2.129.0, docling-core
2.96.0, content-core 2.0.7), Node 22, Tesseract 5.3.4 + `vie` (Ubuntu), không Docker daemon, Hugging Face và host
tải tiktoken bị chặn. `pytest-timeout` cài **cục bộ** (không thêm vào dependency) để test cần mạng thất bại sau 90 s
thay vì treo.

## 1. Baseline v1.2.0 (đo lại trên Cloud, cùng môi trường)

| Bộ | Tham chiếu | Đo trên Cloud | Giải thích chênh lệch |
|---|---|---|---|
| Backend toàn bộ | 1792 pass / 10 lỗi / 64 skip | **1789 pass / 13 fail / 64 skip** (1866) | 10 lỗi có sẵn giống tham chiếu (`test_domain::test_content_settings_defaults` — mặc định `docling`; 9 `test_models_api::TestModelsProviderAvailability`). +3 `test_chunking` (CJK, plain, secondary) cần tải bảng mã tiktoken từ `openaipublic.blob.core.windows.net` — bị proxy Cloud chặn ⇒ lỗi môi trường |
| OCR (`tests/test_ocr_*.py`, worktree tại `f2fdf27`) | 640 pass | **633 pass / 64 skip** | engine Tesseract fast/best không "ready" trong sandbox (skip `NOT VERIFIED`), Tesseract 5.3.4 thay vì 5.5.0 |
| Frontend (vitest) | 423 pass | **423 pass** | — |

Số OCR là một **tập con** của backend, không cộng dồn.

## 2. Sau Phase 12

| Bộ | Kết quả | So với baseline |
|---|---|---|
| Backend toàn bộ | **2122 pass / 13 fail / 65 skip** (2200) | 13 lỗi **giống hệt từng tên** baseline (diff rỗng); +333 pass mới; +1 skip mới (§3) |
| OCR (`tests/test_ocr_*.py`) | **936 pass / 65 skip** | 633 test cũ vẫn pass; +303 mới |
| Test mới Phase 12 | `test_ocr_legal_normalizer.py` 269, `test_ocr_legal_pipeline.py` 28, `test_ocr_phase12_scripts.py` 7 (1 skip khi chạy cả bộ), `test_offline_package.py` 30 | tất cả pass |
| Frontend vitest | **430 pass** (63 file) | +7 (4 OcrEngineManager, 3 markdown-renderer) |
| `tsc --noEmit` | 0 lỗi | |
| `npm run lint` | 0 lỗi, 7 cảnh báo (đều ở file không sửa, có từ trước) | |
| `ruff check` / `ruff format` (file mới/sửa) | sạch | |
| `mypy` (file backend sửa) | sạch | |
| `bash -n` + `shellcheck -S warning` (script mới) | sạch | |
| PowerShell | không chạy được (Cloud không có PowerShell) | NOT EXECUTED |

Regression **mới**: không có. Trong quá trình làm, bộ đầy đủ phát hiện 8 lỗi do test cũ dùng đối tượng cài đặt giả
không có trường mới → `_config` đã đổi sang `getattr` (an toàn với bản ghi cũ) — đã sửa và chạy lại toàn bộ.

## 3. Skip mới

`test_ocr_phase12_scripts.py::test_direct_tesseract_layer_is_real` skip khi chạy chung cả bộ (một test khác đặt
`TESSDATA_PREFIX` tạm thời nên `tesseract --list-langs` không thấy `vie`); chạy riêng file thì **pass** với Tesseract
thật. Không phải lỗi sản phẩm.

## 4. Ma trận test bắt buộc (7.2) → test

| Yêu cầu | Test |
|---|---|
| OFF không đổi nội dung | `test_convert_file_standard_is_byte_identical`, `test_default_config_standard_keeps_content_core`, `test_settings_*` |
| ON | `test_convert_file_legal`, toàn bộ parametrized trên 24 fixture |
| Placeholder đơn lẻ / kèm caption / literal comment | f01, f15, f17, f18 (`test_placeholders_and_warnings`, `test_protected_fields_exact`) |
| Chữ ký, con dấu | f01, f17 |
| Số trang, header/footer lặp, footnote | f02–f04, f07, f13, f14, f22, f23 (`test_artifact_lines_*`, `test_running_header_only_when_repeated_exactly`) |
| Số điều khoản riêng một dòng | f08 (`2024`, `15` giữ), f22 |
| Nối liên trang / không nối khoản mới | f02, f03, f04, f11, f19, f20, f24 (`test_joins_and_non_joins`) |
| Danh sách từ 5/10, không liên tục, nhiều cấp | f05, f06, f21 (`test_standard_renumbers_but_legal_does_not`, `test_synthesized_number_avoided`) |
| Điều/Khoản/Điểm, ngày, tiền, %, URL | f07, f08 (`test_protected_fields_exact`) |
| Bảng | f09, f10 (`test_tables_identical`) |
| Thứ tự đọc | `test_reading_order_not_changed` (24 fixture) |
| Trang trắng | f11 |
| PDF hỗn hợp | biến thể `mixed` của generator (pipeline thật: Local) |
| Không provenance | `test_document_without_provenance_keeps_everything` |
| Document lỗi / fallback / giới hạn | `test_fallback_on_failure_keeps_standard`, `test_limits_fall_back`, `test_malformed_object_falls_back_without_raising`, `test_convert_file_legal_failure_keeps_standard` |
| Idempotency, determinism, tài liệu gốc không đổi | `test_idempotent_and_deterministic`, `test_source_document_untouched` (24 fixture) |
| Không network | `test_no_network_calls` |
| Không mất nội dung hợp lệ | `test_no_valid_content_lost` (24 fixture) |
| Định dạng không thuộc phạm vi | `test_legal_does_not_reroute_other_formats` (ảnh, docx, xlsx, html, md), `test_convert_file_legal_skips_non_pdf_and_non_markdown`, `test_only_pdf_is_supported` |
| RAG nhất quán | `test_source_graph_stores_normalized_text_and_embeds_it`, `test_normalized_text_chunks_without_losing_content` |
| API / quyền | `test_api_*`, `test_config_endpoint_is_admin_only` |
| Bảo mật nội dung | `test_html_and_markdown_injection_not_introduced`, `test_escape_block_start`, `test_summary_contains_no_text` |
| Hiệu năng | `test_large_document_is_fast` (300 trang), `test_very_long_text_item` |

## 5. Integration test (7.3) — mức xác minh

| Hạng mục | Mức |
|---|---|
| RapidOCR mặc định → lớp Docling khi bật Legal; Tesseract Fast/Best, EasyOCR định tuyến không đổi | MOCK VERIFIED |
| Tesseract Agri | MOCK VERIFIED (đường mã chung với Tesseract); **chất lượng Agri thực tế: NOT VERIFIED** |
| Layout Heron, TableFormer, Auto Full Page, Force Full Page trên PDF | NOT VERIFIED (cần model) — parity options cũ vẫn pass |
| OCR Engine Manager, Custom Model Manager, pinning, rollback model, readiness | test cũ (633) vẫn pass; không đổi mã |
| Source ingestion, chunking, embedding (mock), RAG (mock) | MOCK VERIFIED |
| DoclingDocument do ReadingOrderModel thật tạo | REAL (post-layout) VERIFIED trên fixture |

## 6. Release gates (7.5)

| Gate | Kết quả Cloud |
|---|---|
| Không regression mới | ĐẠT (13 lỗi giống hệt baseline) |
| Test bảo toàn dữ liệu quan trọng | ĐẠT trên fixture; tài liệu thật: PENDING |
| Không HIGH/CRITICAL mới | ĐẠT ([PHASE12D_SECURITY_REVIEW.md](PHASE12D_SECURITY_REVIEW.md)) |
| Không đổi hành vi khi tắt | ĐẠT (unit, byte-identical); pipeline thật: PENDING |
| Không mất nội dung hợp lệ / không đánh số sai / không hỏng bảng | ĐẠT trên fixture |
| Không gọi Internet trong normalizer | ĐẠT |
| Overhead ≤ 10% | ước tính < 1% (2,5 ms/trang); đo thật: PENDING |

Gate nào cần pipeline thật được để **PENDING**, không hạ tiêu chí.
