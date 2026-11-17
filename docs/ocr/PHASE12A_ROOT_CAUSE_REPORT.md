# Phase 12A — Phân tích nguyên nhân gốc: artifact bố cục khi OCR văn bản pháp lý

Phiên bản cơ sở: **v1.2.0** (`f2fdf2714a7c0b5b196132f71cfc091928befc06`). Môi trường phân tích: Claude Code Cloud
(không có model Agri, không có tài liệu nội bộ, không tải được trọng số Docling từ Hugging Face — xem §6).

## 1. Tóm tắt

| Hiện tượng | Tầng gây lỗi | Bằng chứng | Mức xác minh |
|---|---|---|---|
| `<!-- image -->` xuất hiện trong nội dung | **G** serializer Markdown (`image_placeholder` mặc định) + **I** frontend hiển thị HTML comment thành chữ | mã nguồn docling-core 2.96.0, test thực thi | VERIFIED (code + test) |
| Chữ ký, con dấu sinh placeholder | **D** Layout gán nhãn PICTURE → **G** | như trên | VERIFIED (đường mã) / chất lượng Heron trên tài liệu thật: cần Local |
| Số trang lọt vào giữa câu | **D** Layout gán nhãn TEXT thay vì PAGE_FOOTER → không vào lớp furniture | ReadingOrderModel thật tái hiện đúng | VERIFIED (cơ chế); tần suất thật: cần Local |
| Câu bị ngắt khi qua trang | **E/F** cơ chế ghép liên trang của Docling chỉ khớp chữ ASCII, chỉ TEXT→TEXT, bị chặn bởi số trang | `reading_order_rb.predict_merges`, test thực thi | VERIFIED |
| Mất số khoản/điểm, đánh lại số | **G** serializer chèn số vị trí khi marker không nhận ra (`đ)`, `a.1)`); **I** CommonMark/trình duyệt đánh lại số danh sách | test thực thi + vitest | VERIFIED |
| Danh sách pháp lý thành danh sách Markdown thường | **F/G** `ListItem` + serializer dùng cú pháp danh sách Markdown | như trên | VERIFIED |
| Thiếu từ cuối trang | **C/D** (ô OCR ngoài vùng cluster) **hoặc** A (Tesseract) — **chưa xác định được trên Cloud**; một nguyên nhân khác đã xác minh: chữ OCR nằm *trong* vùng PICTURE bị serializer bỏ (`traverse_pictures=False`) | diagnostic harness so sánh từng tầng | PARTIAL — cần chạy `phase12_compare.py` trên Local |
| Thứ tự đọc sai | **E** ReadingOrderPredictor (rule-based) | tái hiện với bố cục 2×2 tổng hợp | PARTIAL (cơ chế), chưa đo tài liệu thật |
| Cấu trúc Phần/Chương/Mục/Điều/Khoản/Điểm không bảo toàn | tổng hợp các nguyên nhân trên | 24 fixture tổng hợp | VERIFIED trên fixture |

Không có bằng chứng lỗi nào nằm ở model Agri hay ở Tesseract cho các hiện tượng **cấu trúc**: chúng xảy ra sau OCR,
với bất kỳ engine nào, kể cả khi văn bản nhận dạng đúng 100%.

## 2. Cách điều tra

1. Đọc mã nguồn **đúng phiên bản đã khóa** trong `uv.lock`: docling 2.129.0, docling-core 2.96.0,
   docling-ibm-models 4.0.3, content-core 2.0.7 (đã cài và kiểm tra bằng `importlib.metadata`).
2. Đọc mã ChatBot5400: `open_notebook/ocr/docling_extract.py`, `options.py`, `pdf_prep.py`, `tesseract_gate.py`,
   `graphs/source.py`, `domain/notebook.py` (`Source.vectorize`), frontend `markdown-renderer.tsx`,
   `SourceDetailContent.tsx`, `globals.css` (`.source-prose`).
3. **Harness tái hiện** (`tests/legal_harness.py`): Docling không cho phép tải trọng số Layout Heron trên Cloud, nhưng
   mọi bước *sau* layout là Python thuần. Harness đưa các phần tử bố cục tổng hợp (nhãn, chữ, bbox) vào
   **`ReadingOrderModel` thật của Docling** → nhận `DoclingDocument` giống hệt cái pipeline production tạo ra từ bố cục
   đó (thứ tự đọc, nhận dạng marker danh sách, ghép liên trang của Docling, caption/footnote, lớp furniture).
4. **Công cụ chẩn đoán từng tầng** cho tài liệu thật trên máy cục bộ: `scripts/ocr/phase12_diagnose.py` (chi tiết §5).

## 3. Nguyên nhân theo từng hiện tượng

### 3.1 `<!-- image -->` (tầng G + I)

- `DoclingDocument.export_to_markdown(image_placeholder="<!-- image -->", image_mode=PLACEHOLDER)` — đây là **giá trị
  mặc định** (docling-core `document.py`, dòng ~3752). `MarkdownPictureSerializer._serialize_image_part` trả về đúng
  chuỗi này cho **mọi** `PictureItem` (logo, chữ ký, con dấu, hình trang trí).
