# Phase 12D7 — Báo cáo an toàn Legal (E1-09, E1-03)

Bộ chuẩn hóa **1.3.0** ([D-38](../ocr/DECISIONS.md)). Mã: `open_notebook/ocr/legal_normalizer.py`. Benchmark:
[`phase12d7/benchmark_legal_1_3_0.json`](phase12d7/benchmark_legal_1_3_0.json) (92 fixture, oracle độc lập 12D5,
ground truth **không đổi**).

## 1. E1-09 — nối không an toàn qua trang

**Quan sát Windows (12E1):** trên các phản ví dụ scan thật của F-03, đoạn văn hai trang bị ghép sai 3/4 lần (điểm
mất ký hiệu do OCR, dòng đơn vị tính bị OCR làm hỏng, tiêu đề chạy viết thường).

**Phân tích A / B (Cloud, dựng lại ba dạng từ mô tả của 12E1, không dùng tài liệu thật):**

| | Nguồn | 1.2.0 | 1.3.0 |
|---|---|---|---|
| A | Legal tự nối hai đoạn của hai trang | có (quy tắc bảo thủ, 6/8 phép được phép) | **không bao giờ** |
| B | Docling đã nối sẵn hai khối của hai trang thành một item | chỉ tách khi quy tắc cũ từ chối | **tách mỗi khi charspan khớp** (bằng chứng trực tiếp) |

Trong cả ba dạng, câu ghép sai của 1.2.0 là **B** (Docling: `joins=0, undone=0`); 1.3.0 tách lại (`undone=1`), không
đoán chữ thiếu, không dựng lại gạch nối khi không có bằng chứng. Docling chỉ nối khi phần trước kết thúc bằng chữ ASCII
thường / dấu phẩy / gạch nối.

**Quy tắc 1.3.0:**

1. Không tạo câu mới; hai phần của đoạn bị cắt qua trang giữ thành hai đoạn, đúng thứ tự đọc đã kiểm.
2. Không bao giờ nối footnote, dòng đơn vị tính, ngày, header / footer, tiêu đề chạy, phụ lục, chữ ký, văn bản độc lập,
   bảng — vì không còn phép nối nào.
3. B qua ranh giới trang: tách khi các charspan của provenance cộng lại đúng; trong cùng một trang (cột): chỉ tách khi
   quy tắc cũ từ chối (`_pair_refusal`). Charspan không khớp ⇒ giữ nội dung, cảnh báo `upstream_merge_kept`. Gạch nối
   Docling đã bỏ chỉ khôi phục khi phần tử trước khi ghép cho thấy; không thì giữ và cảnh báo `upstream_dehyphenation`.
4. Từ bị cắt bởi gạch nối cuối trang: giữ hai phần, cảnh báo `hyphen_at_page_break_not_joined` (có trang).
5. Mọi phép tách ghi `upstream_merge_undone` với trang, bbox, chữ trước / sau (provenance giữ nguyên).

**Mô tả trên giao diện** (vi / en): bỏ câu hứa "cải thiện đoạn văn bị ngắt do phân trang"
(`frontend/src/lib/locales/*/index.ts`, `legalHelp` / `legalDetail`).

## 2. Kết quả

| Chỉ số (92 fixture) | Legal 1.2.0 (12D5) | **Legal 1.3.0** |
|---|---|---|
| đơn vị bị xóa sai | 0 | **0** |
| nối sai (false merge) | 0 | **0** |
| chèn sai | 0 | **0** |
| đơn vị bị sửa | 0 | **0** |
| placeholder mất | 0 | **0** |
| trường quan trọng giữ | 89 / 89 | **89 / 89** |
| marker giữ | 36 / 36 | **36 / 36** |
| phép nối được phép đã thực hiện | 6 / 8 | **0 / 8** (thay đổi hành vi có chủ đích) |
| đảo thứ tự (false reordering) | 14 | 14 (thứ tự đọc của Docling, không đổi) |
| tài liệu mất nội dung (theo oracle, đều do thứ tự đọc upstream) | 3 | 3 — **không có mất nội dung mới** |
| CER / WER trung bình | 0.0346 / 0.0395 | 0.0346 / 0.0395 |
| tài liệu có `upstream_merge_undone` | — | 17 |

Standard (Docling nguyên bản) trên cùng bộ: 12 đơn vị bị xóa, 16 nối sai, 3 chèn — không đổi so với 12D5.

**0 phép nối sai do Legal tạo ra; không mất nội dung mới; thứ tự đọc chỉ đổi ở chỗ tách có bằng chứng.**

## 3. Test

| Nhóm | Test |
|---|---|
| E1-09 dạng scan thật | `tests/test_ocr_legal_normalizer.py::test_e1_09_real_scan_shapes_are_never_one_paragraph`, `test_doclings_cross_page_merge_is_split_back_even_when_the_rules_accept_it` |
| Không nối kể cả nơi quy tắc cũ nối | `test_no_cross_page_join_even_where_the_old_rules_joined`, `test_join_baseline_is_not_made`, `test_join_refused_and_reason_reported`, `test_single_line_at_the_page_bottom_is_not_joined_either` |
| Quy mô | `test_many_cut_paragraphs_scale_linearly`, `test_large_document_with_tables_pictures_and_cut_paragraphs` |
| R2-01 / F-03 (retest) | `tests/review_phase12d4/test_legal_reaudit.py` (mọi fixture `must_join` được ghi là đã bỏ — ground truth không đổi), `tests/test_ocr_legal_pipeline.py`, `tests/test_ocr_phase12_scripts.py` |

Thay đổi trong test cũ: chỉ các khẳng định "phép nối được thực hiện" (đổi thành "không có phép nối"); không sửa ground
truth fixture nào.

## 4. E1-03 — số do OCR nhận dạng

**Nguyên nhân:** không phải Legal. Số trang đọc là `2` tới Legal thành `2.0` (E0-07); `2.0` không phải dạng số trang
chặt nên ở lại nội dung; số chứng từ `0001` tới thành `1.0`.

**Sau E0-07** (`tests/test_phase12d7_numeric_preservation.py`, 11 test):

- chuỗi TSV thô → ô OCR của Docling (lớp thật) → Legal: `0001`, `2024`, `000123`, `9.`, `12.50` giữ nguyên; với
  parser cũ Legal giữ **đúng** `1.0`, `2024.0`… (không đoán);
- `1.0`, `2.0` (dạng parser cũ) ở vị trí số trang: không phải số trang, giữ nguyên, không bị đổi thành `1`/`0001`;
- cùng các trang với số `1`…`5` (như Tesseract đọc): được nhận là số trang theo quy tắc cũ;
- `0001`…`0005` (số 0 đầu), `1/2024`…(kỳ báo cáo), năm 2021–2025 ở vị trí số trang: giữ;
- 15 dòng số / mã trong thân (số hiệu văn bản, chứng từ 18 chữ số, `NA`, `N/A`, `05%`, `Quý 1/2024`…): giữ đúng,
  không xóa, không gộp.

Không có regex đoán `1.0` từng là `0001`; không xóa dòng số nào. Kiểm lại trên 22 PDF thật: W-12D7-03.
