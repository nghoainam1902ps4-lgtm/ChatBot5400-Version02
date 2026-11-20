# Phase 12D13 — Báo cáo hồi quy

Môi trường: Windows 11 Pro (Local), Docker Desktop 4.91.0 / Engine 29.8.0. Test runner Linux chỉ dùng cho test
(không phát hành): image candidate 2cc824f (cùng `pyproject.toml` / `uv.lock` runtime với 18eeecb) + nhóm `dev`
theo `uv.lock` (pytest 9.0.3) + Tesseract 5.5.0 `eng` / `osd` / `vie` + DejaVu + `openssh-client`; CPython 3.12.16,
Docling 2.129.0, RapidOCR 3.9.2, torch 2.14.0+cpu. Repo được clone từ git bundle (lịch sử + tag) rồi chép working
tree lên, quyền file theo git (bind mount Windows hiện mọi file là 0777). Mạng: chỉ loopback tới SurrealDB **2.7.0**
server cô lập (RocksDB), `CB5400_D12_SURREAL_URL` đặt nên control server cũng chạy.

## 1. Full backend trên commit code cuối

Lệnh: `pytest <lô> -q -p no:cacheprovider -rfEsxX --tb=short --junitxml=…`, toàn bộ 125 file `tests/**/test_*.py`
chia 7 lô, mỗi lô một tiến trình (lý do ở mục 3). Kết quả cộng từ junit XML:

| Commit | Passed | Failed | Skipped | XFailed | XPassed | Error |
|---|---|---|---|---|---|---|
| `8b94a3f` (code D12-03 + RB-1 + RapidOCR) | **3582** | **10** | 67 | 2 | 0 | 0 |
| `f165399` (+ fixture snapshot, chỉ chú thích kiểu) | **3582** | **10** | 67 | 2 | 0 | 0 |

Hai lượt cho cùng kết quả (cùng 10 lỗi mốc). Các commit sau `f165399` chỉ thêm tài liệu `docs/review/PHASE12D13_*`. Evidence: `d13-evidence\regression-batches\`, `regression-batches-final\` (junit XML + console).

Theo bộ (trên `8b94a3f`): control D10 `test_phase12d10_review_controls` **16 / 16**; D11 bound gate **10 / 10**;
`test_phase12d12_review_controls` **22 passed + 2 xfailed** (D12-01, D12-02 giữ `xfail(strict)`; 4 control D12-03 và
2 control server đều đạt); `test_phase12d13_rb1_hardening` 31 / 31; `test_phase12d13_rapidocr_dictionary` 6 / 6;
`test_phase12d11_rb1` 8 / 8; `test_offline_package` 230 / 230 (gồm gói ký bằng ssh-keygen thật và
`test_version_rule_on_the_real_repository`); `test_phase12d9_standard_gate` 25 / 25; embedding transactions 10 / 10;
offline fingerprint 4 / 4.

D10-09 bổ sung: ma trận 8 trường hợp (`tests/fixtures/phase12f1/f0_case_matrix.py`) trên SurrealDB 2.7.0 server với
`scripts/offline/offline_package.py` cuối: **8 / 8** phát hiện (`vector_same_id`, `chunk_content`, `chunk_order`,
thêm / xoá bản ghi, vector insight, nội dung note, `full_text`). N0 trên Docker Desktop (D12-L1 / L3): fingerprint
không đổi khi chỉ LIVE query đổi.

## 2. Mười lỗi mốc — trùng theo tên và nguyên nhân

| Test | Nguyên nhân (giống 12D11 / 12D12) |
|---|---|
| `tests/test_domain.py::TestContentSettings::test_content_settings_defaults` | `AssertionError: assert 'docling' == 'auto'` (mặc định engine tài liệu là `docling` từ migration 28) |
| `tests/test_models_api.py::TestModelsProviderAvailability::` `test_blank_anthropic_compatible_env_vars_are_unavailable`, `test_generic_env_var_enables_all_modes`, `test_individual_mode_embedding_only`, `test_individual_mode_llm_only`, `test_individual_mode_stt_only`, `test_individual_mode_tts_only`, `test_mixed_config_generic_and_mode_specific`, `test_mode_specific_env_vars_llm_embedding`, `test_no_env_vars_set` | `TypeError: … env_side_effect() takes 1 positional argument but 2 were given` (mock) |

Không có lỗi nào khác. Không file nào trong hai test này nằm trong diff 12D13.

## 3. Lượt chạy một tiến trình bị abort (giữ làm bằng chứng)

Hai lượt `pytest tests` trong **một** tiến trình dừng bằng `Fatal Python error: Aborted` (mã 139) ở ~84 % và ~94 %,
cả hai lần trong `surrealdb/connections/async_embedded.py::__init__` (engine SurrealDB **nhúng** của SDK, tạo DB
trong fixture), với hàng chục thread pipeline Docling còn chờ từ các test OCR trước. Lượt 1 chạy cùng lúc ba lab
Docker; lượt 2 không có tải song song. Các test fail ngay trước abort (`test_sources_api`, `test_search_api`, …) **đạt
134 / 134 khi chạy riêng**. Kết luận: cạn tài nguyên native của tiến trình dài trên máy này, không phải lỗi mã; môi
trường review 12D12 (Linux, không có `vie`) chạy một tiến trình được. Lượt theo lô chạy **đúng cùng tập test**.
Evidence: `d13-evidence\regression-full-8b94a3f.txt`, `regression-full-8b94a3f-run2.txt`.

## 4. 67 ca skip (môi trường, không ca nào thuộc D10 / D12 / RB-1)

| Số | Lý do |
|---|---|
| 55 | pipeline OCR đầy đủ chưa bật (`OCR_FULL_PIPELINE=1`) |
| 7 | engine EasyOCR / Tesseract Best / Fast chưa "ready" trong runner (model chưa cài) |
| 2 | traineddata thật / Tesseract runtime |
| 3 | rehearsal Docker thật (`CB5400_REAL_DOCKER=1`) — phần tương ứng chạy thật ở D12-L1 / L3 |

## 5. Lint, type, frontend

- Ruff: các file Python đã đổi đạt `ruff check` và `ruff format --check` (trừ `scripts/offline/offline_package.py`
  vốn chưa format ở mốc — chỉ đổi 6 dòng, không format lại cả file).
- mypy `mypy .` cùng môi trường: mốc `26ff1c1` **107** lỗi / 26 file; cuối **107** lỗi, **0 lỗi mới** (số khác 81 của
  12D11 do phiên bản mypy / stub của runner; so sánh cùng môi trường).
- Frontend: `git diff 18eeecb HEAD -- frontend` rỗng ⇒ không chạy lại.

## 6. Cổng Local

Xem [checklist nghiệm thu Local](PHASE12D13_LOCAL_ACCEPTANCE_CHECKLIST.md): D12-L1 PASS, D12-L2 PASS, D12-L3 PASS
(Docker Desktop), D12-L4 PARTIAL, D12-L5 PARTIAL, RB-G11 PENDING.