- content-core (`extract_docling`) và lớp `docling_extract.convert_file` của ChatBot5400 đều gọi
  `export_to_markdown()` không tham số ⇒ mọi ảnh thành một dòng `<!-- image -->`.
- Frontend: `react-markdown` 10 không dùng `rehype-raw` ⇒ HTML comment được **hiển thị nguyên văn** thay vì ẩn
  (test `markdown-renderer.test.tsx`: "shows a Docling image placeholder as literal text"). Đây là lý do người dùng
  *thấy* chuỗi này; về an toàn đây là hành vi đúng (không render HTML thô) nên **không** sửa ở frontend.
- Chuỗi literal `<!-- image -->` có trong *nội dung* văn bản được serializer escape thành `&lt;!-- image --&gt;` ⇒
  phân biệt được với placeholder thật (fixture f18).

### 3.2 Số trang lọt vào nội dung (tầng D)

- `ReadingOrderModel._handle_text_element` chỉ đưa `PAGE_HEADER` / `PAGE_FOOTER` vào lớp `FURNITURE`; Markdown chỉ
  xuất lớp `BODY` (`DEFAULT_CONTENT_LAYERS = {BODY}`). Số trang mà Layout Heron gán nhãn **TEXT** (thường gặp với số
  đứng một mình ở chân trang scan) đi thẳng vào nội dung.
- Tái hiện: fixture f02 — `6` (TEXT) nằm giữa khoản 9 và phần tiếp theo; cùng số trang gán đúng `PAGE_FOOTER`
  (fixture f24) thì không xuất hiện ⇒ khẳng định nguyên nhân là **nhãn**, không phải serializer.

### 3.3 Câu bị ngắt khi qua trang (tầng E/F)

Docling **có** cơ chế ghép đoạn liên trang (`ReadingOrderPredictor.predict_merges`, `reading_order_rb.py` dòng 198)
nhưng với điều kiện:

| Điều kiện của Docling | Hệ quả với tiếng Việt / văn bản pháp lý |
|---|---|
| đoạn trước kết thúc bằng `[a-z,\-­]` | "thay đổi **số**" kết thúc bằng `ố` (U+1ED1) ⇒ **không ghép** |
| đoạn sau bắt đầu bằng `[a-zA-ZÀ-ɏ]` | "**ả**nh hưởng" (U+1EA3, Latin Extended Additional) ⇒ không ghép |
| chỉ nhãn TEXT với TEXT | khoản `9.` là LIST_ITEM, phần tiếp theo là TEXT ⇒ không ghép |
| chỉ bỏ qua PAGE_HEADER/FOOTER/TABLE/PICTURE/CAPTION/FOOTNOTE ở giữa | số trang nhãn TEXT chen giữa ⇒ không ghép |

Kết quả đo bằng mã thật (`predict_merges`): ví dụ ASCII → `{0: [1]}` (ghép); "thay đổi số" + "dư trên" → `{}`;
có số trang ở giữa → `{}`; LIST_ITEM + TEXT → `{}`.

### 3.4 Mất / đánh lại số khoản, điểm (tầng G + I)

- `ListItemMarkerProcessor` (docling 2.129) nhận diện `9.`, `a)`, `1.1`, `II.`, `-`; **không** nhận `đ)` (chỉ
  `[a-z]` ASCII) và `a.1)`. Khi marker rỗng, `MarkdownTextSerializer` (chế độ AUTO) **chèn số theo vị trí trong
  nhóm**: danh sách `a) b) c) d) đ)` xuất ra `5. đ) …`; danh sách đa cấp 12 mục xuất `10. đ)`, `11. a.1)`.
- Mục có marker hợp lệ được viết bằng cú pháp danh sách Markdown (`9. …`, `- a) …`). CommonMark chỉ giữ **số đầu
  tiên** của một danh sách; trình duyệt đánh số tiếp 1 đơn vị: nguồn `5. / 7. / 13.` hiển thị **5, 6, 7**
  (vitest "renumbers a standard ordered list"; harness: "6. Lưu trữ…" thay cho "7. Lưu trữ…").
- CSS `.source-prose ul { list-style: none }` (đã có từ trước) ẩn dấu đầu dòng ⇒ gạch đầu dòng gốc `-` của văn bản
  (layout gán TEXT, serializer xuất `- …`) **biến mất** khi hiển thị.

### 3.5 Thiếu từ cuối trang (chưa kết luận trên Cloud)

Ba khả năng, phân biệt được bằng diagnostic harness (§5) trên tài liệu thật:

1. **A — Tesseract** không đọc được từ (vùng mờ, sát mép): khi đó từ cũng thiếu ở `01_tesseract_pXXX.txt`.
2. **C/D — ô OCR nằm ngoài cluster** của Layout Heron: từ có ở `02_ocr_cells.json` nhưng không có trong
   `03_layout_clusters.json` / `04_assembled_elements.json`.
