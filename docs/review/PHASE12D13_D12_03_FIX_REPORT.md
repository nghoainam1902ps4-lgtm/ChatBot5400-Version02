# Phase 12D13 — Sửa D12-03 (cổng Standard expected-diff, chế độ release)

Commit sửa: `842c9b5` (chỉ `scripts/ocr/phase12_standard_diff.py` và hai dòng marker của bốn control D12-03).
Không sửa mã runtime cho phát hiện này. Mã thoát 0 / 1 / 2 / 3 giữ nguyên.

## 1. Lỗi

`verify_bound_output` dựng lại **văn bản baseline** của một span từ các dòng TSV, nhưng lấy **văn bản candidate**
từ chính bản ghi `elements.jsonl` mà candidate tự ghi. Chỉ `cell["raw"]` được so với dòng TSV; `cell["text"]`
và chuỗi đã ghép thì không. Vòng dò ô `break` khi lệch rồi coi phần còn lại hợp lệ, và `_tsv_cause` gán `tsv`
cho mọi khác biệt còn lại. Hậu quả: `--release` trả mã 0, lớp `expected TSV fix` cho một candidate đổi "Điều 5"
thành "Điều 6", làm rơi "không", thêm mệnh đề không có ô nguồn, hoặc cắt bớt văn bản.

## 2. Bản sửa

Mỗi phần tử được **dựng lại chỉ từ bằng chứng nguồn** (`_element_proof`):

| Yêu cầu | Cách kiểm |
|---|---|
| Ràng buộc text của ô với TSV gốc | Với mọi ô OCR: `cell["text"]` phải bằng đúng dòng TSV của nó theo cách candidate parse (`raw.replace("\x02", "-").strip()`), `cell["raw"]` bằng dòng đó, tâm ô nằm trong crop, đúng trang. |
| Không tin span / element thiếu chứng cứ | Văn bản candidate phải bằng **phép ghép đã vá** của chính các ô đó (`_sanitize_text` của candidate), với cờ xuống dòng tính lại bằng `same_line_flags` từ **hộp đã ghi** của từng ô. Ô không có hộp ⇒ không có bằng chứng xuống dòng ⇒ không được khép gạch nối. Element không có ô ⇒ từ chối. |
| Kiểm toàn bộ span | Văn bản candidate = toàn bộ span (so bằng). Vòng dò vị trí đi hết span: lệch trong span **có thay đổi**, hoặc lệch trước một dòng có gạch nối ⇒ NOT VERIFIED; span có thay đổi mà còn ký tự thừa ⇒ NOT VERIFIED. |
| Không thêm / xoá / đổi token ngoài OCR evidence | Token candidate chỉ đến từ dòng TSV (ô OCR) hoặc ô text-layer (cùng giá trị ở hai phía). Văn bản baseline = **phép ghép upstream** của cùng các dòng theo pandas; luôn được kiểm (trước đây bỏ qua khi span không đổi). |
| Giữ thứ tự và định danh từng occurrence | Mỗi `(invocation, row)` chỉ dùng **một lần** trong toàn tài liệu; mỗi element chỉ cho **một** span; span theo thứ tự (`cursor`); dòng có gạch nối phải khớp đúng vị trí, đúng thứ tự (G-H1 giữ nguyên). |
| Chỉ chứng nhận khác biệt hợp đồng cho phép | Nguyên nhân lấy từ chứng minh: `tsv` khi một dòng có dạng pandas khác dạng đã vá; `hyphen` khi phép ghép upstream của chính các token candidate khác phép ghép đã vá. Span đổi mà không có nguyên nhân nào ⇒ NOT VERIFIED. |
| Footnote gắn kèm | Mỗi note phải có bản ghi `footnotes.jsonl` của chính lượt export (dùng một lần) và **đúng một** element đã ghi trên trang đó có text sinh ra note; element đó cũng phải qua `_element_proof`. |
| Thiếu provenance ⇒ NOT VERIFIED | Mọi `KeyError` / `ValueError` / thiếu file đều về NOT VERIFIED (mã 2), không bao giờ mã 0. |

