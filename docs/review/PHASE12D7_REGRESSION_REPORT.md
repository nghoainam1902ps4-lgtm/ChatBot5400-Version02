# Phase 12D7 — Báo cáo hồi quy

Môi trường Cloud: Linux, Python 3.12 (`.venv`), Docling 2.129.0, docling-core 2.96.0, pandas 3.0, Tesseract 5.3.4 +
`vie` + `osd`, Node (frontend). **Không có**: Windows, PowerShell, model layout của Docling (Layout Heron,
TableFormer), tài liệu thật, model Agri. Mạng ra ngoài bị proxy chặn ⇒ tiktoken không tải được bảng mã: hai lượt như
12D5 (không cache; với file `o200k_base` thật đã kiểm SHA-256).

Baseline: Phase 12D5, `904c15c` — **2917 passed / 10 failed / 73 skipped / 3 deselected** (cùng môi trường).

## 1. Backend — toàn bộ `tests/` (không cache tiktoken)

Lệnh: `pytest tests/ -q -p no:cacheprovider -rfEsxX --timeout=900` với 3 test `test_chunking` cần tải bảng mã được bỏ
chọn (như 12D5; chạy với bảng mã thật ở §2). Mã ở `edc6d9c` (test thu thập lúc bắt đầu; `dde8645` chỉ đổi chế độ
`--crops` của công cụ chẩn đoán + 1 test, `c4ed2b3` chỉ sửa kiểu — cả hai chạy riêng ở §4 và §7).

| | Baseline 12D5 `904c15c` | **Phase 12D7** |
|---|---|---|
| passed | 2917 | **3047** |
| failed | 10 | **10** — cùng tên |
| skipped | 73 | 73 — cùng lý do |
| deselected | 3 | 3 |
| xfailed / xpassed | 0 / 0 | 0 / 0 |
| thời gian | 15 phút 58 | 18 phút 34 |

**Không có thất bại mới** (so theo tên). 10 thất bại có từ trước (baseline 12D5; theo 12D3 / 12D4 cũng có ở v1.2.0),
không liên quan 12D7: `tests/test_models_api.py::TestModelsProviderAvailability` (9 — mock `env_side_effect` nhận 1
tham số, mã gọi với 2: `TypeError`) và `tests/test_domain.py::TestContentSettings::test_content_settings_defaults`
(mặc định `docling`, test mong `auto`). +130 test đạt = 124 test của 7 file mới (§4; file hướng xoay có 17 test lúc chạy) + 2 test offline của E0-07 + 4
test Legal mới (2 hàm, một hàm 3 trường hợp E1-09); 5 test Legal về phép
nối được viết lại thành "không nối" (`test_join_baseline_is_made` → `test_join_baseline_is_not_made`,
`test_joins_made_when_the_evidence_is_sufficient` → `test_no_cross_page_join_even_where_the_old_rules_joined`,
`test_many_joins_scale_linearly` → `test_many_cut_paragraphs_scale_linearly`,
`test_large_document_with_tables_pictures_and_joins` → `..._and_cut_paragraphs`,
`test_single_line_at_the_page_bottom_is_joined_…` → `..._is_not_joined_either`). Skipped (73): như 12D5 (pipeline OCR
đầy đủ không bật, model engine chưa cài trong thư mục app, bảng mã thật không có cache — chạy ở §2, Docker thật chưa
bật — chạy ở §3).

## 2. Với bảng mã o200k_base thật

| Bộ | Kết quả |
|---|---|
| `tests/test_token_utils_offline.py` (`CB5400_TIKTOKEN_CACHE_DIR`) | **17 passed** (như 12D5) |
| `tests/test_chunking.py tests/test_utils.py tests/test_embedding.py tests/test_context_endpoint_characterization.py tests/test_context_length_no_retry.py` (`TIKTOKEN_CACHE_DIR`) | **110 passed** (gồm 3 test `test_chunking` bỏ chọn ở §1; như 12D5) |

## 3. Công cụ offline, review 12D2 / 12D4

| Bộ | Kết quả |
|---|---|
| `tests/test_offline_package.py tests/review_phase12d4 tests/review_phase12d2 tests/test_phase12d7_build_lock.py` (sau E1-04) | **409 passed** (397 trước E1-04 + 12 test khóa), 0 failed, 0 xfail, 0 xpass |
| Trước 12D7 (12D5) | 395 passed (+2 test `docling_tsv_patch` của E0-07 = 397) |
| Mã cũ, `fcntl` bị chặn | `ModuleNotFoundError` (cơ chế lỗi Windows); tiến trình bị từ chối xóa trắng PID của người giữ |
| `CB5400_REAL_DOCKER=1 tests/test_offline_real_docker.py tests/test_offline_manual_fallback_real_docker.py` (Docker 29.10.0, containerd store; dùng khóa `update_lock` mới) | **3 passed** (288 s); không còn container / volume; danh sách image trước = sau; không kéo image |

## 4. Test mới của 12D7