3. **F/G — chữ OCR nằm trong vùng PICTURE**: Docling đặt chữ OCR của vùng ảnh (con dấu, hoặc *cả trang* khi layout
   bao trang scan thành một PICTURE — tài liệu docling-core ghi rõ trường hợp full-page OCR) làm **con của
   PictureItem**; `export_to_markdown(traverse_pictures=False)` mặc định **bỏ toàn bộ** chữ này (đã xác minh: fixture
   f16, chuẩn chỉ còn `<!-- image -->`, mất cả "Điều 5…" và "1.100 đồng").

`12_summary.json` của diagnostic báo `page_end_words_in_standard` (từ cuối mỗi trang của OCR trực tiếp có còn trong
kết quả không) và `text_items_under_pictures_dropped_by_standard_export`.

### 3.6 Thứ tự đọc (tầng E)

Với bố cục hai cột gồm các khối thẳng hàng theo hàng (fixture f12, và biến thể khối cao), `ReadingOrderPredictor` đọc
**theo hàng** (trái1, phải1, trái2, phải2). Chưa đo trên PDF thật; Legal mode **không thay đổi thứ tự đọc** (yêu cầu
bảo toàn) nên lỗi này nằm ngoài phạm vi sửa của Phase 12 và được ghi lại là giới hạn.

### 3.7 Tầng H (ChatBot5400) và chunk/embedding

`save_source` lưu nguyên `extraction.content` vào `Source.full_text`; `embed_source` đọc lại chính trường này ⇒ nội
dung hiển thị và nội dung index là một. ChatBot5400 không xử lý thêm Markdown ⇒ không gây thêm lỗi; nhưng
**provenance (trang, bbox) không được lưu** cùng Source (không có trường) ⇒ không thể trích dẫn số trang chính xác.

## 4. Phạm vi sửa nhỏ nhất (đầu vào cho 12B)

1. Không đổi Docling, Heron, TableFormer, engine OCR, model, RAG, schema.
2. Một chế độ **opt-in** chạy trên **bản sao** `DoclingDocument` của PDF, trước khi lưu Source:
   bỏ placeholder không mang thông tin, chuyển số trang/header lặp (đủ bằng chứng) sang furniture, ghép đoạn liên
   trang theo quy tắc bảo thủ (Unicode-aware), xuất marker gốc dưới dạng chữ (escape để không bị đánh lại số), lấy
   chữ OCR nằm trong vùng ảnh.
3. Đường RapidOCR mặc định (content-core) không có `DoclingDocument` ⇒ khi bật Legal, PDF đi qua lớp Docling của
   ChatBot5400 (cùng options với content-core, đã có parity test).

## 5. Diagnostic harness (dùng trên Windows Local)

`scripts/ocr/phase12_diagnose.py <pdf> --engine <engine> --out <thư mục>` — một lần chuyển đổi Docling bằng **đúng
code production** (`docling_extract.convert_document`: pdf_prep, scale, gate Tesseract), rồi ghi:

| File | Tầng |
|---|---|
| `01_tesseract_pXXX.txt/.tsv` | A/B: Tesseract trực tiếp, cùng tessdata, cùng ngôn ngữ (cả Agri), cùng DPI như engine |
| `02_ocr_cells.json` | C: ô OCR/PDF Docling giữ (nếu phiên bản Docling còn giữ `parsed_page`; nếu không ghi `available: false`) |
| `03_layout_clusters.json` | D: cluster layout (nhãn, độ tin cậy, bbox, số ô, chữ) |
| `04_assembled_elements.json` | C/D: phần tử sau khi ghép ô |
| `05_docling_document.json` | F |
| `06_items.json` | E/F: thứ tự đọc, nhãn, lớp, marker, enumerated, provenance |
| `07_markdown_standard.md` / `08_markdown_legal.md` | G |
| `09_legal_report.json` | từng phép biến đổi, trước/sau, lý do |
| `10_display_*.txt` | I: những gì frontend hiển thị (CommonMark) |
| `11_source_full_text.md` | H: nội dung Source đã lưu (tùy chọn, chỉ API loopback) |
| `12_summary.json` | số từ ở từng tầng, tầng làm mất từ, từ cuối trang |

Diagnostic **không** nằm trong đường ingestion, tắt mặc định, không chạy OCR hai lần trong production, không gửi gì
ra ngoài; thư mục kết quả quyền 0700.

## 6. Giới hạn của phân tích trên Cloud

- `huggingface.co` bị chặn ⇒ **không chạy được Layout Heron / TableFormer** ⇒ không đo được tần suất mỗi lỗi trên
  PDF thật, không xác định được nguyên nhân "thiếu từ cuối trang" trên tài liệu của người dùng: **NOT VERIFIED**,
  chuyển sang Windows Local (`PHASE12E_WINDOWS_LOCAL_TEST_GUIDE.md`).
- Tesseract trên Cloud là 5.3.4 (Ubuntu) với `vie` của Ubuntu, khác Tesseract 5.5.0 + tessdata fast/best của
  production ⇒ số liệu nhận dạng chỉ mang tính tham khảo.
- Không có model Agri và tài liệu nội bộ (đúng yêu cầu).
