# Phase 12B — Thiết kế chuẩn hóa văn bản pháp lý sau OCR (Legal Document Normalization)

Quyết định: **D-34** ([DECISIONS.md](DECISIONS.md)). Nguyên nhân gốc: [PHASE12A_ROOT_CAUSE_REPORT.md](PHASE12A_ROOT_CAUSE_REPORT.md).
Module: `open_notebook/ocr/legal_normalizer.py` (phiên bản normalizer **`1.1.0`** từ Phase 12D3; tài liệu này được viết
cho `1.0.0`).

> **CẬP NHẬT (Phase 12D3, quyết định D-36).** Các quy tắc dưới đây đã thay đổi sau audit độc lập 12D2; khi phần
> thân tài liệu mâu thuẫn với bảng này thì **bảng này đúng**:
>
> | Chủ đề | v1.0.0 (mô tả trong tài liệu này) | v1.1.0 (hiện hành) |
> |---|---|---|
> | Dòng lặp ở đầu/cuối trang | chuyển furniture khi lặp ≥ 3 trang, ≥ 50% | **không bao giờ bỏ** theo tần suất; chỉ item layout gắn nhãn PAGE_HEADER/FOOTER; cảnh báo `repeated_line_kept` |
> | Số trang | cùng độ lệch trên ≥ 2 trang | ≥ 3 trang **và** ≥ 60% số trang, cùng dải, cùng vị trí ngang (hoặc lẻ-chẵn), ngoài mép thân, giá trị trong [trang−10, trang+50]; 1–2 trang: giữ + `page_number_kept` |
> | Nối qua trang | theo ký tự kết thúc + đầu trang sau | thêm: đoạn trước phải là đoạn thân bị cắt (bề rộng ≥ 85% cột, không trong dải cuối, không có footer bên dưới, không lặp ở trang sau), không footnote, cùng cột, không có bảng/ảnh/trang trắng ở giữa; marker `a.` `a/` `đ.` `(a)` `a.1)` là đơn vị mới; từ chối có lý do (`join_not_made`) |
> | Phần đã nối | `delete_items` | chuyển `ContentLayer.INVISIBLE` (tuyến tính) |
> | Ảnh không chữ | bỏ placeholder khi < 15% trang | bỏ (có ghi lại) chỉ khi < 4%; còn lại giữ + cảnh báo có trang/bbox |
> | Marker danh sách trong văn bản lưu | có ký tự thoát (`9\.`) | **không thoát**; frontend thoát lúc hiển thị (`legalDisplayMarkdown`) |
> | Bằng chứng chuẩn hóa | chỉ trong log | bản ghi trong `source.asset.extraction` + nhãn trên trang Source |
> | Giới hạn | số item | số item + ngân sách thời gian 30 s ⇒ fallback Standard, trạng thái `failed` |
>
> Kiểm thử: `tests/test_ocr_legal_normalizer.py`, `tests/review_phase12d2/`. Số liệu:
> [../review/PHASE12D3_QUALITY_BENCHMARK.md](../review/PHASE12D3_QUALITY_BENCHMARK.md).

## 1. Nguyên tắc

1. **Dựa trên cấu trúc của Docling**, không dựa trên chuỗi Markdown: mọi quyết định đọc `DocItem` (nhãn, lớp
   nội dung), `ListItem.marker`, provenance (trang, bbox), kích thước trang và thứ tự đọc của `DoclingDocument`.
   Regex chỉ dùng để *nhận diện hình dạng* một dòng đã được khoanh vùng bằng hình học (số trang) và để escape cú pháp
   Markdown ở đầu dòng.
2. **Không bao giờ sửa chữ nhận dạng**: không thêm từ, không sửa chính tả, không đổi 0/O, 1/l, dấu thập phân, đơn
   vị, không đánh lại số. Ký tự duy nhất có thể được thêm là **một dấu cách** khi ghép hai phần của một đoạn.
3. **Không đủ bằng chứng ⇒ giữ nguyên.** Thiếu bbox / kích thước trang / mẫu lặp ⇒ không xóa, không ghép.
4. **Thuần, xác định, lũy đẳng**: không mạng, không LLM, không đọc/ghi file hay database; cùng đầu vào cho cùng đầu
   ra; chạy lại trên kết quả không đổi gì.