| File | Số test | Kết quả |
|---|---|---|
| `tests/test_ocr_tesseract_tsv_text.py` (E0-07) | 74 | 74 passed |
| `tests/test_phase12d7_standard_diff.py` (§9) | 3 | 3 passed |
| `tests/test_phase12d7_standard_parity.py` (§9, stage OCR thật) | 1 | 1 passed |
| `tests/test_phase12d7_numeric_preservation.py` (E1-03) | 11 | 11 passed |
| `tests/test_phase12d7_orientation.py` (E1-05) | 18 | 18 passed |
| `tests/test_phase12d7_build_lock.py` (E1-04) | 12 | 12 passed |
| `tests/test_phase12d7_powershell.py` (E0-05) | 6 | 6 passed |
| `tests/test_offline_package.py` (E0-07: inventory, NOT_READY) | 2 | đạt |
| `tests/test_ocr_legal_normalizer.py` (E1-09: test mới / viết lại) | — | đạt |

ĐỎ đã ghi nhận: 15 test `test_red_*` + Tesseract thật + stage OCR thật cho thấy lỗi E0-07 trên hàm upstream; 5/6 test
PowerShell thất bại trên script cũ; bản cổng CRLF không khởi động; mã khóa cũ không chạy khi thiếu `fcntl`.

## 5. Chất lượng Legal, OCR

| Kiểm | Kết quả |
|---|---|
| Benchmark 92 fixture (`scripts/ocr/phase12_benchmark.py`) chạy lại trên HEAD | tổng hợp Standard và Legal **giống hệt** `docs/review/phase12d7/benchmark_legal_1_3_0.json` (trừ thời gian chạy) |
| Legal 1.3.0 so với 1.2.0 | 0 xóa / nối sai / chèn / sửa / mất placeholder ở cả hai; phép nối 6/8 → 0/8; mọi chỉ số khác giống hệt; không mất nội dung mới ([PHASE12D7_LEGAL_SAFETY_REPORT.md](PHASE12D7_LEGAL_SAFETY_REPORT.md)) |
| Standard expected-diff (stage OCR thật, trang tổng hợp) | 3 hunk, tất cả `expected parser fix` có TSV; 6/11 vùng giống từng byte; 0 hồi quy (`phase12d7/standard_diff_synthetic/`) |
| RapidOCR / EasyOCR | mã không đổi; bản vá chỉ áp cho lớp Tesseract (`test_the_patch_is_applied_by_every_tesseract_engine_and_no_other`) |
| Pipeline OCR thật trên scan thật (Layout Heron, TableFormer, Agri) | **KHÔNG chạy** (model không có ở Cloud) — W-12D7-02, W-12D7-03 |

## 6. Frontend (`frontend/`)

Thay đổi duy nhất: 2 chuỗi mô tả Legal (vi / en) ở `02d2907`.

| Lệnh | Kết quả |
|---|---|
| `npm run test -- --run` | 64 file, **438 / 438** (như 12D5) |
| `npx tsc --noEmit` | sạch |
| `npm run lint` | 0 lỗi, 7 cảnh báo cũ trong file không đổi (như 12D5) |

## 7. Lint và kiểu

| Lệnh | Kết quả |
|---|---|
| `ruff check .` | 2 lỗi — đều có từ 12D5 / baseline, trong file 12D7 không đổi (`tests/test_auth.py` I001, `tests/test_url_ingestion_switch.py` F811) |
| `python -m mypy .` | **81 lỗi** (12D5: 81), **không lỗi mới**. Lượt đầu 101: 20 lỗi trong file mới của 12D7 (gán vào method của lớp Docling, `load_page`, `Optional`) ⇒ sửa không đổi hành vi (`c4ed2b3`), 96 test liên quan chạy lại đạt |
| `mypy --platform win32 scripts/offline/offline_package.py` | phần mới sạch; lỗi `geteuid` chỉ ở các hàm máy chủ Ubuntu (có từ trước), không thuộc đường build |
| `offline_package.py` | parse được với cú pháp Python 3.8 |
| `ruff format` | file mới của 12D7 đã format; `offline_package.py` không format lại toàn file (đã không format từ trước, tránh diff lớn) |

## 8. Kết luận

```
PHASE 12D7: COMPLETED
E0-07 TSV PRESERVATION: VERIFIED
E1-04 CROSS-PLATFORM BUILD LOCK: LOCAL VERIFICATION REQUIRED
E1-09 UNSAFE LEGAL JOIN: FIXED
E1-03 NUMERIC PRESERVATION: PARTIAL
E1-05 ORIENTATION: NEEDS LOCAL EVIDENCE
STANDARD EXPECTED-DIFF PARITY: PARTIAL
LEGAL CONTENT PRESERVATION: PASS ON SYNTHETIC
OFFLINE PACKAGE: NOT VERIFIED ON WINDOWS
READY FOR INDEPENDENT REVIEW: YES
READY FOR WINDOWS RETEST: YES
READY FOR RELEASE: NO
READY FOR PRODUCTION: NO
PRODUCTION UNCHANGED
```

## 9. Không chạy được ở Cloud

Windows, PowerShell 5.1 / 7 (tải PowerShell 7 cho Linux bị cơ chế phê duyệt chặn — không tìm cách khác), Docker
Desktop, build image ứng dụng thật, pipeline OCR thật trên 22 PDF, model Agri, SurrealDB thật, trình duyệt thật — xem
[PHASE12D7_LOCAL_ACCEPTANCE_CHECKLIST.md](PHASE12D7_LOCAL_ACCEPTANCE_CHECKLIST.md).
