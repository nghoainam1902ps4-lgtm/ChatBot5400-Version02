# Phase 12D5 — Benchmark chất lượng (bảo toàn nội dung Legal)

Dữ liệu: `docs/review/phase12d5/benchmark_8d0c438.json` (đo ở 12D5A, trước khi sửa),
`benchmark_8d0c438_final_oracle.json` (mã 8d0c438 đo lại bằng oracle cuối cùng),
`benchmark_after.json` (normalizer 1.2.0), `oracle_mutations.json`,
`red_8d0c438_normalizer_tests.txt`. Lệnh: `uv run python scripts/ocr/phase12_benchmark.py`
(schema `chatbot5400-phase12-benchmark/3`). Docling 2.129.0, docling-core 2.96.0, Tesseract 5.3.4.

## 1. Oracle độc lập (R2-14, T-01, T-03)

`scripts/ocr/phase12_oracle.py` thay oracle cũ (so chữ). Chân lý (ground truth) khai báo trong
fixture TRƯỚC khi sửa mã, không suy ra từ đầu ra của normalizer:

- Mỗi đơn vị bắt buộc (dòng chữ, hàng bảng, placeholder ảnh, chữ trong ảnh) có định danh nguồn:
  trang + bounding box → DocItem. Kiểm theo định danh: đơn vị còn trong lớp BODY, chữ, số lần xuất
  hiện, thứ tự, vùng artifact, vùng bắt buộc. Một dòng cùng chữ ở chỗ khác (số trang trùng số khoản,
  artifact trùng chữ) không thay được đơn vị bị xóa.
- Phát hiện: xóa nhầm, chèn, đảo thứ tự, nối sai (trong tài liệu và khi hiển thị), mất số khoản,
  mất số chứng từ, mất một lần xuất hiện của nội dung lặp, mất placeholder, đổi một chữ số.
- Furniture, placeholder, nội dung bảng không bị bỏ qua.

Kiểm đột biến (`tests/test_phase12d5_oracle.py`, mỗi đột biến áp lên đầu ra đúng của mọi fixture):

| Đột biến | Phát hiện |
|---|---|
| xóa một dòng bắt buộc | 478 / 478 |
| đưa item bắt buộc ra khỏi body (định danh) | 471 / 471 |
| chèn một dòng | 621 / 621 |
| đảo hai dòng kề nhau | 468 / 468 |
| đảo với dòng artifact / furniture | 94 / 94 |
| nối sai — hiển thị thành một dòng | 439 / 439 |
| nối sai — trong tài liệu | 439 / 439 |
| xóa một lần xuất hiện của nội dung lặp | 58 / 58 |
| mất placeholder ảnh | 6 / 6 |
| đổi một chữ số (số, ký hiệu, ô bảng) | 294 / 294 |

Fixture gốc bị sửa ở 12D3 để né lỗi upstream đã được trả lại; 47 fixture `d5_*` thêm mọi phản ví
dụ của 12D4 và biến thể theo vị trí / nhãn / đuôi Unicode. Tổng 92 fixture, 618 đơn vị bắt buộc.
Ba fixture khai báo `upstream_reordering` (thứ tự đọc của Docling khác thứ tự in — có ở cả
Standard): `f12_two_columns`, `d5_f02_voucher_numbers_beside_label`,
`d5_f02_voucher_numbers_alone_top_right`.

## 2. Kết quả (92 fixture, 618 đơn vị bắt buộc)

| Chỉ số | Standard (v1.2.0, không đổi) | Legal 1.0.0 | Legal 1.1.0 (8d0c438) | **Legal 1.2.0 (12D5)** |
|---|---|---|---|---|
| đơn vị bị xóa nhầm (token) | 12 (67) | 80 (236) | 30 (50) | **0 (0)** |
| nối sai | 16 | 36 | 30 | **0** |
| chèn (token) | 3 (31) | 3 (6) | 3 (6) | **0 (0)** |
| đơn vị bị đổi chữ | 1 | 1 | 1 | **0** |
| placeholder ảnh bị mất / bắt buộc | 0 / 9 | 7 / 9 | 5 / 9 | **0 / 9** |
| ký hiệu Điều / Khoản bị đổi | 8 | 0 | 0 | **0** |
| đảo thứ tự | 18 | 2 | 6 | 14 (chỉ 3 fixture `upstream_reordering`, bằng Standard từng fixture) |
| trường trọng yếu còn đúng | 84 / 89 | 58 / 89 | 69 / 89 | **89 / 89** |
| tài liệu có xóa / nối / chèn / đổi chữ / mất placeholder | 19 | — | 39 | **0** |
| bảng giống hệt Standard | — | có | có | có |
| CER / WER trung bình | 0,0722 / 0,0861 | 0,046 / 0,0468 | 0,0401 / 0,0452 | 0,0346 / 0,0395 |
| thời gian (tổng 92 tài liệu) | 80 ms | — | 172 ms | 729 ms (1 000 trang: 1,4 s) |

