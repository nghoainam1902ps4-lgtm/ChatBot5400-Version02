# Phase 12D2 — Chất lượng test và các khoảng trống

Đánh giá bộ test của Phase 12 tại commit `2ef0074`. Finding liên quan: T-01, T-02, T-03 trong
[PHASE12D2_FINDINGS.json](PHASE12D2_FINDINGS.json). Kết luận: **TEST QUALITY: PARTIAL**.

## 1. Đối chiếu các con số đã báo cáo

Số test thu thập được (đếm lại trong phiên review, đã cài extra `docling`: Docling 2.129.0, Docling Core 2.96.0, Content Core 2.0.7):

| Hạng mục | Báo cáo của Opus | Đếm lại | Nhận xét |
|---|---|---|---|
| Tổng backend tại HEAD | 2122 + 13 + 65 = 2200 | 2200 thu thập được | Khớp |
| Tổng backend tại v1.2.0 | 1789 + 13 + 64 = 1866 | 1866 thu thập được | Khớp |
| Test OCR có sẵn | 633 | 697 file `test_ocr_*` tại v1.2.0 | Con số 633 không tái lập được theo cách đếm file; chênh lệch có thể do SKIP |
| Test OCR mới | 303 | 304 (269 normalizer + 28 pipeline + 7 script) | Lệch 1 |
| Test offline | 30 | 30 | Khớp về số lượng; chạy lại: **29 PASS + 1 SKIP** (`test_signature_valid_and_invalid`: môi trường review không có `ssh-keygen`) |
| Frontend | 430/430 | **430/430 PASS**, 63 file, `tsc --noEmit` sạch | Đã chạy lại trong phiên review |

Kết quả chạy lại backend theo từng file và so sánh lỗi theo tên: xem §6.

## 2. T-03 — Số lượng test không phản ánh độ phủ

`tests/test_ocr_legal_normalizer.py` có 10 test tham số hóa trên cả 24 fixture (240 ca). Sáu test trong đó chỉ khẳng định được
điều gì khi fixture có khóa dữ liệu tương ứng; nếu không có, vòng lặp rỗng hoặc `return` sớm và ca đó luôn PASS:

| Test | Khóa fixture cần có | Fixture có khóa | Ca rỗng |
|---|---|---|---|
| `test_protected_fields_exact` | `protected` | 8/24 | 16 |
| `test_markers_displayed_as_in_original` | `markers` | 7/24 | 17 |
| `test_artifact_lines_absent_and_kept_lines_present` | `absent_lines`, `present_lines` | 12/24 | 12 |
| `test_joins_and_non_joins` | `must_join`, `must_not_join`, `forbidden` | 7/24 | 17 |
| `test_placeholders_and_warnings` | `expect_placeholders`, `expect_warnings` | 7/24 | 17 |
| `test_tables_identical` | `table_identical` | 2/24 | 22 |
| **Cộng** | | | **101 / 144** |

Kích thước fixture: 11 fixture một trang, 8 fixture hai trang, 4 fixture ba trang, 1 fixture bốn trang; mỗi fixture có 1–15 phần
tử. `must_join` chỉ có ở 3 fixture. Các ngưỡng của normalizer (≥ 3 trang, ≥ 50% số trang, offset trùng trên 2 trang) hầu như chỉ
được thử ở đúng giá trị biên mà implementation đã chọn.

Cách đếm (chạy lại được):

```bash
uv run python -c "import sys; sys.path.insert(0,'tests'); import legal_harness as H; FX=H.load_fixtures().FIXTURES; print({k: sum(1 for f in FX if f.get(k)) for k in ['protected','markers','must_join','table_identical']})"
```

## 3. T-01 — Oracle "0 từ bị mất" là vòng tròn

`test_no_valid_content_lost` và `scripts/ocr/phase12_benchmark.py` tính số từ mất bằng cách so bản Standard với
`bản Legal + toàn bộ text mà normalizer đã chuyển sang furniture`. Mọi thứ normalizer xóa đều được cộng trở lại trước khi so, nên
xóa nhầm **không bao giờ** được tính là mất. Con số "0 words lost" và "protected fields 24/24" trong PR được tạo theo cách này.

Bằng chứng: `tests/review_phase12d2/test_legal_normalizer_counterexamples.py::test_f01_f02_existing_oracle_cannot_see_these_deletions`
(PASS) cho thấy trên hai phản ví dụ, oracle hiện có trả 0 trong khi từ "triệu" và "2024" đã biến mất khỏi nội dung.

Cả 24 fixture đều có trường `ground_truth` nhưng phép đo mất từ không dùng nó.

## 4. T-02 và các oracle yếu khác

