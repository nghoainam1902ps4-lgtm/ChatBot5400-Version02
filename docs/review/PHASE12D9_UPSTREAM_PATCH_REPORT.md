# Phase 12D9 — Báo cáo bản vá upstream có kiểm soát

Phạm vi: các hàm của Docling 2.129.0 / docling-core 2.96.0 mà ứng dụng thay khi chạy (không sửa site-packages, không
fork, không monkey-patch pandas, không đổi phiên bản, không đổi model). Quyết định: D-39 (khuôn bản vá), D-41 (gạch nối),
D-42 (footnote), D-45 (vùng OCR lỗi) trong [DECISIONS.md](../ocr/DECISIONS.md). Mã: `open_notebook/ocr/docling_patches.py`.

## 1. Đích vá và mã băm upstream đã kiểm

SHA-256 = `sha256(inspect.getsource(<hàm upstream>))`, cùng giá trị `compat.DOCLING_FINGERPRINTS` kiểm.

| Patch ID | Đích (module : hàm) | Phiên bản bắt buộc | SHA-256 upstream | Thay đổi duy nhất |
|---|---|---|---|---|
| `E0-07/tesseract-tsv-text/1` (12D7) | `docling.models.stages.ocr.tesseract_ocr_cli_model : TesseractOcrCliModel._run_tesseract` | docling 2.129.0 | `e0623aa9…de233c` | đọc TSV giữ chữ nguyên văn; **12D9 (E2-04):** `stderr=PIPE` (chỉ đọc 4 096 byte cuối để phân loại), `timeout` 600 s |
| `E2-04/tesseract-region-failure/1` | `… : TesseractOcrCliModel.__call__` | docling 2.129.0 | `98ecbc91…006482` | lỗi nhận dạng ⇒ thử lại có giới hạn rồi `OcrRegionError` thay vì `continue`; OSD lỗi ở chế độ auto-script ⇒ lỗi vùng thay vì bỏ vùng; log OSD che stderr |
| `D8-03/hyphen-preservation/1` | `docling.models.stages.page_assemble.page_assemble_model : PageAssembleModel.sanitize_text` | docling 2.129.0 | `7c6242f7…a41b03e` | nhánh gạch nối: không bỏ `-`; ghép liền chỉ khi hộp chữ cho thấy xuống dòng |
| `D8-03/hyphen-preservation/1` | `… : PageAssembleModel.__call__` | docling 2.129.0 | `b2052577…41cec37e` | truyền hình học các ô (`same_line_flags`) cho `sanitize_text`; ghi bằng chứng phần tử khi đang thu bằng chứng |
| `D8-03/hyphen-preservation/1` | `docling.models.stages.reading_order.readingorder_model : ReadingOrderModel._merge_elements` | docling 2.129.0 | `297d40a4…bc892da` | nối khối qua trang / cột giữ `-`, charspan đúng chỗ phần tiếp |
| `D8-02/attached-footnotes/1` | `docling_core.transforms.serializer.markdown : MarkdownTableSerializer.serialize` | docling-core 2.96.0 | `5eb2124b…1db` | gọi serializer upstream rồi **chỉ nối thêm** footnote gắn với bảng |
| `D8-02/attached-footnotes/1` | `… : MarkdownPictureSerializer.serialize` | docling-core 2.96.0 | `ec9a0039…b` | như trên cho ảnh |

## 2. Cơ chế bảo vệ (giống D-39)

* Đúng phiên bản phân phối (`importlib.metadata`) **và** SHA-256 của mã nguồn từng hàm; lệch bất kỳ điều kiện nào ⇒
  không vá gì (tất cả hoặc không gì) và báo lỗi rõ; chuyển đổi PDF / scan bị **từ chối** chứ không chạy khi chưa vá.
* Idempotent, có khóa (vá đồng thời chỉ một lần), dấu `__cb5400_patch__` / `__cb5400_upstream__` trên hàm đã vá; fingerprint
  compat theo mã nguồn upstream (không theo hàm đã vá).
* Test AST: mỗi hàm vá **bằng** hàm upstream trừ đúng các thay đổi đã ghi (`test_sanitize_text_is_upstream_except_the_hyphen_branch`,
  `test_page_assembly_is_upstream_except_the_geometry_it_passes`, `test_merge_elements_is_upstream_except_the_hard_hyphen_branch`,
  `test_footnote_serializers_call_upstream_and_only_append_notes`, `test_the_ocr_loop_is_upstream_except_the_two_e2_04_changes`).
* Nơi áp dụng: `docling_extract.build_converter` (mọi engine), đồ thị source trước đường Docling riêng của content-core,
  Legal normalizer, tiến trình worker mới trước lần chuyển đổi đầu. Hiển thị: `python -m open_notebook.ocr.cli status`
  (dòng trạng thái từng bản vá; `--json` mang `docling_text_preservation`, `docling_tsv_patch`, `orientation_gate`),
  readiness, inventory / readiness của gói offline (`docling_text_patch`).

## 3. RED / GREEN

| Bộ test | RED trên `4587eb7` (chưa vá) | GREEN (12D9) |
|---|---|---|
| `tests/test_phase12d9_text_preservation.py` | 44 failed + 11 errors / 8 passed (control) — [red_4587eb7_text_preservation.txt](phase12d9/red_4587eb7_text_preservation.txt) | 63 passed |
| `tests/test_phase12d9_ocr_failure_safety.py` | 23 failed / 1 passed (24 test lúc đó) — [red_4587eb7_ocr_failure_safety.txt](phase12d9/red_4587eb7_ocr_failure_safety.txt) | 25 passed |
| `tests/review_phase12d8/` (bộ audit 12D8, nhập nguyên trạng ở `85ada78`) | 71 xfail strict mang mã finding | xfail của finding đã sửa được gỡ, mỗi chỗ có chú thích `# was:` |

Số liệu GREEN cuối: [PHASE12D9_REGRESSION_REPORT.md](PHASE12D9_REGRESSION_REPORT.md).

## 4. Giới hạn đã ghi nhận (có test control)

* **Ô bảng TableFormer:** `TableCell.from_dict_format` ghép token bằng một khoảng trắng — `-` được giữ nhưng có thể thêm
  khoảng trắng (`TT- BNNPTNT`); không mất ký tự (`test_control_table_cell_tokens_keep_the_hyphen_upstream`).
* **Gạch nối mềm U+00AD, dấu nháy, bullet, ligature:** giữ quy tắc upstream (`test_other_upstream_text_rules_are_unchanged_and_recorded`).
* **Không có bằng chứng hình học** (thiếu hộp, gốc tọa độ lẫn lộn): giữ ranh giới ô bằng một khoảng trắng, không bao giờ
  suy diễn hai ô là một từ (`test_without_boxes_two_cells_are_never_assumed_to_be_one_word`).
* **Footnote gắn kèm chỉ trong Markdown:** đầu ra HTML vẫn như upstream (thiếu footnote); JSON vốn giữ mọi text item
  (`test_control_html_export_still_omits_attached_notes_and_json_keeps_them`). Ứng dụng lưu Markdown.
* Không thêm `-`, không sửa chính tả theo từ điển, không AI sửa chữ.
