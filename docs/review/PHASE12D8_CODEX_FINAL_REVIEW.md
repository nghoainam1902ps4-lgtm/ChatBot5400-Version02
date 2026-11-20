# Phase 12D8 — Review cuối trước nghiệm thu release candidate

| | |
|---|---|
| Đối tượng | `4587eb77e25935db2d4375fe55be64f22341d1bb` (`feature/legal-document-normalization`, PR #50 — Draft) |
| Baseline | v1.2.0 `f2fdf27`; ứng viên trước sửa runtime `904c15c` |
| Nhánh review | `review/phase12d8-codex-final-audit` (chỉ thêm tài liệu này và `tests/review_phase12d8/`) |
| Runtime code | **không sửa** (`git diff 4587eb7..HEAD -- . ':!docs/review' ':!tests/review_phase12d8'` rỗng) |
| PR / tag / release / production | không approve, không merge, không tạo tag / release, không kết nối production |
| Chi tiết từng finding | [PHASE12D8_FINDING_STATUS.json](PHASE12D8_FINDING_STATUS.json) · [PHASE12D8_RELEASE_BLOCKERS.md](PHASE12D8_RELEASE_BLOCKERS.md) · [PHASE12D8_LOCAL_GATE_CHECKLIST.md](PHASE12D8_LOCAL_GATE_CHECKLIST.md) |

## 0. Tính độc lập và giới hạn — đọc trước

- **Reviewer không phải Codex.** Đề bài giao cho một reviewer thuộc họ model khác với bên phát triển. Phiên thực hiện
  là một phiên Claude Code mới, **cùng họ model** với bên phát triển. Tên file giữ theo đề bài để quy trình tìm thấy,
  nhưng yêu cầu "khác họ model" **không được đáp ứng**. Phiên này không dùng lại ngữ cảnh của 12D3–12D7; mọi kết
  luận dựa trên mã, test tự viết và lệnh tự chạy. Ba mảng (offline, hướng xoay, oracle / standard-diff) được giao cho
  tiến trình phụ rồi kiểm lại: toàn bộ test của họ được chạy lại, các finding P2 được đối chiếu với mã nguồn.
- **Môi trường:** Cloud Linux, Python 3.12, Docling 2.129.0, docling-core 2.96.0, pandas 3.0.0, Tesseract 5.3.4
  (`vie`, `eng`, `osd`). **Không có:** Windows, PowerShell, Docker daemon, Layout Heron / TableFormer, PDF nghiệp vụ,
  model Agri, bảng mã tiktoken (proxy chặn). Không có gì trong tài liệu này là bằng chứng Windows hay runtime thật.
- Báo cáo 12E0 / 12E1 đã làm sạch không có trong repo ⇒ E1-01, E1-02, E1-06 không đánh giá được.

## 1. Kết luận

Bản vá E0-07 làm đúng việc của nó. Nhưng review **chưa đạt** theo tiêu chí §10 của đề bài: còn 1 P1 mở và ba lỗi
tái hiện được làm đổi hoặc mất nội dung pháp lý. Hai trong ba lỗi có từ v1.2.0 (hành vi upstream của Docling), nên
cần quyết định của chủ dự án chứ không chỉ một bản sửa.

| Mã | Mức | Tóm tắt | Có từ | Chế độ |
|---|---|---|---|---|
| **D8-03** | P1 | Docling bỏ dấu gạch nối cuối dòng / cuối từ OCR: `05/2024/TT-` + `BNNPTNT` → `05/2024/TTBNNPTNT`; `2021-` + `2025` → `20212025` | v1.2.0 (upstream) | Standard + Legal, mọi engine |
| **D8-01** | P2 | Legal đảo thứ tự đọc khi tách phép nối liên trang của Docling nếu hai trang khác chiều cao, hoặc trang sau hai cột | 12D5; lộ rộng hơn ở 12D7 | Legal |
| **D8-02** | P2 | Footnote Docling gắn vào bảng / ảnh không có trong nội dung, không cảnh báo | v1.2.0 (upstream) | Standard + Legal |

Ngoài ra: công cụ nghiệm thu Standard expected-diff có ba lỗ hổng làm nó không dùng được làm cổng (D8-STD-01 / 02 /
04) và quy trình không tạo được bằng chứng cho nó (D8-STD-03); công cụ chẩn đoán hướng xoay sai ở 90° / 270°
(D8-ORI-01); `build-package.ps1` hỏng khi máy không có `uv` (D8-OFF-11, chỉ đọc mã); công cụ offline và release notes
không ghi updater tự động là EXPERIMENTAL (D8-OFF-01 / 02). Không tìm thấy lỗi nghiêm trọng trong quy trình thủ công
offline; có 7 điểm P3 nên sửa trong tài liệu.

Tổng số finding mới: **37** — P0: 0 · P1: 1 · P2: 11 · P3: 20 · P4: 5.

## 2. Ưu tiên 1 — Bản vá TSV của Tesseract (E0-07): PASS

Mã: `open_notebook/ocr/docling_patches.py`; áp dụng tại `open_notebook/ocr/options.py:392-396`.
Test: `tests/review_phase12d8/test_tsv_patch_d8.py` (138 đạt, 6 xfail thuộc D8-03).

| Hạng mục | Kết quả | Cách kiểm |
|---|---|---|
| Chốt phiên bản | Đạt | `docling` ≠ 2.129.0 ⇒ `TsvPatchError` (một `ValueError` ⇒ job thất bại vĩnh viễn, không thử lại). Gói `docling` 2.129.0 ghim cứng `docling-slim[standard]==2.129.0`, nơi chứa mã thật |
| Chốt SHA-256 | Đạt | SHA của `inspect.getsource` hàm upstream = `e0623aa9…`; file cài đặt khớp hash trong `RECORD` của wheel, wheel ghim hash trong `uv.lock` ⇒ so AST của 12D7 là so với đúng upstream 2.129.0 |
| Idempotent, thread-safe | Đạt | 16 luồng × 50 lần `apply()`: một lớp bọc duy nhất, không lỗi |
| Multiprocessing / worker startup | Đạt | interpreter mới: chưa vá khi import; `build_ocr_options("rapidocr")` không vá; options Tesseract đầu tiên vá |
| Converter caching | Đạt | bản vá nằm trên lớp ⇒ model tạo **trước** `apply()` vẫn chạy phép đọc đã vá |
| Compat fingerprint | Đạt | `compat.source_fingerprint` đi qua `__cb5400_upstream__` nên luôn băm mã upstream |
| Fast / Best / Agri, Standard / Legal, PDF full-page / theo vùng | Đạt (đọc mã + test) | `build_ocr_options` là nơi **duy nhất** tạo `TesseractCliOcrOptions`; `docling_extract.py` gọi nó đúng một chỗ, cho cả PDF lẫn ảnh. Agri: chỉ kiểm đường mã, không có model |
| Đường mặc định content-core | Đạt | đường này dùng Auto OCR của Docling, không bao giờ chọn Tesseract; RapidOCR / EasyOCR không đi qua mã được vá |
| Bản vá chạy trong **tiến trình ingestion** | Đạt | worker → `extract_with_selected_ocr` → `convert_file` → `build_converter` → `build_ocr_options` → `apply()` trong chính tiến trình chuyển đổi; probe readiness và engine test dùng cùng `convert_file` |
| Đường lỗi | Đạt | không vá được ⇒ `build_ocr_options` ném lỗi **trước** khi tạo options: không có đường nào chạy Tesseract chưa vá; `OCR_ALLOW_UNVERIFIED_DEPENDENCIES` không bỏ qua chốt; readiness chạy đường thật trong tiến trình con nên không PASS giả |
| Offline readiness | Đạt (đọc mã + test có sẵn) | `inventory` áp bản vá bằng Docling của image; không áp được ⇒ gói `NOT_READY` |

**Phản ví dụ đã thử** (từng token một mình trong vùng — trường hợp pandas đổi kiểu — và trong dòng hỗn hợp, với `\n`
và `\r\n`): `1.` `123.` `2024.` `9.` `12.50` `NA` `N/A` `NULL` `NaN` `true` `false` `True` `FALSE` `0001` `000123`
`1e5` `inf` `-inf` `Infinity` `+5` `-5` `.5` `5.` `0x1F` `1_000` `1,234` `１２３` `"` `"abc` `#` `\N` `1.0` `1e400`
`-0` `00` `9999999999999999999999` `None` `null` `n/a` `nan` `#N/A` `<NA>` `-1.#IND` `NaT` `…` `½` `12/2024/NĐ-CP`,
chữ tiếng Việt, ký tự tổ hợp. Tất cả giữ nguyên văn. Dòng trống / chỉ khoảng trắng bị lọc như upstream.

**So với TSV thô của chính lần gọi tạo ô OCR.** Test của 12D7 gọi Tesseract lần thứ hai để lấy "TSV thô". Test của
12D8 chặn `subprocess.run` bên trong hàm đã vá và so đúng `stdout` của lần gọi đó với các ô trả về: 9 vùng thật (chỉ
số, hỗn hợp, nhiều dòng) — ô = trường `text` thô, đúng thứ tự; mọi cột khác bằng kết quả phép parse upstream trên
cùng các byte đó. Cùng các byte của vùng `0001` qua phép parse upstream cho `1.0` ⇒ phép kiểm không rỗng. TSV đi qua
cổng hướng xoay giống từng byte với gọi thẳng Tesseract.

**Cột ngoài `text`.** Fuzz 2000 TSV (rác ở cột số, dòng thiếu trường): mọi cột khác `text` có cùng `dtype` và giá trị
với upstream; lỗi parse là cùng loại lỗi. Confidence bất thường được xử lý như upstream.

**Ghi nhận nhỏ:** D8-08 (P4) — TSV hỏng mà mọi dòng có trường thứ 13 (tab trong chữ, Tesseract không ghi): cột chỉ
mục ngầm được định kiểu khác upstream; cột và chữ vẫn như upstream. D8-10 (P4) — `ocr.cli status` không in trạng thái
bản vá.

**Chưa kiểm được ở Cloud:** 22 PDF thật, Tesseract Best với traineddata của ứng dụng, Agri v1 / v2, image thật.

### D8-03 — sau ô OCR, Docling vẫn đổi số hiệu (P1, có từ v1.2.0)

Bản vá bảo đảm *ô OCR = TSV thô*. Bước tiếp theo của Docling, `PageAssembleModel.sanitize_text`
(`page_assemble_model.py:115-153`), ghép các ô của một vùng layout và **bỏ dấu `-`** khi ô trước kết thúc bằng `-`
dính liền chữ / số và ô sau bắt đầu bằng chữ / số. Đây là quy tắc nối từ bị ngắt dòng của tiếng Anh; tiếng Việt không
ngắt từ bằng gạch nối, nên gần như mọi `-` cuối dòng là ký tự thật của số hiệu, khoảng năm, địa danh.

Tái hiện bằng Tesseract thật → stage OCR thật của Docling (đã vá) → `LayoutPostprocessor` thật → `PageAssembleModel`
thật (`test_control_real_ocr_cells_are_raw_but_element_text_loses_hyphens`):

| TSV thô = ô OCR | Chữ của phần tử (đi vào `full_text`) |
|---|---|
| `05/2024/TT-` `BNNPTNT` (ngắt dòng) | `05/2024/TTBNNPTNT` |
| `2021-` `2025` (ngắt dòng, hoặc `2021- 2025` giữa dòng) | `20212025` |
| `0001-` `0002.` | `00010002.` |
| `VT-` `KHTC;` (giữa dòng) | `VTKHTC;` |
| `1-` `Điều` `5.` (giữa dòng) | `1Điều 5.` |

- Trường hợp ngắt dòng xảy ra với **mọi engine** và cả lớp chữ PDF (mỗi ô là một dòng). Trường hợp giữa dòng chỉ với
  Tesseract (mỗi ô là một từ).
- Giống nhau ở v1.2.0 và ứng viên (`uv.lock` không đổi) ⇒ **không phải hồi quy**, nhưng cùng loại với E0-07 (Docling
  đổi chữ Tesseract đã đọc đúng) và E0-07 đã được xếp P1. Đây chính là loại finding mục W-12D7-02d dự liệu.
- `sanitize_text` còn đổi `“ ” ‘ ’` thành nháy thẳng, `•` thành `·`, `⁄` thành `/`.
- Không sửa trong review này. Hướng sửa và quyết định cần có: [PHASE12D8_RELEASE_BLOCKERS.md](PHASE12D8_RELEASE_BLOCKERS.md).

## 3. Ưu tiên 2 — Legal normalizer 1.3.0: PARTIAL

Mã: `open_notebook/ocr/legal_normalizer.py`. Test: `tests/review_phase12d8/test_legal_d8.py` (12 đạt, 5 xfail).
Tài liệu được dựng bằng `ReadingOrderModel` **thật** của Docling, với kích thước trang theo từng trang.

| Yêu cầu | Kết quả |
|---|---|
| Không còn phép nối liên trang do Legal tạo | **Đạt.** Không còn nhánh nào ghép chữ; danh sách `joined` luôn rỗng |
| Tách phép nối của Docling | **Đạt một phần.** Mọi phép nối có charspan khớp đều được tách (liên trang: luôn luôn; cùng trang: `_pair_refusal` luôn từ chối cặp cùng trang nên cũng luôn tách). Vị trí chèn lại sai trong D8-01 |
| Không xóa số khoản, số hiệu, số tiền | **Đạt ở tầng Legal** (số trong thân, bảng, ảnh giữ nguyên; bảng dùng `disable_numparse=True`). Số trang chỉ bị bỏ khi đủ bằng chứng trên ≥ 3 trang. D8-03 xảy ra trước Legal |
| Không tự tạo nội dung | **Đạt.** Fuzz 500 tài liệu: tập từ của Legal = tập từ của các item |
| Không đảo thứ tự đọc | **Không đạt — D8-01** |
| Bảo toàn bảng, marker | **Đạt** |
| Nội dung trong furniture | **Đạt** (chữ header / footer xuất hiện một lần được đưa vào thân); furniture lặp ≥ 2 trang hoặc là số trang hợp lệ thì bỏ như Standard |
| Ảnh / caption | **Đạt** (chữ trong ảnh nhỏ và caption được giữ); **footnote gắn vào bảng / ảnh mất — D8-02** |
| Cảnh báo chính xác | **Đạt một phần.** `upstream_merge_undone` nói các phần "được hiển thị tách ra" nhưng không nói vị trí chưa được kiểm |
| Lưu metadata, fallback Standard | **Đạt** (normalizer lỗi ⇒ bản xuất Standard + `status: failed`) |
| Charspan thiếu / chồng lấn / vượt độ dài / âm / đảo, Unicode, nhiều provenance | **Đạt.** Không ngoại lệ, không mất hay thêm chữ, tài liệu vào không đổi, chạy lần hai không đổi gì |
| Hai văn bản độc lập, tiêu đề chạy, khoản mất marker | **Đạt** (không nối; Docling nối "…quy định" với "Điều 5…" ở trang sau, Legal tách lại đúng) |

### D8-01 — đảo thứ tự đọc khi tách (P2)

`_split_item` (dòng 1480-1562) chèn phần tách ra bằng cách đi qua mọi anh em có `(trang, top)` nhỏ hơn nó — kể cả
đoạn văn và tiêu đề. Bbox của phần ở trang sau do Docling ghi bằng chiều cao của **trang đầu**
(`readingorder_model.py:657-670`), nên `top` lệch đúng bằng hiệu chiều cao hai trang.

| Tình huống | Legal 1.3.0 lưu |
|---|---|
| Hai trang 595 × 842 (cả 92 fixture) | đúng thứ tự |
| Trang 1 cao 820 pt, trang 2 cao 842 pt | `…theo quy định` / `Điều 6. Hiệu lực thi hành` / **`của pháp luật hiện hành…`** / `Thông tư này có hiệu lực…` |
| Trang 1 ngang (842 × 595), trang 2 dọc | phần nối nằm sau cả `Điều 6` và nội dung của nó |
| Trang 2 hai cột, cột phải cao hơn 2 pt | `Điều 6…` (cột phải) đứng trước phần nối (cột trái) |

Không mất chữ. Standard trong cùng tình huống giữ đúng thứ tự (nhưng ghép sai thành một đoạn). Normalizer 1.2.0 của
`904c15c` cho cùng kết quả ⇒ lỗi có từ 12D5; 12D7 làm nó lộ rộng hơn vì giờ **mọi** phép nối liên trang đều được tách
và chèn lại. Cả 92 fixture dùng trang 595 × 842 nên benchmark không thấy.

### D8-02 — footnote gắn vào bảng / ảnh bị mất (P2, có từ v1.2.0)

Docling gắn phần tử `FOOTNOTE` đứng ngay sau bảng / ảnh vào item đó. Serializer Markdown của docling-core 2.96.0
không xuất footnote của bảng / ảnh. Kết quả: `(1) Theo Thông tư số 15/2024/TT-BNNPTNT ngày 01/02/2024.` dưới một bảng
có trong `doc.texts` nhưng không có trong Standard, không có trong Legal, và Legal không cảnh báo. Footnote không gắn
vào bảng / ảnh được giữ. Fixture `f13_footnotes` chỉ có trường hợp sau.

### Rủi ro còn lại (đã có cảnh báo, không phải finding mới)

- **Nối liên trang còn tồn tại khi Docling bỏ gạch nối mà không có bằng chứng.** `…xuyên-` + `biên giới…` ở trang
  sau: không có chữ phần tử trước khi ghép thì Legal để nguyên một đoạn `…xuyênbiên giới…` và cảnh báo
  `upstream_dehyphenation`; có bằng chứng thì tách và khôi phục `-`
  (`test_control_residual_a_removed_hyphen_without_evidence_stays_joined`). Cảnh báo không phải là đã sửa nội dung.
- Charspan không khớp ⇒ giữ phép nối, cảnh báo `upstream_merge_kept` (không xảy ra với Docling 2.129.0 theo mã đã đọc).
- `<` mở thẻ HTML được lưu thành `&lt;`, `#` / `>` đầu dòng thành `\#` / `\>` (quyết định F-17 của 12D5).
- Header / footer lặp ≥ 2 trang (kể cả số hiệu văn bản in ở đầu mỗi trang) bị bỏ như Standard.

## 4. Ưu tiên 3 — Oracle và Standard expected-diff: PARTIAL

### Oracle 92 fixture

Chạy lại benchmark trên HEAD: 92 dòng và hai bảng tổng hợp giống hệt `phase12d7/benchmark_legal_1_3_0.json` (trừ
thời gian / bộ nhớ). Ground truth khai báo độc lập (module fixture chỉ import `typing`; oracle không import
normalizer); đơn vị được khóa theo trang + bbox, so chữ theo item, đếm số lần xuất hiện, thứ tự theo LIS.

Negative control độc lập trên đầu ra 1.3.0 thật của cả 92 fixture — oracle **bắt được**: xóa một bản của dòng lặp
(95/101; 6 lần sót đều là artifact tùy chọn), xóa khối bất kỳ (619/644; 25 lần sót đều là đơn vị tùy chọn), đổi chữ
số `Điều 12`→`13` (489/489), bỏ số 0 đầu (31/31), bỏ dấu chấm cuối (295/295), bỏ / bịa marker, nhân đôi khối
(643/644), đổi chữ cùng độ dài, bỏ ô / hàng bảng, bỏ placeholder ảnh, ghép hai đoạn kể cả qua trang (527/527), chèn
đoạn bịa (644/644), NFC→NFD, đổi trang / bbox / provenance của item.

Điểm mù (đều P3, không chặn phát hành): D8-ORC-01 hàng bảng không được so chữ ở chế độ identity; D8-ORC-02 khối code
vô hình; D8-ORC-03 chữ artifact đã bỏ có thể chèn lại chỗ khác; D8-ORC-04 cấu trúc khối không được đo; D8-ORC-05 đảo
thứ tự bão hòa ở fixture Docling vốn đã đảo; D8-ORC-06 nối liên trang của cặp `gt="join"` không bị tính lỗi dù 12D7
cấm. Thêm hai điểm mù do review này tìm ra: không fixture nào có trang khác kích thước (D8-01) hay footnote dưới bảng
(D8-02).

### Standard expected-diff (`scripts/ocr/phase12_standard_diff.py`)

Trên trang tổng hợp qua stage OCR thật, khác biệt Standard chỉ ở đúng token parser cũ làm sai (test 12D7 đạt, chạy
lại). RapidOCR / EasyOCR: mã cấu hình không đổi từ v1.2.0; `apply()` chỉ nằm trong nhánh Tesseract (kiểm bằng AST).
Phân loại theo từng hunk, không miễn trừ cả tài liệu: `1.0 Điều 5` → `0001 Điều 6` cho [expected, unexpected], rc 1.
Khác biệt do cổng hướng xoay không có lớp chấp nhận ⇒ `unexpected` (thận trọng, đúng).

Nhưng công cụ **chưa dùng được làm cổng** cho W-12D7-02e:

| Mã | Lỗ hổng | Ví dụ đã chạy |
|---|---|---|
| D8-STD-01 | So trên `text.split()`; `byte_identical` chỉ ghi vào JSON | gộp hai đoạn thành một, bảng dồn một dòng, space→NBSP: `unchanged`, rc 0 |
| D8-STD-02 | Bằng chứng TSV là tập từ của cả tài liệu, không theo vùng OCR, không đếm | vùng `0001`: v1.2.0 in `1.0`, ứng viên in `1` (vẫn mất số 0) ⇒ `expected parser fix` vì số trang `1` có ở vùng khác |
| D8-STD-04 | Chỉ `unexpected` làm rc ≠ 0 | tài liệu thiếu ở bản ứng viên, hoặc không có file nào: rc 0 |
| D8-STD-03 | Quy trình không tạo được bằng chứng | `diagnose` ghi `01_tesseract_pNNN.tsv` (Direct OCR toàn trang), công cụ tìm `<tên>*.tsv` của từng crop; `qd1` nhận TSV của `qd10` |

Hệ quả: với 22 PDF thật, sửa thật sẽ ra `not verified` (không có TSV khớp) và công cụ vẫn thoát 0; một hồi quy về
xuống dòng sẽ ra `unchanged`. Direct OCR toàn trang và OCR theo vùng **không phải cùng một lần gọi** — đúng lưu ý của
đề bài; bằng chứng phải là TSV thô của chính lần gọi tạo ô OCR.

## 5. Ưu tiên 4 — Cổng hướng xoay: gate đạt; nguyên nhân E1-05 chưa có bằng chứng

Test: `tests/review_phase12d8/test_orientation_gate_d8.py` (20 đạt, 8 xfail).

| Hạng mục | Kết quả |
|---|---|
| LF / shebang / quyền chạy | blob LF, mode 100755, `#!/usr/bin/env python3`; `.gitattributes` ép LF cho cổng và `*.sh` |
| Docker build fail khi cổng hỏng | **Đạt (mô phỏng, không build thật).** Cổng CRLF chạy trực tiếp: rc 127; không có bit chạy: rc 126; bước `RUN` là chuỗi `&&` thuần, tự kiểm ở cuối, nằm trong `runtime-base`, không `COPY` nào ghi đè sau đó. Phát lại cả bước trên bản CRLF 0644 cho ra file giống blob git |
| Logic cổng | byte-giống v1.2.0; ngưỡng **2.0 không đổi**; đúng 2.00 giữ, 1.99 chặn; `nan` / `inf` / âm / dấu phẩy thập phân / thiếu dòng confidence ⇒ coi là thẳng; treo ⇒ kill, rc 124 |
| Chuyển tiếp | stdout / stderr / mã thoát giống gọi thẳng với `--psm` khác 0, `--tessdata-dir`, `-l vie+eng`, đường dẫn Unicode có dấu cách, file thiếu |
| Tương tác với E0-07 | bản vá chỉ thay `_run_tesseract`; `_perform_osd` vẫn của upstream và đi qua cổng |
| Đầu-cuối trên mã OSD của Docling | tiêu đề ba dòng thẳng: OSD thô `180` conf ≈ 0.1 ⇒ không cổng: 180; qua cổng: 0, chữ đọc đúng; cổng CRLF: lại 180 (cơ chế E1-05) |
| Tìm góc sai có conf ≥ 2.0 | 864 vùng thẳng tổng hợp: 28 góc sai đều < 2.0, **0** góc sai ≥ 2.0 ⇒ không có căn cứ để đổi ngưỡng |
| Fallback | cổng không chạy được ⇒ Tesseract không cổng + một WARNING; `status` dạng chữ báo `NOT ACTIVE` (thực sự chạy thử cổng). Readiness, `status --json`, metadata chuyển đổi không phản ánh (D8-ORI-02, P3) |

**Phân biệt bắt buộc:** đã chứng minh *lỗi CRLF được sửa và build sẽ thất bại nếu cổng không khởi động*. **Chưa**
chứng minh *CRLF là nguyên nhân của 11 vùng nghi ngờ trên Windows* — cần image cũ có `\r` **và** từng vùng có OSD thô
< 2.0. Mục W-12D7-01a hiện ghi "nguyên nhân E1-05 xác nhận" chỉ từ vế đầu (D8-ORI-04). `DECISIONS.md` D-40 và
`PHASE12D7_FINDING_STATUS.json` giữ đúng sự phân biệt này.

- **D8-ORI-01 (P2):** công cụ `phase12_orientation_diagnose.py` xoay vùng 90° / 270° ngược chiều với Docling
  (`rotated_copy` dùng góc thô; Docling đổi thành `(-deg) % 360` trước). Vùng nằm ngang đọc đúng ở ingestion bị công
  cụ báo oan; trường hợp ngược lại bị bỏ sót. Ingestion không ảnh hưởng; 180° (triệu chứng E1-05) được xử lý đúng.
- **D8-ORI-03 (P3):** `.gitattributes` không sửa checkout Windows đã có — sau `pull` file cổng vẫn `w/crlf` (blob
  không đổi nên Git không ghi lại). Chỉ bước `sed` trong Dockerfile bảo vệ, và nó hoạt động. W-12D7-00c sẽ thấy
  `w/crlf` sau pull: đó là bình thường.

## 6. Ưu tiên 5 — Gói offline: PARTIAL; updater tự động: EXPERIMENTAL

Test: `tests/review_phase12d8/test_offline_d8.py` (15 đạt, 15 xfail).

**Khóa đa nền tảng (E1-04).** Nhánh `flock` kiểm bằng tiến trình thật: tiến trình thứ hai bị từ chối với PID của
người giữ; file khóa không bị truncate, không đổi inode; `kill -9` người giữ ⇒ lấy lại được ngay; fd không bị kế
thừa; không chỗ nào xóa file khóa. Nhánh `msvcrt` **chỉ mô phỏng**: dùng `LK_NBLCK`, khóa đúng 1 byte ở offset 2³⁰,
tách khỏi chữ PID ở offset 0. Đây không phải bằng chứng Windows.

**Đầu ra nguyên tử.** Ba lần `os.replace` đều trong `--out`. Hai cửa sổ còn hở (P3): build lỗi *sau* khi đổi tên gói
làm mất cặp gói + hash cũ (D8-OFF-03); kill giữa "cất `.sha256` cũ" và "đổi tên gói" để gói cũ mất hash (D8-OFF-04).
Cả hai thất bại an toàn (gói không có hash không được chấp nhận).

**Tin cậy.** `verify` từ chối gói chưa ký chỉ có sidecar, không giải nén gì; quét archive trước khi ghi; image nhận
diện theo ID / config digest; nhãn revision phải bằng commit. Đường chữ ký chạy được sau khi cài `ssh-keygen` (384
test đạt). Tài liệu nói thật rằng `.sha256` đi kèm không phải kênh tin cậy.

**Quy trình thủ công (đường production ưu tiên).**

| Yêu cầu | Kết quả |
|---|---|
| Xác thực trước khi giải nén / chạy | Đạt: §3.1 so SHA-256 từ kênh tin cậy **trước** `tar -x`; lật một byte bị từ chối |
| Backup mới sau khi dừng ghi, kiểm restore | Đạt theo văn bản: maintenance → job = 0 → F1 → backup + thử restore → F2, trước khi chuyển tag |
| Không pull / build / recreate DB | Đạt: mọi lệnh Compose là `ps -q`, `logs --tail`, hoặc một lần recreate `--no-deps --no-build --pull never --force-recreate "$APP"`; không có `down`, `pull`, `build`, `-v`, `prune` |
| Tag triển khai, pin image, tag rollback | Đạt: tag rollback được tạo trước khi chuyển |
| Rollback đúng image và commit | **Thứ tự sai (D8-OFF-10):** app được lùi và mở lại trước khi mã nguồn được đưa về |
| Boot guard, tokenizer offline, artifact OCR | Có trong quy trình; chưa chạy với Docker thật |

Bảy điểm P3 nên sửa trong tài liệu: D8-OFF-05 (payload không ràng buộc với manifest đã ký), D8-OFF-07 (thư mục làm
việc đoán trước được), D8-OFF-08 và D8-OFF-14 (phép so dữ liệu bỏ sót / đạt khi không đọc được dữ liệu), D8-OFF-10,
D8-OFF-13 (lệnh `python -c` nhiều dòng bị thụt lề ⇒ `IndentationError` khi chép từ file `.md` thô — bước bắt buộc
"chờ job nền"), D8-OFF-15 (`--no-deps` là tùy chọn trong hợp đồng adapter).

**Updater tự động.** Năm tài liệu triển khai ghi rõ **EXPERIMENTAL / NOT READY**, và quy trình thủ công không gọi
`update` / `finish` / `rollback` / `preflight`. Makefile và README không nhắc tới updater. Nhưng chính công cụ
(`--help`, wrapper `.sh`) không có nhãn nào (D8-OFF-01), và release notes 1.3.0-rc.1 vẫn trình bày updater như đường
nâng cấp offline (D8-OFF-02). State machine của updater **không** được review lại (theo đề bài).

**PowerShell (chỉ đọc mã).** Lời gọi Compose đã dùng mảng tường minh (E0-05); script thuần ASCII, không BOM, không
`2>&1`. D8-OFF-11: `build-package.ps1` hỏng khi có Python mà không có `uv`. D8-OFF-12: `phase12-test.ps1` còn
`2>$null` ở hai lệnh native.

## 7. Kiểm thử

| Bộ | Kết quả 12D8 | So với báo cáo 12D7 |
|---|---|---|
| Backend `tests/` (trừ `test_chunking.py`, `review_phase12d8`) | 3010 passed / 11 failed / 78 skipped / 1 error | 10 lỗi **cùng tên**: 9 × `test_models_api.py::TestModelsProviderAvailability` (mock nhận 1 tham số, mã gọi 2), `test_domain.py::TestContentSettings::test_content_settings_defaults` |
| Lỗi thứ 11 và 1 error | do môi trường: `test_ocr_engine_manager.py::TestLifecycle::test_assert_ready_raises_value_error` (EasyOCR chưa cài) và `test_forged_verify_report_does_not_replace_authentication` (thiếu `ssh-keygen`) | sau khi cài cả hai: 5 file liên quan **384 passed**, 0 skip |
| `tests/test_chunking.py` | 31 đạt; 3 test treo chờ tải bảng mã | đúng 3 test bị deselect: `TestChunkText::test_cjk_text_is_chunked_by_tokens`, `::test_explicit_content_type_plain`, `::test_secondary_chunking_for_large_sections` |
| Quy đổi | 3048 passed / 10 failed / 73 skipped / 3 không chạy được | khớp 3047 / 10 / 73 / 3 (+1 test thêm ở `dde8645`) |
| Review 12D2, 12D4; test 12D7 | đạt (trong lượt chạy toàn bộ) | như báo cáo |
| Benchmark 92 fixture | giống hệt file đã commit | như báo cáo |
| Frontend | **438 / 438**, `tsc` sạch, lint 0 lỗi / 7 cảnh báo cũ | như báo cáo (lượt đầu 1 test quá 30 s vì máy đang tải nặng; chạy lại đạt) |
| `tests/review_phase12d8/` | 204 passed / 71 xfailed (strict) / 0 failed | mới |

Không chạy: Docker thật (`CB5400_REAL_DOCKER`), bảng mã `o200k_base` thật, pipeline OCR đầy đủ, Windows / PowerShell.

## 8. Trạng thái 51 finding cũ và E0 / E1

Chi tiết từng finding: [PHASE12D8_FINDING_STATUS.json](PHASE12D8_FINDING_STATUS.json).

| | Số lượng |
|---|---|
| Sửa trong mã | 51 / 51 |
| Đã kiểm ở Cloud (test hồi quy đạt trong lượt chạy 12D8) | 51 / 51; trong đó 24 không còn mục Local |
| Còn mục Local mở | 27 |
| Đã kiểm trên Windows / runtime thật | **0** — không có bằng chứng Windows nào trong repo |

Review này chạy lại toàn bộ test hồi quy của 51 finding, không dựng lại riêng từng finding. E0-07: đã kiểm lại độc
lập, PASS. E1-09: đã sửa phép nối, phát sinh D8-01. E1-04, E0-05: sửa trong mã, chưa chạy trên Windows. E1-05: cần
bằng chứng Local. E1-01, E1-02, E1-06: không có báo cáo nguồn.

## 9. FINAL VERDICT

```
INDEPENDENT REVIEW: PARTIAL
  (review đầy đủ đã thực hiện; reviewer cùng họ model với bên phát triển, không phải Codex;
   không có Windows / Docker / model layout)
E0-07 PATCH: PASS
LEGAL CONTENT PRESERVATION: PARTIAL
STANDARD EXPECTED-DIFF: PARTIAL
OFFLINE MANUAL FALLBACK: PARTIAL
AUTOMATIC UPDATER: EXPERIMENTAL
NEW P0/P1/P2/P3/P4: 0 / 1 / 11 / 20 / 5
CODE RELEASE BLOCKERS: 3 (D8-03, D8-01, D8-02)
LOCAL ACCEPTANCE GATES: G-01 … G-12 (PHASE12D8_LOCAL_GATE_CHECKLIST.md)
READY FOR FINAL LOCAL ACCEPTANCE: CONDITIONAL
  (sau khi D8-01 được sửa, D8-02 / D8-03 được sửa hoặc chủ dự án chấp nhận bằng văn bản,
   và công cụ standard-diff dùng được làm cổng; các lượt thu bằng chứng Local không phụ thuộc
   những điểm đó có thể chạy ngay)
READY FOR RELEASE: NO
READY FOR PRODUCTION: NO
RUNTIME CODE UNCHANGED
PRODUCTION UNCHANGED
```
