# Phase 12D9 — An toàn khi OCR lỗi (E2-04) và các finding OCR của 12E2

Trạng thái máy đọc được: [PHASE12D9_E2_FINDING_STATUS.json](PHASE12D9_E2_FINDING_STATUS.json). Quyết định:
[D-45](../ocr/DECISIONS.md) (E2-04), [D-47](../ocr/DECISIONS.md) (chẩn đoán metadata-only, không có fallback chữ ngắn),
[D-40 — cập nhật 12D9](../ocr/DECISIONS.md) (E1-05).

Nguồn bằng chứng Windows: báo cáo 12E2 và 12E2 Follow-up do chủ dự án tóm tắt trong yêu cầu 12D9. Cloud không truy cập
đường dẫn Windows, không có tài liệu thật, không có model Agri. Báo cáo đã làm sạch `PHASE12E2_FOLLOWUP_SANITIZED.md`
không có trong repo hay nhánh nào ⇒ các finding chỉ được tái hiện bằng fixture (E1-01, E1-02, E1-06, E1-08) **không
được suy diễn** ở đây.

## 0. Bốn loại vấn đề — không gộp

| Finding | Loại | Kết luận 12D9 |
|---|---|---|
| **E2-04** | lỗi **thực thi** OCR: tiến trình nhận dạng Tesseract thất bại | FIXED IN CODE (Cloud, tiêm lỗi); Windows chạy lại |
| **E2-01** | giới hạn **phân đoạn / nhận dạng**: PSM 3 đọc rỗng crop có token ngắn | NEEDS LOCAL EVIDENCE; không đổi PSM, không fallback |
| **E2-02** | chất lượng **crop / layout / nhận dạng** của 11 cụm nhiễu | NEEDS LOCAL EVIDENCE; chỉ thêm chẩn đoán |
| **E1-05** | **toàn vẹn khi chạy** của cổng hướng xoay | lỗi build cổng: FIXED; chất lượng OCR 11 vùng: chưa xác minh (⇒ E2-02) |

## 1. E2-04 — lỗi thực thi OCR (P1)

### 1.1 Bằng chứng Windows (12E2 Follow-up)

* OSD lỗi **một mình** không làm mất vùng khi nhận dạng thành công (Docling dùng ngôn ngữ đã cấu hình).
* Tiến trình **nhận dạng** lỗi ⇒ Docling 2.129.0 bỏ cả vùng (`continue`), kết quả vẫn `SUCCESS`, `errors = 0`; Source
  `completed`, `success = true`. Mất: Best 13 / 49 token, Agri v2 63 / 100, D22 445 / 1 220.
* D22 có `embed = false`: không có bằng chứng embedding được tạo từ nội dung thiếu (cũng không có bằng chứng ngược lại).
* Thư mục dữ liệu là mount 9p từ Windows. **Nguyên nhân gốc chưa biết** vì upstream đưa stderr vào `DEVNULL`.
  12D9 **không** kết luận mount 9p là nguyên nhân.

### 1.2 Sửa (commit `691fac9`, khuôn bản vá có kiểm soát D-39)

| Yêu cầu của chủ dự án | Cách làm | Test |
|---|---|---|
| 1. không nhầm OSD với nhận dạng | hai đường riêng trong `TesseractOcrCliModel.__call__` (bản sao upstream, SHA-256 `98ecbc91…`); chỉ lỗi **nhận dạng** được thử lại / làm hỏng vùng | `test_osd_failure_alone_keeps_the_region_and_the_document` |
| 2. OSD lỗi mà nhận dạng đủ ⇒ không làm hỏng Source | OSD lỗi: log (stderr đã che), nhận dạng chạy với ngôn ngữ đã cấu hình — như upstream. Riêng chế độ auto-script (không cấu hình ngôn ngữ, ứng dụng không dùng) upstream bỏ vùng ⇒ nay thành lỗi vùng | `…_osd_failure_in_auto_script_mode_fails_the_region_instead_of_dropping_it` |
| 3. thử lại có giới hạn | tối đa **2 lần thử lại** (3 lần chạy), chờ 0,5 s rồi 1,5 s, **cùng** crop, lệnh, ngôn ngữ, file model; timeout 600 s mỗi lần | `…_transient_failure_is_retried_on_the_same_crop_and_model`, `…_crash_or_an_error_exit_is_retried`, `…_hung_tesseract_times_out_and_is_retried`, `test_recognize_region_retries_exactly_the_policy` |
| — không thử lại lỗi vĩnh viễn | thiếu chương trình, không được chạy, thiếu file model (`-l` / `--tessdata-dir`), không phân loại được | `test_a_missing_model_file_is_not_retried`, `test_failure_categories_and_what_is_retried` |
| 4. thử lại vẫn lỗi ⇒ không lưu như hoàn tất | `OcrRegionError` ⇒ Docling đánh dấu trang lỗi ⇒ `convert_file` từ chối **mọi** kết quả khác SUCCESS hoặc có ErrorItem (`IncompleteConversionError`, ValueError ⇒ job dừng, không tự lặp) | `…_region_that_always_fails_rejects_the_document`, `…_middle_page_failure_is_named_and_refused`, `…_every_page_failing_is_refused_not_retried_as_a_job`, `…_partial_result_with_data_is_refused_before_storage` |
| 5. không embedding nội dung lỗi | lỗi xảy ra trước khi lưu; `embed_source` không được xếp hàng | `…_new_source_whose_region_fails_gets_no_content_and_no_embedding` |
| 6. không ghi đè Source cũ hợp lệ | xử lý lại thất bại: `full_text` và các bản ghi `source_embedding` cũ giữ nguyên, không job embedding mới; thông báo nói rõ nội dung cũ được giữ | `…_failed_reprocess_keeps_the_previous_content_and_embeddings` |
| 7. không đổi engine / model Agri | không có đường đổi engine, không dùng model khác khi thử lại | `…_transient_failure_is_retried_on_the_same_crop_and_model` (so lệnh từng lần) |
| 8. stderr có giới hạn, không lộ | `stderr=PIPE`, chỉ đọc 4 096 byte cuối để phân loại; log / thông báo chỉ có trang, vùng, engine, category, mã thoát, số lần thử; OSD log `[stderr withheld: N bytes, category]` | `test_logs_and_the_source_error_carry_no_stderr_and_no_document_text`, `test_only_the_tail_of_stderr_is_read` |
| 9. tiêm lỗi qua vòng đời Source / embedding thật | wrapper trước binary `tesseract` THẬT; pipeline Docling thật (chỉ layout là stub — không có trọng số ở Cloud); `convert_file`, đồ thị source, command `process_source`, `Source` và hàng đợi `embed_source` trên SurrealDB thật (engine nhúng, migration của ứng dụng) | toàn bộ file |

