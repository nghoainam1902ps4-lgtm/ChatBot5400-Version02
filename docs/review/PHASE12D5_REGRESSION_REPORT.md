# Phase 12D5 — Báo cáo hồi quy

Môi trường Cloud: Linux, Python 3.12 (`.venv`), Tesseract 5.3.4 + `vie`, Docker 29.10.0 (containerd image store) +
Compose 5.7.1, Node (frontend). Mạng ra ngoài bị proxy chặn (trừ registry gói): tiktoken **không tải được** bảng mã
— vì vậy có hai lượt: không cache (giống baseline) và với file `o200k_base` thật đã kiểm SHA-256.

Baseline so sánh: `bc7236e` (= `8d0c438` + test 12D4 nhập nguyên trạng), cùng môi trường, log
`baseline_full.log` (14 failed / 2423 passed / 65 skipped).

## 1. Backend — toàn bộ `tests/` (không cache tiktoken)

Lệnh: `pytest tests/ -q -p no:cacheprovider -rfEsxX --timeout=900` với 3 test `test_chunking` cần tải bảng mã được
bỏ chọn (`--deselect`: ở môi trường không có bảng mã chúng lặp chờ tải theo hành vi online v1.2.0; với bảng mã thật
chúng đạt — §2). Commit `6edd7b6` (mã cuối cùng; commit sau chỉ thêm tài liệu).

| | Baseline `bc7236e` | **Phase 12D5** |
|---|---|---|
| passed | 2423 | **2917** |
| failed | 14 | **10** |
| skipped | 65 | 73 |
| deselected | 0 | 3 |
| xfailed / xpassed | 42 / 0 (review 12D4) | **0 / 0** (toàn bộ bộ test) |
| thời gian | 13 phút 26 | 15 phút 58 |

**Không có thất bại mới** (so theo tên). 10 thất bại còn lại có từ trước (baseline; theo 12D3 / 12D4 cũng có ở
v1.2.0), không liên quan 12D5: `tests/test_models_api.py::TestModelsProviderAvailability` (9 test — mock
`env_side_effect` nhận 1 tham số, mã gọi với 2: `TypeError`) và
`tests/test_domain.py::TestContentSettings::test_content_settings_defaults` (mặc định `docling`, test mong `auto`).
So với baseline: 3 test `test_chunking`
được bỏ chọn ở lượt này và đạt với bảng mã thật; `test_ocr_engine_manager.py::TestLifecycle::test_assert_ready_raises_value_error`
thất bại ở lượt baseline chỉ vì `easyocr` được cài vào môi trường SAU lượt đó — đạt ở cả hai commit khi chạy lại.

Skipped (73): pipeline OCR đầy đủ không bật (`test_ocr_integration.py` 39, `test_ocr_auto_full_page_pipeline.py` 16),
model engine chưa cài trong thư mục model của app (7), bảng mã thật không có cache (6, chạy ở §2), Docker thật chưa
bật (3, chạy ở §3), `test_ocr_quality_prep.py` (1), `test_ocr_custom_models.py` cần traineddata thật (1). Tăng 8 so với
baseline = 9 test opt-in mới (6 bảng mã, 3 Docker) − 1 (R2-21: test Tesseract trực tiếp giờ chạy).

## 2. Với bảng mã o200k_base thật (cache SHA-256 `446a9538…`)

| Bộ | Kết quả |
|---|---|
| `tests/test_token_utils_offline.py` (`CB5400_TIKTOKEN_CACHE_DIR`) | 17 passed (6 test bảng mã thật chạy, không skip) |
| `tests/test_chunking.py tests/test_utils.py tests/test_embedding.py tests/test_context_endpoint_characterization.py tests/test_context_length_no_retry.py` (`TIKTOKEN_CACHE_DIR`) | 110 passed (gồm 3 test `test_chunking` cần bảng mã) |
| Script dò token của `health` (chạy trực tiếp) | `{'ok': True, 'tokens': 522}`; thư mục rỗng ⇒ thất bại rõ ràng; `n_vocab` 200 019 |

## 3. Công cụ offline, review 12D2 / 12D4

| Bộ | Kết quả |
|---|---|
| `tests/test_offline_package.py tests/review_phase12d4 tests/review_phase12d2` | **395 passed**, 0 failed, 0 xfail, 0 xpass |
| trước 12D5 (12D4 trên `8d0c438`) | 129 passed, 42 xfailed (review); 32 test evidence ĐẠT khi lỗi còn |
| sau 12D5 | mọi xfail strict của 12D4 đã gỡ (42); 32 test evidence đảo thành test hồi quy (`# was:`); test `control` khẳng định hành vi lỗi đã đảo |
| `CB5400_REAL_DOCKER=1 tests/test_offline_real_docker.py tests/test_offline_manual_fallback_real_docker.py` | **3 passed** (279 s); dọn sạch container / image / volume |

## 4. Chất lượng Legal, oracle, OCR

| Kiểm | Kết quả |
|---|---|
| Benchmark 92 fixture (`scripts/ocr/phase12_benchmark.py`) chạy lại trên HEAD | tổng hợp Standard và Legal **giống hệt** `docs/review/phase12d5/benchmark_after.json` |
| Đột biến oracle (`tests/test_phase12d5_oracle.py`) | 10 / 10 lớp, phát hiện 100 % |
| Benchmark ĐỎ trên `8d0c438` | 74 cặp test normalizer thất bại (`red_8d0c438_normalizer_tests.txt`) |
| R2-21: lượt OCR toàn bộ theo thứ tự thu thập | trước: 65 skipped gồm `test_ocr_phase12_scripts.py:162`; sau: 64 skipped, test đó đạt |
| Pipeline OCR thật (Layout Heron, TableFormer, EasyOCR / RapidOCR / Agri trên scan thật) | **KHÔNG chạy** (model không có ở Cloud) — không tuyên bố nghiệm thu; W-PIPE, W-RC (LOCAL) |

## 5. Frontend (`frontend/`)

| Lệnh | Kết quả |
|---|---|
| `npm run test -- --run` | 64 file, **438 / 438** |
| `npx tsc --noEmit` | sạch |
| `npm run lint` | 0 lỗi, 7 cảnh báo cũ trong file không đổi |

Frontend không đổi từ `3526e44` tới HEAD (`git diff --stat 3526e44 HEAD -- frontend/` rỗng).

## 6. Lint và kiểu

| Lệnh | Kết quả |
|---|---|
| `ruff check .` | 2 lỗi — đều có ở baseline, trong file 12D5 không đổi (`tests/test_auth.py` I001, `tests/test_url_ingestion_switch.py` F811) |
| `python -m mypy .` | 81 lỗi (baseline 82), **không lỗi mới**; file công cụ / oracle / normalizer / token_utils sạch |
| `offline_package.py` | parse được với Python 3.8 |

## 7. Còn lại / không chạy được ở Cloud

PowerShell (5.1 / 7), Windows Docker Desktop, image ứng dụng thật, SurrealDB thật, script vận hành và boot guard của
máy chủ, Docker của Ubuntu production (image store cổ điển), trình duyệt thật, mạng bị chặn thật trên máy chủ, pipeline
OCR thật trên scan thật — `PHASE12D5_LOCAL_ACCEPTANCE_CHECKLIST.md`.