5. **Opt-in, mặc định Standard**: Standard giữ nguyên **từng byte** kết quả v1.2.0.

## 2. Hai chế độ

| | Standard (mặc định) | Văn bản pháp lý (Legal) |
|---|---|---|
| Kết quả | `doc.export_to_markdown()` như v1.2.0 | Markdown do normalizer tạo từ cùng `DoclingDocument` |
| Áp dụng cho | mọi định dạng | **chỉ PDF** do Docling chuyển đổi, đầu ra Markdown |
| Không áp dụng | — | ảnh, Word, Excel, PowerPoint, HTML, Markdown, audio, YouTube, trang web, Docling không cài, `docling_output_format` html/json |

### Cách bật — hai lớp

1. **Cổng triển khai** `OCR_LEGAL_NORMALIZATION_ENABLED=true` (biến môi trường, mặc định **tắt**) — cùng kiểu với
   `OCR_AUTO_FULL_PAGE_ON_WATERMARK`. Tắt cổng = toàn hệ thống dùng Standard, bất kể lựa chọn đã lưu (rollback tức
   thời không cần database).
2. **Lựa chọn của quản trị viên** trong *Cài đặt → OCR Engine Manager → Chuẩn hóa văn bản sau OCR*: `Tiêu chuẩn` /
   `Văn bản pháp lý`. Lưu ở trường mới `ocr_text_normalization` của bản ghi `open_notebook:content_settings`
   (bảng **SCHEMALESS**, giá trị thiếu = Standard) ⇒ **không migration**. API `PUT /api/ocr/config` (đã
   `require_admin`) **từ chối** chọn Legal khi cổng đang tắt.

Hiệu lực = Legal **chỉ khi** cả hai đều bật (`legal_normalizer.effective_mode`). Giá trị được "đóng băng" vào
`OcrSettings.text_normalization` khi job bắt đầu (như engine OCR), nên đổi cài đặt giữa chừng không ảnh hưởng tài
liệu đang xử lý. Lựa chọn **theo từng tài liệu** chưa làm (cần đổi API tạo Source và form tải lên — ngoài phạm vi
nhỏ nhất); tài liệu đã xử lý **không** tự xử lý lại.

## 3. Kiến trúc

```
content_process (graphs/source.py)
  OcrSettings.from_content_settings  ──► text_normalization = effective_mode(setting)   [gate + setting]
  should_use_native_ocr(file)          ──► Legal + PDF ⇒ lớp Docling của ChatBot5400 (kể cả RapidOCR mặc định)
  extract_with_selected_ocr
    convert_file
      convert_document  (pdf_prep, D-33, build_converter: options = content-core + ocr_options)  ← không đổi
      Standard: doc.export_to_markdown()                                                         ← không đổi
      Legal:    legal_normalizer.normalize_or_fallback(doc)  → (content, metadata)
save_source: Source.full_text = content  → embed_source đọc lại full_text (chunk + embedding)   ← không đổi
```

**Vì sao RapidOCR mặc định cũng đi qua lớp Docling khi bật Legal**: content-core chỉ trả về chuỗi Markdown, không có
`DoclingDocument`. Lớp `docling_extract` dựng **đúng** `PdfPipelineOptions` của content-core, chỉ thêm
`ocr_options` (parity test `tests/test_ocr_docling_parity.py`). Khác biệt duy nhất so với đường content-core: bước
`pdf_prep` (sửa trang xoay, D-25) cũng chạy — đây là đường production đã dùng cho mọi cấu hình không mặc định.

## 4. API thực tế (đã kiểm tra trong docling-core 2.96.0 / docling 2.129.0)

