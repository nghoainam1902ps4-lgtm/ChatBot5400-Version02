# Phase 12D9 — Cổng Standard expected-diff v2 (D8-STD-01 … 05, E2-03)

Quyết định: D-44 trong [DECISIONS.md](../ocr/DECISIONS.md). Mã: `scripts/ocr/phase12d9_standard_export.py` (xuất +
bằng chứng), `scripts/ocr/phase12_standard_diff.py` (so). Commit `75c9455`, `31f72a8`.

## 1. Vì sao viết lại

Review 12D8: cổng v1 có thể báo `unchanged` khi khác khoảng trắng / cấu trúc (D8-STD-01); chấp nhận một thay đổi ở bất kỳ
đâu nếu TSV nào đó dự đoán nó (D8-STD-02); quy trình checklist không tạo được bằng chứng đúng crop và khớp tên theo tiền
tố (`qd1` nhận TSV của `qd10`) (D8-STD-03); trả mã 0 cho run không chứng minh gì (D8-STD-04); văn bản v1.2.0 được mô phỏng
thay vì tính lại (D8-STD-05). Một hunk có nhiều nguyên nhân bị phân loại sai (E2-03).

## 2. Cách làm v2

1. **Xuất cùng lần chuyển đổi:** `phase12d9_standard_export.py` chuyển đổi mỗi PDF **một lần** bằng đường production
   (`convert_file`, Standard, engine chỉ định) và ghi trong chính lần đó: `<tên>.md`, `<tên>.evidence/` (TSV thô của
   **mỗi** lần gọi Tesseract + sidecar `{document, page, region, bbox, invocation, attempt, engine, model_files[sha256]}`,
   `elements.jsonl` với văn bản v1.2.0 / ứng viên của từng vùng, phép nối khối, footnote đã viết), `manifest.json`
   (commit, phiên bản, engine, SHA-256 đầu vào / đầu ra, trạng thái chuyển đổi hoặc lỗi). File 0600, thư mục 0700;
   console chỉ in số đếm. `--out` phải mới hoặc rỗng (không trộn hai lần chạy).
2. **Phía v1.2.0:** cùng công cụ chạy trên image v1.2.0 (không có module bản vá ⇒ chỉ đầu ra + manifest, không bằng
   chứng). Image v1.2.0 không có script: chép vào `/app/scripts/ocr/` của container đó trước (`docker compose cp`).
3. **So:** `unchanged` chỉ khi **byte giống hệt**. Khoảng trắng và cấu trúc Markdown là token (padding bảng được chuẩn
   hóa). Mỗi khác biệt phải được **lát kín** bởi các đơn vị bằng chứng: văn bản v1.2.0 của đơn vị được **tính lại** bằng
   chính mã upstream (pandas thật với các dòng cha của TSV, `sanitize_text` upstream), mỗi đơn vị dùng **một lần**, gắn
   với ngữ cảnh 2 token của crop / phần tử sở hữu (xử lý cả mép tài liệu); crop sở hữu vị trí mà không dự đoán thay đổi ⇒
   hồi quy. Một hunk có thể mang nhiều lớp (E2-03); chỉ được chứng minh một phần ⇒ `not verified`. Không miễn trừ cả tài
   liệu.

| Lớp | Ý nghĩa |
|---|---|
| `unchanged` | hai file giống từng byte |
| `expected TSV fix` | chữ TSV nguyên văn (E0-07) — bằng chứng TSV thô của đúng crop |
| `expected hyphen fix` | `-` được giữ (D8-03) — bằng chứng phần tử / phép nối khối |
| `expected attached footnote fix` | footnote gắn kèm được viết (D8-02) — bằng chứng footnote đã viết, đúng một lần |
| `expected orientation fix` | chỉ khi có bằng chứng hướng xoay — **chưa có công cụ ghi** ⇒ hunk đó `not verified`, xem tay |
| `not verified` | thiếu / không xác thực được bằng chứng, chỉ chứng minh một phần, thay đổi dự đoán mà không xuất hiện, tài liệu chuyển đổi lỗi |
| `unexpected regression` | khác biệt không thay đổi được duyệt nào giải thích |

| Mã thoát | Khi nào |
|---|---|
| 0 | mọi tài liệu `unchanged` hoặc khác biệt được chứng minh hết |
| 1 | có `unexpected regression` |
| 2 | có `not verified` |
| 3 | run không chứng minh gì: không tài liệu, thiếu một phía, trùng ID (không phân biệt hoa thường), manifest không đọc được / lệch SHA-256 / đầu ra không có trong manifest, đầu vào khác giữa hai lần chạy, tài liệu đổi mà không có bằng chứng, bằng chứng lệch, tài liệu chuyển đổi lỗi ở bất kỳ phía nào |

Báo cáo `standard_diff.json` / `.md` mặc định **không chứa chữ**; `--with-text` ghi token của từng hunk vào file quyền
chủ sở hữu, không bao giờ in ra console.

## 3. Kiểm ở Cloud

`tests/test_phase12d9_standard_gate.py` (25): Tesseract **thật**, pipeline PDF thật của Docling (chỉ layout là stub với
vùng cố định — không có trọng số ở Cloud), `convert_file` thật; phía v1.2.0 = cùng chuyển đổi với mã upstream (parse TSV,
ghép chữ, Markdown).

* Mọi khác biệt thật (`1.0` → `0001`, `TTBNNPTNT` → `TT-BNNPTNT`, `VTKHTC` → `VT- KHTC`) được chứng minh ⇒ mã 0; console
  và báo cáo mặc định không chứa chữ.
* Đột biến đầu ra ứng viên bị bắt: đổi một chữ số, xóa một từ, NBSP thay khoảng trắng, đổi vùng không đổi ⇒
  `unexpected regression`; mất `-` trở lại ⇒ `not verified` (thay đổi được dự đoán không xuất hiện); đầu ra không phải
  đầu ra đã ghi (lệch SHA-256 manifest) ⇒ mã 3.
* Unit: footnote đúng một lần, phép nối khối giữ `-`, hai nguyên nhân trong một hunk (E2-03), hunk chỉ chứng minh một
  phần, hướng xoay cần bằng chứng riêng, khoảng trắng / cấu trúc không bao giờ được giải thích; lỗi mức run; tài liệu
  chuyển đổi lỗi (kể cả khi không phía nào có đầu ra, và đầu ra cũ bên cạnh); export trên checkout không có module bản vá;
  số đếm gạch nối của manifest (đủ trên OCR thật, thiếu khi một `-` bị mất).
* `tests/review_phase12d8/test_standard_diff_d8.py` (13 xfail D8-STD đã gỡ), `tests/test_phase12d7_standard_diff.py`
  (TSV có dòng cha như Tesseract ghi; kỳ vọng mới có chú thích `# was:`).

**E2-03 MIXED-HUNK EXPECTED-DIFF: PASS** (Cloud; Windows đã tái hiện bằng fixture tổng hợp ở 12E2, chạy lại ở G-04).

## 4. Còn thiếu

* Bằng chứng hướng xoay chưa được ghi ⇒ mọi khác biệt do cổng hướng xoay (E1-05) sẽ là `not verified` và phải xem tay
  với ảnh crop (G-04c).
* Chưa chạy trên 22 PDF thật với model thật: **D8-STD-03 LOCAL VERIFICATION REQUIRED**. Lệnh:
  [PHASE12D9_LOCAL_ACCEPTANCE_CHECKLIST.md](PHASE12D9_LOCAL_ACCEPTANCE_CHECKLIST.md) G-04.