Đường chẩn đoán (không `--release`) và `load_evidence` không đổi.

## 3. RED → GREEN

Bốn control D12-03 của review (`tests/test_phase12d12_review_controls.py`, nguyên byte trừ hai dòng marker
`xfail(strict=True, reason=D12_03)` được bỏ):

| Lượt | Commit | Kết quả |
|---|---|---|
| RED, `--runxfail` | `26ff1c1` (candidate `18eeecb` + hồ sơ review) | **4 failed** (3 tổng hợp: chữ số, rơi token, thêm mệnh đề; 1 Tesseract + Docling thật: "Điều 6", mất "không"), 1 passed (control hợp lệ) |
| GREEN, `--runxfail` | bản sửa | **5 passed** |
| GREEN, marker strict còn nguyên | bản sửa | 4 XPASS(strict) đúng như thiết kế ⇒ marker được bỏ |

Evidence Local: `E:\ProjectWeb\CHATBOT5400\d13-evidence\d12-03-RED-26ff1c1.txt`, `d12-03-GREEN-runxfail.txt`,
`d12-03-gate-suites-fixed.txt`.

## 4. Các ca hợp lệ trước đây vẫn đạt

Chạy lại đầy đủ các bộ dùng comparator (test runner Linux, Tesseract 5.5.0 `eng` / `osd` / `vie`, Docling 2.129.0):
`test_phase12d10_review_controls.py` (16 control D10 gồm D10-05, D10-06, D10-07), `test_phase12d11_bound_gate.py`
(D11 bound gate, kể cả ca Tesseract + Docling thật trả mã 0), `test_phase12d12_review_controls.py`,
`test_phase12d7_standard_diff.py`, `test_phase12d7_standard_parity.py`, `test_phase12d9_standard_gate.py`,
`review_phase12d8/test_standard_diff_d8.py`: **106 passed**, 2 skipped (control server cần
`CB5400_D12_SURREAL_URL`), 2 xfailed (D12-01, D12-02 — P3, giữ nguyên), 4 XPASS(strict) của D12-03 trước khi bỏ
marker. Không assertion hay fixture nào bị sửa. Kết quả trên candidate cuối: xem
[báo cáo hồi quy](PHASE12D13_REGRESSION_REPORT.md).

## 5. Ảnh hưởng tới G-04 và tài liệu NOT VERIFIED

Bản sửa làm cổng **chặt hơn**, không nới. Ngoài các loại đã biết ở review (số hiệu gạch nối trong tiêu đề mục,
list item, footer, bảng, đoạn nối qua trang, sau token bị escape), từ nay thêm một loại cho NOT VERIFIED: **gạch
nối được khép giữa các ô text-layer** (PDF có lớp chữ), vì export không ghi hộp của ô text-layer nên không có
bằng chứng xuống dòng. Đây là thiếu provenance, không phải hồi quy, và đúng yêu cầu "thiếu provenance ⇒ NOT
VERIFIED". Không hạ tiêu chí G-04.

Quy trình kiểm chứng Local riêng cho tài liệu NOT VERIFIED (không thay mã 0, chỉ là bằng chứng bổ sung để chủ
dự án quyết định): xem mục G-04 của [checklist nghiệm thu Local](PHASE12D13_LOCAL_ACCEPTANCE_CHECKLIST.md).

## 6. Giới hạn còn lại (không chặn)

- Hộp của ô OCR là dữ liệu tự khai trong evidence không ký (inventory có hash nhưng không có chữ ký). Giả mạo
  hộp chỉ có thể biến một dấu cách thành khép gạch nối giữa hai token **đã có trong TSV**; không thể thêm, xoá
  hay đổi token.
- Định danh model / commit / image vẫn là chuỗi tự khai (như review đã ghi).
- Đường chẩn đoán không `--release` vẫn có thể trả 0; checklist bắt buộc `--release`.