| API | Dùng để |
|---|---|
| `DoclingDocument.model_copy(deep=True)` | làm việc trên bản sao; tài liệu gốc không đổi (test) |
| `iterate_items(with_groups=False, traverse_pictures=True, included_content_layers={BODY})` | thứ tự đọc của nội dung |
| `ProvenanceItem.page_no`, `.bbox.to_top_left_origin(page_height)`, `doc.pages[n].size` | hình học |
| `DocItem.content_layer = ContentLayer.FURNITURE` | "xóa" số trang / header lặp **theo cách của Docling** (vẫn còn trong tài liệu để truy vết) |
| `ListItem.marker`, `ListGroup.first_item_is_enumerated` | marker gốc, phát hiện số bị chèn |
| `DoclingDocument.delete_items(node_items=…)` | bỏ phần sau của đoạn đã ghép |
| `MarkdownDocSerializer(text_serializer=…, list_serializer=…, picture_serializer=…, params=MarkdownParams(…, traverse_pictures=True))` | serializer chính thức với 3 lớp con nhỏ |
| `MarkdownParams.orig_list_item_marker_mode=NEVER`, `ensure_valid_list_item_marker=False` | lấy phần chữ của ListItem, marker do ta viết |

## 5. Quy tắc

### 5.1 Placeholder ảnh

| Trường hợp | Kết quả |
|---|---|
| ảnh có **caption** | caption giữ, placeholder bỏ |
| ảnh có **chữ OCR bên trong** (con của PictureItem) | chữ được xuất (`traverse_pictures=True`), placeholder bỏ |
| ảnh không chữ, diện tích < 15% trang (chữ ký, con dấu, logo) | placeholder bỏ, ghi operation |
| ảnh không chữ, ≥ 15% trang (sơ đồ, biểu đồ, ảnh chụp, watermark được nhận là ảnh) | **giữ** placeholder + cảnh báo `picture_without_text` |
| ảnh không có provenance / kích thước trang | **giữ** placeholder (không đủ bằng chứng) |
| ảnh trong ô bảng (rich cell) | không đụng tới bảng |
| chuỗi literal `<!-- image -->` trong văn bản | được Docling escape (`&lt;!-- image --&gt;`), giữ nguyên |

PDF gốc, ảnh, biểu đồ có dữ liệu bảng (`PictureTabularChartData`), mô tả ảnh (nếu bật vision) không bị đụng tới.

### 5.2 Số trang và header/footer (chuyển sang furniture)

Số trang — **tất cả** điều kiện:
- `TextItem` nhãn TEXT / PAGE_HEADER / PAGE_FOOTER, một provenance, không nằm trong ảnh/bảng;
- chữ đúng một dạng: `6`, `- 6 -`, `Trang 6`, `Trang 6/12`, `Page 6 of 12`, `6/12` (≤ 20 ký tự);
- nằm trong dải 10% trên hoặc 10% dưới của trang, và **ngoài cùng** (không có phần tử nào nằm hẳn phía trên — với
  header — hoặc hẳn phía dưới — với footer);
- **mẫu lặp**: độ lệch `số in − số trang PDF` giống nhau trên **ít nhất hai trang khác nhau**, mỗi trang tối đa một
  ứng viên.
Một trang duy nhất, hai "số trang" trên một trang, số giữa trang (năm `2024`, số `15`), số điều/khoản, tiền, tỷ lệ
⇒ giữ nguyên (fixture f08, f22).

Header/footer lặp: cùng dải, ngoài cùng, ≤ 150 ký tự, chữ **giống hệt** (chỉ bỏ qua khoảng trắng và hoa/thường — chữ
số cũng phải giống), xuất hiện trên ≥ 3 trang và ≥ 50% số trang; không bắt đầu bằng Phần/Chương/Mục/Điều; không phải
tiêu đề (SectionHeader/Title) hay ListItem. (Phiên bản đầu dùng che chữ số và đã bị chính harness phát hiện xóa nhầm
"Nội dung trang 2 của quy định" — đã sửa, test hồi quy f14.)

Footnote (nhãn FOOTNOTE) không bao giờ là ứng viên.

### 5.3 Ghép đoạn liên trang

Phần A (cuối trang p) và phần B (đầu trang p+1) được ghép khi **mọi** điều kiện đúng:

1. A là đoạn văn (TEXT) hoặc ListItem; B là đoạn văn TEXT (hoặc ListItem *không marker* khi A là ListItem);
   không nằm trong ảnh/bảng;
