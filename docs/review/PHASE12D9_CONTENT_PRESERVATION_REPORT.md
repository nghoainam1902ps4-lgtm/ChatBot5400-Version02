# Phase 12D9 — Bảo toàn nội dung văn bản (D8-03, D8-01, D8-02, E0-07)

Ba blocker mã của 12D8 ([PHASE12D8_RELEASE_BLOCKERS.md](PHASE12D8_RELEASE_BLOCKERS.md)) đều đã sửa trong mã và kiểm ở
Cloud bằng dữ liệu tổng hợp. Cả ba vẫn **LOCAL VERIFICATION REQUIRED**: chỉ máy Local có PDF / scan nghiệp vụ, model
Agri, Layout Heron / TableFormer chạy thật trên trang thật. Cloud không có và không được nhận tài liệu thật.

Kết luận: **LEGAL CONTENT PRESERVATION: PASS ON SYNTHETIC** — trên 92 fixture có ground truth khai báo, Legal 1.3.1 không
xóa, không nối sai, không chèn, không đổi đơn vị nào; thứ tự còn đảo ở 3 tài liệu là thứ tự đọc của chính Docling
(Standard y hệt, Legal không thêm cặp đảo nào).

## 1. D8-03 — gạch nối (P1) — commit `de55d4e`, D-41

**Lỗi:** Docling 2.129.0 bỏ `-` ở hai chỗ: `PageAssembleModel.sanitize_text` (ghép ô của một vùng: `05/2024/TT-` +
`BNNPTNT` → `05/2024/TTBNNPTNT`; ô Tesseract là từ nên cả giữa dòng: `VT- KHTC` → `VTKHTC`) và
`ReadingOrderModel._merge_elements` (nối khối qua trang / cột trước chữ thường). Có từ v1.2.0, mọi engine và lớp chữ PDF.

**Sửa:** không bao giờ bỏ `-`; hai phần chỉ ghép liền khi **hộp chữ của chính các ô** cho thấy xuống dòng; cùng dòng hoặc
không có bằng chứng ⇒ giữ ranh giới ô (một khoảng trắng). Legal 1.3.1 hiểu phép nối có giữ `-` và vẫn tách mọi phép nối
qua trang (D-38).

| Đường đi | Test (Cloud) |
|---|---|
| ghép ô trong một vùng (đúng / sai dòng, dấu trừ đầu ô, gạch có khoảng trắng hai bên) | `test_page_assembly_keeps_every_hyphen_and_the_printed_spacing` (+ control upstream) |
| Tesseract **thật** → Docling → `Source.full_text` (đầu-cuối) | `test_e2e_every_hyphen_of_the_raw_tsv_reaches_source_full_text` (+ control upstream mất) |
| lớp chữ PDF qua docling-parse (backend mặc định) | `test_pdf_text_layer_keeps_every_hyphen` |
| nối khối qua trang của Docling | `test_a_page_end_hyphen_is_kept_and_the_char_span_is_exact`, `test_legal_splits_the_patched_page_end_join_back_into_its_pages` |
| bộ audit 12D8 | `tests/review_phase12d8/test_tsv_patch_d8.py` (xfail D8-03 đã gỡ) |

Giới hạn (có test control): ô bảng TableFormer giữ `-` nhưng có thể thêm khoảng trắng; U+00AD / nháy / bullet / ligature
theo upstream. Xem [PHASE12D9_UPSTREAM_PATCH_REPORT.md](PHASE12D9_UPSTREAM_PATCH_REPORT.md) §4.

## 2. D8-01 — thứ tự đọc khi Legal tách phép nối của Docling (P2, blocker) — commit `de55d4e`, D-43

**Lỗi:** khi trang khác kích thước (scan tự cắt lề, phụ lục khổ ngang, PDF ghép) hoặc trang hai cột, Legal 1.3.0 đặt phần
tách ra sau tiêu đề / đoạn kế tiếp.

**Sửa (Legal 1.3.1):** phần sau đặt **ngay sau** phần đầu, chỉ vượt các item mà phép nối của Docling bỏ qua (header,
footer, bảng, ảnh, caption, footnote) **và** đứng trước nó trong thứ tự đọc Docling tự tính; không bao giờ vượt đoạn văn,
list item hay tiêu đề. Hộp của phần sau giải mã bằng chiều cao trang của phần đầu (quy ước của Docling). Không xác định
được ⇒ giữ phép nối + cảnh báo `upstream_merge_kept`. Không sắp lại tài liệu theo tọa độ.