Chạy cùng benchmark trên mã 8d0c438 trước khi sửa (đỏ): 74 cặp test normalizer thất bại
(`red_8d0c438_normalizer_tests.txt`).

Cảnh báo Legal 1.2.0 (số tài liệu): `page_number_kept` 17, `join_not_made` 14,
`upstream_merge_undone` 13, `repeated_line_kept` 9, `picture_without_text` 4,
`picture_text_unverified` 3, `hyphen_at_page_break_not_joined` 2, `furniture_text_kept` 1. Mỗi cảnh
báo là chỗ normalizer GIỮ nguyên vì bằng chứng không đủ mạnh.

## 3. Đổi gì để có 0 mất mát (normalizer 1.2.0)

- F-02: một số đứng riêng chỉ được coi là số trang khi đủ MỌI điều kiện: dạng số trang chặt (không
  số 0 đầu; "n/m", "trang n/m" chỉ khi m là số trang), ở dải trên / dưới và ngoài cùng của trang,
  một mình trên dòng (không có item khác cùng độ cao — "Số:" + "0001" là một trường) và không nằm
  dưới nhãn kết thúc bằng ":", căn giữa hoặc sát mép ngoài hoặc đối xứng trang chẵn / lẻ (không bao
  giờ chỉ ở bên trái, nơi số khoản tách rời nằm), cùng vị trí dọc, cùng độ lệch "số in − số trang
  PDF" trên ≥ 3 trang VÀ ≥ 60 % số trang; tài liệu 1–2 trang không bao giờ đủ. Còn lại giữ
  (`page_number_kept`).
- F-03: chỉ nối qua trang khi có đúng một ứng viên, đoạn trước chưa hết câu, dòng sau không mở đầu
  một cấu trúc (điểm `a)` / `c )` / `a-` / `a,`, footnote `(*)` `1.` `¹`, ngày tháng, đơn vị tính,
  tiêu đề chạy, dòng ký, URL, "Trang n/m"…), không có ứng viên khác ở trang sau; còn lại giữ và
  cảnh báo `join_not_made`.
- R2-01: phép nối của chính Docling được tách lại khi có bằng chứng (provenance + charspan + phần tử
  trước khi ghép của pipeline); bỏ gạch nối không có bằng chứng thì không đoán — giữ và báo.
- R2-11 / F-06: nội dung nhãn header / footer / furniture xuất hiện một lần (số hiệu văn bản, tên
  đơn vị, footnote, caption) được giữ (`furniture_text_kept`); placeholder `<!-- image -->` chỉ bỏ
  với ảnh < 4 % diện tích trang (chữ ký, dấu, logo), mọi ảnh khác giữ kèm cảnh báo có vị trí;
  caption / một chữ không được coi là bằng chứng ảnh đã OCR (`picture_text_unverified`).
- R2-02 / F-17: `full_text` không còn ký tự thoát Markdown; khi hiển thị, `*`, `_`, ngoặc, tỉ lệ,
  công thức, URL, mã nghiệp vụ, ký tự Markdown được thoát đúng (`legal-display.ts` = bản Python,
  48 vector chung; test React thật kiểm chữ hiển thị đúng chữ in).

## 4. Giới hạn — chưa phải nghiệm thu chất lượng thật

- Fixture tổng hợp dựng `DoclingDocument` + phần tử pipeline (`tests/legal_harness.py`), **không**
  phải OCR thật trên scan thật (Layout Heron / TableFormer / Tesseract thật trên PDF scan chưa chạy
  ở Cloud cho bộ này). Nghiệm thu pipeline thật: W-RC-07…09, W-LEG-19…22 (LOCAL).
- Thứ tự đọc sai của Docling (3 fixture) KHÔNG được normalizer phát hiện lúc chạy — chỉ oracle thấy.
  Không sửa (cần heuristic thứ tự đọc — ngoài phạm vi, không đổi Docling).
- Vì vậy: **LEGAL CONTENT PRESERVATION: PARTIAL** — 0 mất mát trên 92 fixture tổng hợp, chưa có bằng
  chứng trên scan thật, đảo thứ tự upstream không được cảnh báo.