2. B là phần tử thực tiếp theo của A trong thứ tự đọc; ở giữa chỉ có số trang/header đã loại hoặc ảnh không chữ đã
   bỏ placeholder; ảnh lớn được giữ, bảng, tiêu đề ⇒ không ghép;
3. trang của B = trang cuối của A + 1 (trang trắng ở giữa ⇒ không ghép);
4. có bbox và kích thước trang: A kết thúc ở nửa dưới trang, B bắt đầu ở nửa trên trang sau;
5. A chưa kết thúc câu: ký tự cuối là chữ/số (Unicode) hoặc dấu phẩy; kết thúc bằng `. : ; ! ? … ) ”` ⇒ không ghép;
   kết thúc bằng gạch nối ⇒ **không ghép**, cảnh báo `hyphen_at_page_break_not_joined` (tiếng Việt hiếm khi ngắt
   từ, gạch nối thường là dấu câu);
6. B bắt đầu bằng **chữ thường** (Unicode, gồm `đ`, `ư`, `ạ`…) và **không** mở đầu một đơn vị pháp lý: `a)`, `đ)`,
   `a.1)`, `i.`, `1.`, `1.1`, `2)`, gạch đầu dòng, "Điều/Khoản/Điểm/Chương/Mục/Phần …".

Ghép = `A.text + " " + B.text`, provenance của B nối vào A (giữ cả hai trang), B bị xóa khỏi bản sao. Có thể ghép
chuỗi qua nhiều trang (fixture f24). **Không** sửa từ bị tách, **không** thêm từ thiếu (fixture f03: "thay đổi dư"
được ghép nhưng không thêm "số").

### 5.4 Marker và số thứ tự gốc

- ListItem: xuất `marker + " " + chữ`, marker lấy từ `ListItem.marker` của Docling — `9.`, `a)`, `1.1`, `II.`, `-`.
- ListItem không có marker (Docling không nhận `đ)`, `a.1)`): xuất **chỉ chữ** — chữ vẫn chứa `đ)` — và **không**
  chèn số vị trí (đếm vào `synthesized_number_avoided`).
- Mỗi mục là **một đoạn riêng**, không dùng cú pháp danh sách Markdown, không thụt lề (thụt 4 dấu cách sẽ thành
  code block).
- Escape cú pháp khối Markdown ở **đầu dòng**: `9.` → `9\.`, `10)` → `10\)`, `-`/`*`/`+` → `\-`, `#` → `\#`, `>` →
  `\>`. Mọi renderer CommonMark hiển thị đúng `9.`, `-`… như chữ thường ⇒ không còn đánh lại số, không còn mất gạch
  đầu dòng do CSS. Áp dụng cho cả đoạn TEXT bắt đầu bằng số hoặc gạch.
- Tiêu đề (SectionHeader/Title: "Điều 1.", "CHƯƠNG I") giữ nguyên cú pháp `##` của Docling.

### 5.5 Bảng

`TableItem` không bị đọc hay sửa; serializer bảng của Docling dùng nguyên (test: Markdown của từng bảng trong kết quả
Legal giống hệt Standard). Hai bảng ở hai trang **không** bị ghép; bảng không bao giờ là một phần của phép ghép đoạn.

### 5.6 Trường nghiệp vụ

Không có quy tắc nào chạm vào chữ ngoài: (a) chuyển cả phần tử sang furniture (chỉ số trang/header lặp đủ điều kiện),
(b) nối hai phần tử bằng một dấu cách, (c) escape một ký tự cú pháp ở đầu dòng. Số hiệu, ngày, tiền, %, lãi suất, hạn
mức, thời hạn, URL, mã tài liệu giữ nguyên (fixture f08: 12/12 trường).

## 6. Provenance và khả năng kiểm chứng

`NormalizationResult`: `content`, `operations` (mỗi phép: loại, lý do, trang, ref DocItem, bbox, số ký tự trước/sau,
và — chỉ khi `include_text=True` cho diagnostic cục bộ — chữ trước/sau), `warnings`, `counts`, `elapsed_ms`,
`version`, `document` (bản sao đã chuẩn hóa).