Thông báo cho người dùng (tiếng Việt, không chi tiết kỹ thuật thô): "Nhận dạng tài liệu chưa hoàn tất do một vùng OCR gặp
lỗi." / "Chuyển đổi tài liệu chưa hoàn tất do một trang không xử lý được." + "Tài liệu chưa được đưa vào kho tri thức."
hoặc "Nội dung cũ của tài liệu vẫn được giữ nguyên." + "Vui lòng thử lại." Phần chi tiết chỉ có trạng thái, trang,
vùng, engine, category, mã thoát, số lần thử.

**Thay đổi hành vi có chủ đích (D-45):** `PARTIAL_SUCCESS` của mọi engine (trước đây lưu kèm cảnh báo — xem
`conversion_outcome` của v1.2.0) nay bị từ chối. Đường API đồng bộ (`async_processing=false`): command lỗi ⇒ Source
mới bị xóa (mã có sẵn, đọc lại trong 12D9, không thêm test riêng).

### 1.3 Bằng chứng

* RED trên `4587eb7` (worktree, cùng `.venv`, 24 test lúc đó): **23 failed / 1 passed** —
  [red_4587eb7_ocr_failure_safety.txt](phase12d9/red_4587eb7_ocr_failure_safety.txt). Test đạt ở RED là control "OCR
  thành công mà không có chữ không phải lỗi". Control "upstream bỏ vùng lỗi và báo SUCCESS" cũng fail ở RED chỉ vì dùng
  `P.call_upstream()` (chỉ có trong bản vá); ở GREEN nó chạy **chính** vòng OCR upstream và chứng minh việc mất vùng
  lặng lẽ (SUCCESS, errors = 0, thiếu chữ của vùng).
* GREEN: 25 / 25 (test thứ 25 thêm sau RED: `ocr.cli status` nêu bản vá E2-04 — commit `ac34bb9`) (trong lượt hồi quy đầy đủ, [PHASE12D9_REGRESSION_REPORT.md](PHASE12D9_REGRESSION_REPORT.md)).
* Không đổi: Docling 2.129.0, docling-core 2.96.0, engine, Agri, Layout Heron, TableFormer, ngưỡng OSD.

### 1.4 Rủi ro còn lại

* Nếu lỗi trên Windows **kéo dài** (không tạm thời), tài liệu bị từ chối thay vì lưu thiếu — đúng yêu cầu, nhưng người
  dùng phải xử lý lại sau khi khắc phục môi trường. Category trong log 12D9 là dữ liệu để tìm nguyên nhân gốc.
* Model embedding không chạy ở Cloud (không có provider): kiểm tra là không job nào được xếp và bản ghi
  `source_embedding` cũ không đổi.

### 1.5 Cổng Windows (E2-G1 … E2-G6)

Chi tiết lệnh: [PHASE12D9_LOCAL_ACCEPTANCE_CHECKLIST.md](PHASE12D9_LOCAL_ACCEPTANCE_CHECKLIST.md) §3. Lỗi tạm thời có
kiểm soát dùng `scripts/ocr/phase12d9_tesseract_fault.sh` (chỉ stack thử; chỉ lệnh nhận dạng có thể bị làm lỗi; OSD,
`--version`, `--list-langs` đi thẳng tới binary thật; không ghi dữ liệu tài liệu).