Test: `tests/review_phase12d8/test_legal_d8.py::test_d8_01_mixed_page_heights_keep_the_reading_order`,
`::test_d8_01_two_columns_keep_the_reading_order`, `::test_d8_01_the_continuation_goes_back_right_after_its_head` (xfail đã
gỡ) và các control; `tests/test_ocr_legal_normalizer.py::test_mixed_page_sizes_and_landscape_pages`,
`::test_doclings_cross_page_merge_is_split_back_even_when_the_rules_accept_it`.

## 3. D8-02 — footnote gắn với bảng / ảnh (P2, blocker) — commit `de55d4e`, D-42

**Lỗi:** docling-core 2.96.0 không viết footnote gắn với bảng / ảnh trong Markdown — mất ở **Standard và Legal**.

**Sửa:** mỗi footnote gắn kèm viết **một lần**, ngay sau item, đúng cách Docling viết đoạn văn của chế độ đó (Standard
escape `&` → `&amp;`, Legal không); tham chiếu hỏng bỏ qua, không lặp; bộ lọc nhãn của người gọi được tôn trọng; tài liệu
không có footnote gắn kèm **giống từng byte** như trước.

Test: `tests/test_phase12d9_text_preservation.py` §I (một bảng một ghi chú, nhiều ghi chú giữ thứ tự, bảng liên tiếp, ảnh
+ caption, ghi chú dùng chung, ghi chú trang sau / không provenance, tham chiếu hỏng, byte-identical khi không có),
`tests/review_phase12d8/test_legal_d8.py::test_d8_02_legal_keeps_a_footnote_attached_to_a_table_or_picture`. Giới hạn:
đầu ra HTML vẫn như upstream.

## 4. E0-07 — chữ TSV nguyên văn

Bản vá 12D7 (`0001`, `05` không thành `1.0`, `5.0`): Windows 12E2 đạt **383 / 383** lần gọi, 3 184 token số (trên
`4587eb7`). 12D9 chỉ đổi phần xử lý lỗi của cùng hàm (stderr được giữ để phân loại, timeout — E2-04); phần đọc TSV không
đổi (test AST). Windows chạy lại trên commit cuối (G-03). **E0-07 TSV PRESERVATION: PASS** (Windows 12E2 + Cloud).

## 5. Benchmark 92 fixture — Legal 1.3.1

[benchmark_legal_1_3_1.json](phase12d9/benchmark_legal_1_3_1.json) (oracle đã vá D8-ORC-01 … 06; Tesseract 5.3.4 Cloud;
docling 2.129.0, docling-core 2.96.0; ground truth khai báo của fixture, không so với đầu ra khác của hệ thống).

| Chỉ số (618 đơn vị bắt buộc) | Standard | Legal 1.3.1 |
|---|---|---|
| xóa sai (đơn vị / token) | 12 / 67 | **0 / 0** |
| nối sai | 20 | **0** |
| chèn sai (dòng / token) | 3 / 31 | **0 / 0** |
| đơn vị bị đổi | 0 | 0 |
| cặp đảo thứ tự (Kendall, D8-ORC-05) | 43 | 35 |
| placeholder mất | 0 / 9 | 0 / 9 |
| trường quan trọng | 85 / 89 | 89 / 89 |
| marker hiển thị | 17 / 36 | 36 / 36 |
| tài liệu có xóa sai / nối sai | 6 / 17 | 0 / 0 |
| bảng giữ nguyên | đạt | đạt (giống từng byte) |

**35 cặp đảo của Legal** nằm ở 3 tài liệu (`f12_two_columns` 1, `d5_f02_voucher_numbers_beside_label` 24,
`d5_f02_voucher_numbers_alone_top_right` 10). Kiểm 12D9: thứ tự đơn vị của Legal **giống hệt** Standard ở cả 3 ⇒ đây là
thứ tự đọc của Docling, Legal không thêm cặp nào; ở 2 tài liệu khác Legal bỏ được 8 cặp đảo của Standard (6 + 2). Đây là
cột "đảo do Docling" / "đảo do Legal" mà G-05d yêu cầu cho fixture.

## 6. Cần ở Local

G-H1 (gạch nối), G-H2 (footnote), G-H3 (thứ tự đọc), G-03, G-05 trong
[PHASE12D9_LOCAL_ACCEPTANCE_CHECKLIST.md](PHASE12D9_LOCAL_ACCEPTANCE_CHECKLIST.md). Chỉ ghi số liệu, không gửi chữ tài liệu.