Metadata trả về cùng kết quả trích xuất (không chứa chữ): `text_normalization`, `legal_normalization_status`
(`applied` / `failed`), `legal_normalizer_version`, `legal_normalization_counts`, `legal_normalization_warnings`,
`legal_normalization_ms`, cùng OCR engine/model version đã có (`ocr_engine`, `ocr_model_version`, `ocr_model_sha256`).

**Giới hạn trung thực:** ChatBot5400 hiện **không lưu** metadata trích xuất vào Source và không có provenance theo
chunk ⇒ Phase 12 **không** tuyên bố trích dẫn số trang chính xác trong RAG. Báo cáo provenance đầy đủ (trước/sau
từng phép) chỉ có ở diagnostic cục bộ (`09_legal_report.json`). Không tạo sidecar lưu nội dung (tránh dữ liệu nhạy
cảm không có vòng đời / phân quyền). Lưu provenance theo chunk là việc của một phase sau (cần thiết kế schema).

## 7. Fallback

`normalize_or_fallback`: bất kỳ ngoại lệ nào (tài liệu lỗi, vượt giới hạn) hoặc kết quả rỗng trong khi Standard có
chữ ⇒ trả về **Standard export** + `legal_normalization_status=failed` + tên lỗi; log một dòng cảnh báo (không có
chữ). Không bao giờ mất nội dung, không bao giờ báo "đã chuẩn hóa" khi không làm được.

Giới hạn tài nguyên (ngoài giới hạn đó ⇒ fallback): 200.000 item, 10.000 trang, 50.000.000 ký tự. Thuật toán tuyến
tính theo số item (trừ kiểm tra "ngoài cùng" trên ứng viên dải biên).

## 8. Threat model

| Mối đe dọa | Biện pháp |
|---|---|
| Nội dung PDF chứa HTML/script | serializer Docling escape HTML (`&lt;script&gt;`); normalizer không bỏ escape; frontend không dùng rehype-raw (test) |
| Markdown injection (`#`, `>`, `- `, `1.` ở đầu dòng) | escape ở đầu dòng (test) |
| Liên kết `javascript:` | không đổi so với Standard; react-markdown `urlTransform` mặc định chặn |
| Metadata/OCR thành lệnh hoặc prompt | normalizer không gọi LLM; metadata chỉ là số; nội dung đi vào RAG như trước (cùng mức tin cậy) |
| Tài liệu lỗi / cực lớn / item lồng sâu | giới hạn tài nguyên + fallback; duyệt cha tối đa 64 cấp |
| Rò rỉ nội dung qua log | log chỉ số đếm/phiên bản/thời gian; báo cáo có chữ chỉ ở diagnostic cục bộ, thư mục 0700 |
| Truy cập mạng | không import thư viện mạng; test chặn socket |
| Đổi cấu hình toàn cục trái phép | endpoint `PUT /api/ocr/config` nằm sau `require_admin`; cổng triển khai là biến môi trường |

## 9. Bảo toàn hành vi cũ

- Standard: `convert_file` đi đúng nhánh cũ (test so sánh từng byte với `export_to_markdown()`); quyết định định
  tuyến không đổi khi Legal tắt (test parity định tuyến); parity options content-core giữ nguyên.
- Không đổi dependency, Docling, Heron, TableFormer, engine, model, PDF Prep, D-33, chunking, embedding, RAG, chat,
  transformation, podcast, schema.

## 10. Giới hạn đã biết

1. Phụ thuộc nhãn của Layout Heron: số trang mà layout gộp vào đoạn văn (cùng một cluster) không tách được.
2. Thứ tự đọc của Docling không được sửa (bảo toàn theo yêu cầu).
3. Ghép đoạn yêu cầu bbox; PDF không có provenance chỉ được escape marker.
4. Ngưỡng 15% cho "ảnh lớn" và dải 10% là giá trị khởi điểm trên fixture tổng hợp; cần đo trên tài liệu thật.
5. Trường hợp đoạn kết thúc bằng chữ số rồi trang sau bắt đầu chữ thường nhưng thực ra là hai đoạn khác nhau (rất
   hiếm, ví dụ bảng kê không có dấu chấm) có thể bị ghép — đo bằng `false_merge` trên tài liệu thật ở Local.