## 2. E2-01 — token ngắn một mình trong crop

**Windows:** 15 crop ngắn; PSM 3 ⇒ 2 rỗng; padding không ổn định; PSM 6 và 7 đúng 15 / 15 với Best, Fast, Agri v1, Agri v2;
PSM 8 và 13 lỗi với Agri.

**Cloud (tổng hợp, kiểm công cụ — không phải bằng chứng Windows):** `phase12d9_crop_diagnose.py benchmark`, Tesseract 5
`vie` của container, 18 trường hợp (DejaVu Sans, 216 dpi) —
[e2_01_cloud_synthetic_benchmark.json](phase12d9/e2_01_cloud_synthetic_benchmark.json):

| Nhóm (số crop) | PSM 3 | PSM 6 | PSM 7 | Luật fallback thử nghiệm (PSM 7 khi PSM 3 rỗng + hình học một dòng) |
|---|---|---|---|---|
| token ngắn (11: chữ số đơn, `9.`, `4.`, `123.`, `a).`, `đ).`, `0004`, `05/2024`, `Điều`, `Khoản`) | 4 đúng, **7 rỗng** | 11 đúng | 11 đúng | 9 đúng, 2 rỗng |
| không có chữ (6: trống, nhiễu mép, con dấu, chữ ký, ảnh, đường kẻ bảng) | 6 rỗng đúng | 3 rỗng đúng, **3 chèn chữ giả** | 1 rỗng đúng, **5 chèn chữ giả** | 2 rỗng đúng, **4 chèn chữ giả** |
| nhiều dòng (1) | đúng | đúng | **nhận sai** | đúng |

Đo theo bốn kết cục (đúng / rỗng / nhận sai / chèn chữ giả), không chỉ đếm token.

**Quyết định (D-47):** không đổi PSM mặc định; **không cài** fallback, kể cả cờ `OCR_TESSERACT_SHORT_TEXT_FALLBACK`
tắt mặc định: luật hình học không phân biệt được crop không chữ (con dấu, chữ ký, ảnh, đường kẻ) với crop token ngắn — 4 / 6
crop không chữ bị chèn chữ. Không suy diễn số điều / ký tự, không LLM. Không phải điều kiện phát hành.

**Cần ở Windows (E2-G7):** `benchmark` với Best / Fast / Agri v1 / Agri v2 và `crops` trên các crop thật của 15 trường
hợp (chỉ số liệu); trước mọi đề xuất bật fallback phải có tỉ lệ chèn chữ giả trên crop không chữ thật.

## 3. E2-02 — 11 cụm OCR nhiễu

**Windows:** không cụm nào do xoay hoặc watermark (OSD 0°). Nguyên nhân có thể (chưa xác minh, không có ground truth):
crop bị cắt, chồng lấn layout, crop quá nhỏ, chữ nhỏ, nhiễu mép, khác biệt model OCR theo vùng, chồng lấn ảnh / dấu / chữ ký.

**12D9:** không đổi Layout Heron, TableFormer, ngưỡng OSD; không fine-tune Agri; không xóa theo confidence; không tự bỏ
nội dung vùng ảnh. Chỉ thêm chẩn đoán: `phase12d9_crop_diagnose.py crops <thư mục crop>` — kích thước, dpi, độ tương phản,
tỉ lệ mực, năng lượng biên, mực chạm mép, số từ và thống kê confidence theo PSM 3 / 6 / 7; **không chữ** trừ khi `--with-text` (file quyền chủ
sở hữu). Bằng chứng crop của chính lần chuyển đổi: thư mục `<tên>.evidence/` của `phase12d9_standard_export.py` (TSV thô
từng lần gọi + bbox). Trạng thái: **NEEDS LOCAL EVIDENCE**.

## 4. E1-05 — tách hai kết luận

* **Lỗi build cổng hướng xoay (toàn vẹn khi chạy): FIXED.** CRLF của image cũ được xác nhận và đã sửa (12D7:
  `.gitattributes`, bước chuẩn hóa + tự kiểm trong Dockerfile; 12D9: test chứng minh bước tự kiểm làm hỏng build được —
  D8-ORI-05; readiness / `status --json` ghi cổng **thực sự** chạy — D8-ORI-02).
* **Chất lượng OCR của 11 vùng: CHƯA XÁC MINH ĐẦY ĐỦ.** CRLF không phải nguyên nhân (OSD 0°) ⇒ chuyển sang E2-02.

## 5. Finding chỉ có fixture tổng hợp

E1-01, E1-02, E1-06, E1-08: Windows đã tái hiện bằng fixture tổng hợp; chưa nhận báo cáo đã làm sạch ⇒ **EVIDENCE
REQUIRED**, không suy diễn. E2-03 (hunk nhiều nguyên nhân) đã sửa trong cổng v2 — xem
[PHASE12D9_STANDARD_DIFF_REPORT.md](PHASE12D9_STANDARD_DIFF_REPORT.md).