| Vị trí | Vấn đề |
|---|---|
| `tests/test_offline_package.py::_assert_safe_calls` (495-506) | `A and B or C`: mọi lệnh Compose có `--pull` đều qua, kể cả `down`. Đã chứng minh bằng `test_t02_*` |
| Docker giả (`FAKE_DOCKER`) | `compose config` được mô phỏng bằng regex trên tên file (`"image-override" in f`, `"maintenance" in f`): test không thể sai khi cú pháp override sai, khi Compose **nối** danh sách `ports` thay vì thay thế, hay khi `pull_policy` không có hiệu lực |
| Docker giả | `load` đọc JSON `{tag, id}`; ID luôn bằng nhau trước/sau: không thể phát hiện F-20, F-25 |
| Docker giả | `exec … import_rapidocr_weights` luôn in `{}` mã 0: nhánh lỗi không được thử (F-22) |
| Fixture `inventory` | `app_version: "1.3.0"` trong khi `VERSION` thật là `1.2.0` (F-27) |
| `test_update_apply_full_flow` | Chú thích "and upgrade again" nhưng không chạy cập nhật lần hai (F-08 nằm đúng ở đó) |
| `test_wrapper_scripts_only_delegate` | Chỉ tìm chuỗi `exec python3`; không chạy wrapper; `build-package.sh/.ps1` không nằm trong danh sách (F-04) |
| `tests/test_ocr_legal_pipeline.py` | Định tuyến và graph dùng converter giả/monkeypatch: đúng cho logic cổng và định tuyến, không chứng minh gì về Docling thật |
| `markdown-renderer.test.tsx` | Kiểm tra không có `<ol>/<ul>`; không kiểm tra định dạng phân cấp của trang Source (F-16) |

## 5. Đường mã không có test

| Đường mã | Finding |
|---|---|
| `sync_source` (60 dòng, có `git merge`/`checkout`) | F-05 — không có test nào |
| `build-package.sh`, `build-package.ps1` (đối số thật) | F-04 |
| `cmd_finish` / `cmd_rollback` khi ứng dụng không khỏe | F-09 |
| Cập nhật lần hai sau rollback/thất bại | F-08 |
| Journal hỏng | F-13 |
| `rollback legal-off` không có `--no-maintenance` | F-23 |
| Gói version khác khi `awaiting_approval` | F-24 |
| Trôi cấu hình sau `finish` | F-11 |
| `save_source` không lưu metadata chuẩn hóa | F-07 |
| Nhiều phép ghép / tài liệu lớn có ghép | F-10 (test hiệu năng hiện có không có phép ghép nào) |
| Footnote/footer nhãn TEXT, điểm `a.`/`a/`, dòng lặp là nội dung, số không phải số trang, ảnh 5–15% | F-01, F-02, F-03, F-06 |
| Trang xoay, khổ trang khác nhau, provenance sai/thiếu một phần, item nhiều provenance, bảng trong ảnh | chưa có fixture |
| Pipeline thật: Heron, TableFormer, RapidOCR, Tesseract, EasyOCR, Agri | chưa chạy (Windows Local) |
| PowerShell | chưa chạy ở đâu cả |

## 6. Chạy lại backend và so sánh lỗi theo tên

Cách chạy trong phiên review: mỗi file test một tiến trình, giới hạn 900 giây mỗi file, tại HEAD (`2ef0074`) và tại `v1.2.0`
(worktree riêng, cùng môi trường ảo).

| | HEAD `2ef0074` | `v1.2.0` |
|---|---|---|
| File test đã chạy | 85 | 81 |
| PASS | 2089 | 1757 |
| FAIL | 11 | 11 |
| SKIP | 66 | 64 |
| Hết giờ (không tính vào ba dòng trên) | `tests/test_chunking.py` (34 test) | `tests/test_chunking.py` (34 test) |
| Tổng đối chiếu | 2089 + 11 + 66 + 34 = 2200 | 1757 + 11 + 64 + 34 = 1866 |

Bốn file test mới của Phase 12 tại HEAD: `test_ocr_legal_normalizer.py` 269 PASS · `test_ocr_legal_pipeline.py` 28 PASS ·
`test_ocr_phase12_scripts.py` 6 PASS + 1 SKIP (không có Tesseract) · `test_offline_package.py` 29 PASS + 1 SKIP (không có
`ssh-keygen`).

Hệ quả: trong phiên review, **đường kiểm tra chữ ký `ssh-keygen -Y verify` không được thực thi**; phần này chỉ được xác minh bằng
đọc mã. Cần chạy lại trên máy có OpenSSH (checklist W-PIPE).

**Tập lỗi tại HEAD và tại v1.2.0 trùng nhau hoàn toàn theo tên** (không có lỗi nào chỉ xuất hiện ở một bên):

| Test | Nguyên nhân (đã đọc thông báo lỗi) | Liên quan Phase 12? |
|---|---|---|
| `test_domain.py::TestContentSettings::test_content_settings_defaults` | Test mong `'auto'`, mặc định hiện là `'docling'` | Không (có từ trước) |
| `test_models_api.py::TestModelsProviderAvailability::` 9 test (`test_blank_anthropic_compatible_env_vars_are_unavailable`, `test_generic_env_var_enables_all_modes`, `test_individual_mode_embedding_only`, `…_llm_only`, `…_stt_only`, `…_tts_only`, `test_mixed_config_generic_and_mode_specific`, `test_mode_specific_env_vars_llm_embedding`, `test_no_env_vars_set`) | Lỗi có từ trước | Không |
| `test_ocr_engine_manager.py::TestLifecycle::test_assert_ready_raises_value_error` | Môi trường review có Docling nhưng không có EasyOCR ⇒ thông báo lỗi khác mẫu test mong đợi | Không (đặc thù môi trường; giống nhau ở baseline) |
| `tests/test_chunking.py` (hết giờ 900 s) | `tiktoken.get_encoding("o200k_base")` gọi `requests.get` **không có timeout** tới host tải bảng mã; proxy Cloud chặn host này nên lời gọi treo (đã xác nhận bằng stack của faulthandler: `tiktoken/load.py:17 read_file`) | Không |

So với báo cáo của Opus (2122 PASS / 13 FAIL / 65 SKIP):

- 10 lỗi "đã biết" (1 + 9 ở hai dòng đầu) **khớp theo tên** ở cả hai phía. Đã xác minh.
- 3 lỗi `test_chunking` do tiktoken: trong môi trường review chúng **treo** chứ không lỗi nhanh, nên không tái lập được dưới dạng
  FAIL; nguyên nhân (host tải bảng mã bị chặn) được xác nhận và giống nhau ở baseline. File `test_chunking.py` không thay đổi
  giữa v1.2.0 và HEAD.
- Chênh lệch còn lại (thêm 1 FAIL do thiếu EasyOCR, 1 SKIP) là khác biệt môi trường, xuất hiện giống hệt ở baseline.

Ảnh hưởng tới máy chủ offline của ba test tiktoken: image nướng sẵn bảng mã `o200k_base` vào `/app/tiktoken-cache` và đặt
`TIKTOKEN_CACHE_DIR`, nên bình thường không cần mạng. Rủi ro còn lại (có từ trước, không do Phase 12): nếu file cache thiếu hoặc
hỏng trên máy chủ mà tường lửa DROP gói tin, `tiktoken` sẽ **treo** thay vì ném lỗi, và nhánh fallback đếm từ của `token_count`
không được kích hoạt. Kiểm tra bằng mục W-OFF-09 của checklist Windows.

## 7. Test phản ví dụ do review thêm

`tests/review_phase12d2/` (chỉ trên nhánh `review/phase12-fable-audit`):

| File | PASS | XFAIL (tái hiện finding) |
|---|---|---|
| `test_legal_normalizer_counterexamples.py` | 10 | 9 (F-01 ×2, F-02 ×2, F-03 ×4, F-06 ×1) |
| `test_offline_counterexamples.py` | 4 | 9 (F-04, F-05, F-08, F-09, F-12 ×2, F-13, F-14, T-02) |

Mỗi test `xfail(strict=True)` nêu hành vi **mong đợi**; đã kiểm tra bằng `--runxfail` rằng từng test thất bại đúng vì lý do ghi
trong finding (không phải do lỗi dựng dữ liệu). Các test PASS ghi lại những tính chất review đã xác minh: tính xác định,
idempotent, không sửa tài liệu gốc, an toàn luồng, giá trị trong đoạn văn không bị đổi, mọi lệnh `compose up` đúng dạng an toàn.

Chạy:

```bash
uv run pytest tests/review_phase12d2 -q -rxX
```

## 8. Test cần bổ sung ở Phase 12D3 (theo thứ tự ưu tiên)

1. Oracle bảo toàn nội dung dựa trên `ground_truth` (T-01).
2. Fixture phản ví dụ F-01, F-02, F-03, F-06 chuyển thành fixture chính thức với `present_lines` / `must_not_join`.
3. `sync_source`: 4 kịch bản; `build-package.sh --no-build` với docker giả.
4. Máy trạng thái: lần thử thứ hai, `finish`/`rollback` khi health lỗi, journal hỏng, gói khác khi chờ duyệt, drift.
5. Property test (Hypothesis nếu được phép thêm phụ thuộc dev, nếu không thì sinh ngẫu nhiên có seed): với tài liệu sinh ngẫu
   nhiên, mọi từ của item **không** thuộc dải trên/dưới phải còn trong đầu ra; số item đầu ra ≥ số item thân − số phép ghép.
6. Hiệu năng tương đối: thời gian 500 trang có ghép ≤ 2,5 × thời gian 250 trang.
7. Docker thật trong CI (job tùy chọn) với image nhỏ: `save`/`load`/so ID; Compose merge của override.
