# Báo cáo Phase 10G — Mất nội dung OCR dưới watermark chéo và cơ chế tự dùng Full Page OCR

Ngày: 2026-11-16 · Nhánh: `feature/tesseract-agri-custom-model` · Stack: `chatbot5400-agri-test` · Trạng thái: **chờ
chủ dự án phê duyệt** — chưa merge, chưa push, chưa phát hành, chưa triển khai production.

Tài liệu này công khai và chỉ chứa **số liệu tổng hợp**: không có nội dung văn bản, tên tài liệu nội bộ, ảnh trang hay
nội dung watermark của tài liệu thật. Mọi PDF dùng trong test và trong kho mã là **tổng hợp** (văn bản hư cấu, chuỗi
watermark trung tính). Quyết định thiết kế: [DECISIONS.md](DECISIONS.md) D-33. Cấu hình:
[OCR_CONFIGURATION.md](OCR_CONFIGURATION.md).

> **Bản công khai (rà soát ở Phase 10I).** Báo cáo ghi nhận trạng thái tại thời điểm viết. Chi tiết hạ tầng
> (đường dẫn máy chủ, mã container / image, tài khoản, SHA-256 của model riêng) đã được lược bỏ hoặc thay bằng giá trị
> minh họa (`/srv/example/…`); bản vận hành đầy đủ do chủ dự án lưu ngoài repository. Các mã commit ngắn trong báo cáo
> là commit cục bộ của nhánh phát triển trước khi gộp — chúng không có trên GitHub. Trạng thái phát hành hiện tại:
> [OCR_RELEASE_NOTES_RC2.md](OCR_RELEASE_NOTES_RC2.md).

## 1. Kết luận

| Hạng mục | Kết luận | Cơ sở |
|---|---|---|
| Mất nội dung dưới watermark | **WATERMARK OCR CONTENT LOSS FIXED** (khi bật cờ, tài liệu không hỗn hợp) | Tài liệu thật 5 trang: 974 → 10.606 ký tự (Agri), 975 → 10.636 (Best); mục 7 |
| Cơ chế tự động | **AUTO FULL PAGE VERIFIED** | 25/25 PDF tổng hợp có nguy cơ cho đầu ra giống hệt từng byte với Force Full Page thủ công; cả năm engine qua API + worker; mục 5–6 |
| PDF thông thường | **NORMAL PDF BEHAVIOR UNCHANGED** | 17/17 PDF tổng hợp không có nguy cơ, 7/7 fixture nghiệm thu và 102/102 lượt của bộ benchmark Phase 10E chạy lại cho đầu ra giống hệt từng byte; mục 5, 6.1 |
| Engine hiện có | **EXISTING OCR ENGINES UNCHANGED** | Cờ mặc định tắt: không phân tích, không log, không metadata mới; Docker acceptance 53 PASS / 0 FAIL, hồi quy backend chỉ còn đúng 10 lỗi có sẵn của baseline; mục 9 |
| Production | **PRODUCTION UNCHANGED** | Cùng commit, cùng container (không restart), cùng file cấu hình, cờ không có mặt; mục 10 |

**AWAITING OWNER APPROVAL.**

Hai điều cần biết trước khi phê duyệt:

1. **PDF hỗn hợp chưa được sửa** (theo yêu cầu): tài liệu vừa có trang scan dưới watermark vừa có trang văn bản điện
   tử tốt giữ nguyên hành vi cũ, có cảnh báo trong log. Số đo hai phía ở mục 6.3.
2. **Ngưỡng 50% / 10% đề xuất ban đầu đã được thay** sau khi hiệu chuẩn: ngưỡng góc cố định bị loại bỏ, ngưỡng phủ
   là 2% của một đại lượng khác (mục 4). Các ngưỡng vẫn là giá trị khởi điểm, chỉnh được bằng biến môi trường.

## 2. Nguyên nhân gốc

Docling 2.129.0, `docling/models/base_ocr_model.py`. Thứ tự pipeline: tiền xử lý → Layout → **OCR** → hậu xử lý
layout → bảng → ghép tài liệu.

- `get_ocr_rects`: chế độ `DEFAULT` gọi `_find_pdf_aware_layout_ocr_rects` — giữ các cụm layout có bitmap. Trang scan
  nên mọi cụm được giữ; vùng OCR cho ra 98,7% số từ so với OCR toàn trang. Bước này **không** gây mất nội dung.
- `post_process_cells`: `FULL_PAGE` → dùng nguyên các ô OCR. Chế độ khác → `_merge_ocr_and_pdf_cells` với ưu tiên
  `PDF_FIRST`: giữ mọi ô text PDF **hiển thị**, chỉ thêm ô OCR không giao với ô nào trong số đó; sau đó ô text **ẩn**
  cũng chỉ được thêm lại nếu không giao với các ô đã giữ.
- `_merge_cells_by_priority`: phép giao dùng bbox **thẳng trục** (`cell.rect.to_bounding_box()`); mã nguồn tự ghi
  chú *"The R-tree bbox intersection is a weak criterion"*.

Một dòng watermark chéo là **một** ô text hiển thị. Bbox thẳng trục của nó phủ gần hết trang, nên gần như mọi ô OCR
(và cả lớp OCR ẩn) bị bỏ. Trên tài liệu thật: 2.071 / 2.129 ô OCR bị bỏ, 100% do giao với ô watermark. Không phụ
thuộc engine (Tesseract Agri, Tesseract Best, RapidOCR đều như nhau); không liên quan model, DPI hay Layout Heron.

## 3. Phương án phát hiện

Thực hiện trong `open_notebook/ocr/pdf_prep.py` bằng pdfium, **trước** khi Docling chạy. Chỉ đọc hình học và số đếm:
không so khớp nội dung chữ, không hardcode tên tổ chức hay chuỗi watermark, không sửa và không ghi PDF.

| Lớp trong PDF | Cách nhận biết | Vai trò |
|---|---|---|
| **Ảnh scan** | hợp các ảnh phủ ≥ 50% trang | điều kiện cần của trang có nguy cơ |
| **Lớp OCR ẩn** | text render mode 3 / 7 | không bao giờ gây nguy cơ; số ký tự ẩn là bằng chứng nội dung nằm trong ảnh |
| **Văn bản hiển thị thông thường** | bbox của đối tượng bằng tổng ô ký tự của chính nó — tỷ lệ **1,00** với mọi chữ song song trục, mọi cỡ chữ. Chữ nghiêng cũng được tính khi các khung bao nghiêng của trang chứa ký tự hiển thị **nhiều hơn khoảng trống** (lớp văn bản hiển thị đi theo bản scan bị lệch) | ≥ 400 ký tự và nhiều hơn ký tự ẩn ⇒ "trang văn bản điện tử" |
| **Khung bao nghiêng** (watermark chéo) | bbox ≥ **1,5** lần tổng ô ký tự của chính nó **và** nghiêng ≥ 1° so với trục gần nhất | đại lượng quyết định: phần trang chúng chiếm **trên ảnh, ngoài mọi ký tự hiển thị** |

**Trang có nguy cơ** ⇔ là trang scan **và** phần "chiếm trống trên ảnh" ≥ 2% trang **và** không phải trang văn bản điện tử.

**Quyết định cấp tài liệu** (`pdf_prep.decide_ocr_mode`; Docling chỉ có một chế độ OCR cho cả tài liệu):

| Tình huống | Chế độ hiệu lực | Lý do ghi log |
|---|---|---|
| Cờ tắt (mặc định) | như đã cấu hình; không phân tích | — (không log, không metadata) |
| OCR đang tắt | như đã cấu hình; **không tự bật OCR** | `ocr_disabled` |
| Force Full Page đã bật thủ công | `full_page` (giữ nguyên lựa chọn) | `manual_full_page` |
| ≥ 1 trang có nguy cơ, không có trang văn bản điện tử | **`full_page` cho riêng tài liệu này** | `tilted_text_box_over_scan` |
| Có trang có nguy cơ **và** có trang văn bản điện tử | như đã cấu hình + `WARNING` | `mixed_document` |
| Không có trang có nguy cơ | như đã cấu hình | `no_risk` |
| Không phải PDF / không đọc được | như đã cấu hình | `not_a_pdf` / `check_failed` |

Áp dụng bằng `OcrOptions.mode = FULL_PAGE` chính thức của Docling trong `docling_extract.convert_document`. Giá trị
Force Full Page trong cơ sở dữ liệu không bao giờ bị ghi.

**Năm engine.** Bốn engine Tesseract Fast / Best / Agri và EasyOCR luôn đi qua `convert_document`. RapidOCR ở cấu
hình mặc định đi nguyên Content Core (D-03), vốn không nhận tham số chế độ OCR; vì vậy khi cờ bật và tài liệu được
quyết định `full_page`, `should_use_native_ocr` chuyển **riêng tài liệu đó** sang lớp OCR của dự án với cùng engine
RapidOCR. Mọi tài liệu khác vẫn đi Content Core.

**Log** — một dòng cho mỗi PDF khi cờ bật (ví dụ từ tài liệu thật; không có tên file hay nội dung):

```text
OCR mode: engine=tesseract_agri configured=default effective=full_page auto_full_page=True
reason=tilted_text_box_over_scan pages=5 scan_pages=5 risk_pages=5 text_pages=0 max_coverage=0.7991
max_box=0.8429 max_inflation=11.06 angles=[37] (thresholds: scan>=0.5, coverage>=0.02,
box_inflation>=1.5, angle>=1.0, text_page_chars>=400)
```

## 4. Ngưỡng sử dụng và cách hiệu chuẩn

Bộ hiệu chuẩn: 38 PDF tổng hợp sinh bởi `scripts/ocr/generate_overlay_fixtures.py`, đo bằng
`scripts/ocr/overlay_calibration.py` qua đúng đường chuyển đổi production (Docling + Layout Heron + TableFormer +
Tesseract Vietnamese Best), ground truth đã biết.

**Phát hiện chính: nội dung mất tỷ lệ với diện tích khung bao, không với góc.**

| Dòng watermark vẽ ở góc | Độ nghiêng đo được | Phình khung bao | Khung bao / trang | Chiếm trống trên ảnh | Recall cờ tắt | Recall Force Full Page | Mất (điểm %) | Quyết định |
|---|---|---|---|---|---|---|---|---|
| 2° | 2° | 3,05 | 7,1% | 4,8% | 95,6% | 99,5% | 3,9 | **kích hoạt** |
| 5° | 5° | 5,52 | 14,3% | 12,1% | 87,3% | 98,4% | 11,0 | **kích hoạt** |
| 10° | 10° | 8,57 | 26,3% | 23,9% | 84,0% | 98,1% | 14,1 | **kích hoạt** |
| 15° | 15° | 10,73 | 38,1% | 35,5% | 75,2% | 99,2% | 24,0 | **kích hoạt** |
| 30° | 30° | 14,17 | 71,5% | 68,3% | 42,4% | 97,8% | 55,4 | **kích hoạt** |
| 45° | 45° | 15,09 | 91,6% | 87,5% | 4,7% | 97,2% | 92,6 | **kích hoạt** |
| 75° | 15° | 10,73 | 53,9% | 50,2% | 38,8% | 97,8% | 59,0 | **kích hoạt** |
| 85° | 5° | 5,52 | 20,3% | 17,1% | 71,4% | 95,9% | 24,5 | **kích hoạt** |
| 90° | 0° (không tính) | — | 0,0% | 0,0% | 100,0% | 99,5% | -0,5 | giữ nguyên |

Một dòng dài nghiêng 2° đã mất 3,9 điểm phần trăm số từ; 5° mất 11; 85° (lệch 5° so với trục dọc) mất 24,5. Ngưỡng
góc 10° dự định ban đầu sẽ bỏ sót các trường hợp này. Vì vậy:

| Tín hiệu được yêu cầu xem xét | Kết luận sau khi đo | Cách dùng trong quy tắc |
|---|---|---|
| **Góc xoay** | Không phải nguyên nhân: 90° không mất gì, 2° đã mất | Điều kiện phụ ≥ 1° (loại phông chữ có số đo bất thường); góc được ghi log |
| **Kích thước khung bao** | Chính là nguyên nhân, nhưng phải so với chữ của chính nó: chữ thẳng trục cỡ 60 pt có bbox lớn mà tỷ lệ vẫn 1,00 | Tỷ lệ phình bbox / ô ký tự ≥ 1,5 để một khung bao được tính |
| **Tỷ lệ bao phủ** | Quyết định mức mất: số từ mất tăng đều theo diện tích bị chiếm, bằng 0,6–2,6 lần diện tích đó tùy khung bao nằm trên vùng nhiều hay ít chữ | Phần chiếm trên ảnh, ngoài ký tự hiển thị, ≥ 2% trang |

| Dòng watermark 55° | Độ nghiêng đo được | Phình khung bao | Khung bao / trang | Chiếm trống trên ảnh | Recall cờ tắt | Recall Force Full Page | Mất (điểm %) | Quyết định |
|---|---|---|---|---|---|---|---|---|
| 1 lần lặp, cỡ 10 pt | 35° | 2,66 | 1,5% | 1,1% | 96,4% | 99,5% | 3,0 | giữ nguyên |
| 1 lần lặp, cỡ 16 pt | 35° | 2,66 | 3,9% | 3,0% | 91,5% | 99,2% | 7,7 | **kích hoạt** |
| 2 lần lặp, cỡ 16 pt | 35° | 5,06 | 15,1% | 13,2% | 69,7% | 97,0% | 27,3 | **kích hoạt** |
| 3 lần lặp, cỡ 16 pt | 35° | 7,47 | 33,6% | 30,8% | 34,4% | 95,6% | 61,1 | **kích hoạt** |
| 4 lần lặp, cỡ 16 pt | 35° | 9,88 | 59,4% | 55,6% | 3,6% | 95,0% | 91,5 | **kích hoạt** |
| 8 lần lặp, cỡ 16 pt | 35° | 19,51 | 100,0% | 95,0% | 0,0% | 96,4% | 96,4 | **kích hoạt** |

Ngưỡng 2% tách hai điểm đo gần nhau nhất: 1,1% (mất 3,0 điểm — giữ nguyên) và 3,0% (mất 7,7 điểm — kích hoạt).

| Ngưỡng | Mặc định | Biến môi trường | Ghi chú |
|---|---|---|---|
| Trang scan | ảnh phủ ≥ 50% trang | — (ngưỡng sẵn có của `pdf_prep`) | Không còn là ngưỡng nhạy: phần chiếm chỉ được tính ở nơi có ảnh |
| Phình khung bao | ≥ 1,5 | — (hằng số) | Chữ thẳng trục đo đúng 1,00; nghiêng 2° đã là 3,0; watermark thật 11,1 |
| Độ nghiêng | ≥ 1° | `OCR_AUTO_FULL_PAGE_MIN_ANGLE` | |
| Chiếm trống trên ảnh | ≥ 2% trang | `OCR_AUTO_FULL_PAGE_MIN_COVERAGE` | Thay cho "text hiển thị ≥ 10%" ban đầu |
| Trang văn bản điện tử | ≥ 400 ký tự thường và nhiều hơn ký tự ẩn | `OCR_AUTO_FULL_PAGE_TEXT_PAGE_CHARS` | Header + footer + khối chữ ký tổng hợp: 97 ký tự; một trang văn bản: > 1.200 |

Các ngưỡng này được hiệu chuẩn trên PDF tổng hợp và kiểm lại trên **một** tài liệu thật; chúng là giá trị khởi điểm.

## 5. Kết quả trước và sau trên bộ PDF tổng hợp

Engine Tesseract Vietnamese Best, máy phát triển. "Recall" = tỷ lệ từ của ground truth có trong kết quả.

**Tài liệu có nguy cơ — phải kích hoạt**

| PDF tổng hợp | Ô OCR giữ / tạo ra (cờ tắt) | Recall cờ tắt | Recall cờ bật | Recall Force Full Page thủ công | CER cờ tắt → bật | Số từ trong kết quả tắt → bật | Giây tắt → bật | Cờ bật = thủ công (từng byte) |
|---|---|---|---|---|---|---|---|---|
| scan 150 DPI + lớp OCR ẩn + watermark 55° | 0/364 | 0,0% | 86,0% | 86,0% | 98,2% → 28,9% | 15 → 361 | 6,3 → 5,7 | có |
| scan 200 DPI + lớp OCR ẩn + watermark 55° | 0/360 | 0,0% | 95,6% | 95,6% | 98,2% → 1,7% | 15 → 362 | 6,0 → 6,4 | có |
| scan 300 DPI + lớp OCR ẩn + watermark 55° | 0/359 | 0,0% | 95,6% | 95,6% | 98,2% → 2,9% | 15 → 364 | 6,1 → 6,3 | có |
| scan 1-bit 300 DPI + lớp OCR ẩn + watermark 55° (đúng cấu trúc gây lỗi) | 0/359 | 0,0% | 98,6% | 98,6% | 98,2% → 1,2% | 15 → 362 | 6,0 → 6,0 | có |
| scan + watermark 55°, không có lớp ẩn | 0/360 | 0,0% | 95,6% | 95,6% | 98,2% → 1,7% | 15 → 362 | 6,0 → 6,1 | có |
| watermark vẽ qua Form XObject (phép xoay nằm trong ma trận của form) | 0/360 | 0,0% | 95,6% | 95,6% | 98,2% → 1,7% | 15 → 362 | 6,9 → 7,5 | có |
| watermark 55° + header, footer, khối chữ ký thông thường | 0/383 | 0,5% | 96,1% | 96,1% | 94,2% → 1,7% | 43 → 361 | 7,5 → 6,2 | có |
| nhiều watermark nhỏ 45° lát kín trang | 163/362 | 44,6% | 93,7% | 93,7% | 58,7% → 3,0% | 211 → 364 | 6,1 → 6,2 | có |
| 5 trang scan, trang nào cũng có watermark | 0/1035 | — | — | — | — → — | 120 → 920 | 23,1 → 21,5 | có |
| 3 trang scan, chỉ trang 2 có watermark (không có trang điện tử) ⁴ | 592/645 | — | — | — | — → — | 621 → 612 | 11,9 → 12,2 | có |

Hai tài liệu nhiều trang không có ground truth chính xác theo trang nên chỉ có số từ. Bản scan 150 DPI khôi phục 86% vì chính chất lượng OCR ở 150 DPI (CER 28,9% cả khi ép toàn trang thủ công), không phải do cơ chế.

⁴ Fixture này kiểm quy tắc cấp tài liệu (một trang có nguy cơ giữa các trang scan thường ⇒ cả tài liệu OCR toàn trang), không kiểm lượng nội dung: trang 2 của nó gần như trống. Đo riêng trang đó: cờ tắt giữ 0 / 53 ô OCR và kết quả chỉ còn 15 từ, đều là chuỗi watermark; OCR toàn trang cho 6 từ nội dung và không còn chuỗi watermark. Vì vậy tổng số từ 621 → 612 là 606 từ nội dung + 15 từ watermark → 606 + 6 từ nội dung. Hai trang scan thường của tài liệu cho cùng số từ ở hai chế độ.

**Tài liệu trông giống nhưng không có nguy cơ — phải giữ nguyên**

| PDF tổng hợp | Chiếm trống trên ảnh | Ký tự hiển thị thường / ẩn | Quyết định | Ô OCR giữ / tạo ra | Recall cờ tắt | Recall cờ bật | Cờ bật = cờ tắt (từng byte) | Recall nếu ép Force Full Page |
|---|---|---|---|---|---|---|---|---|
| chữ dọc 90° ở lề (khung bao khít chữ) | 0,0% | 64 / 1271 | giữ nguyên | 364/378 | 100,0% | 100,0% | có | 99,5% |
| dấu chéo nhỏ ở góc trang | 0,0% | 6 / 1271 | giữ nguyên | 363/363 | 100,0% | 100,0% | có | 99,5% |
| scan thường 150 DPI | 0,0% | 0 / không đếm | giữ nguyên | 363/363 | 99,2% | 99,2% | có | 99,2% |
| scan thường 200 DPI | 0,0% | 0 / không đếm | giữ nguyên | 363/363 | 99,5% | 99,5% | có | 99,5% |
| scan thường 300 DPI | 0,0% | 0 / không đếm | giữ nguyên | 363/363 | 98,4% | 98,4% | có | 98,4% |
| scan + lớp OCR ẩn, không watermark | 0,0% | 0 / không đếm | giữ nguyên | 363/363 | 100,0% | 100,0% | có | 99,5% |
| scan + lớp ẩn + header / footer / chữ ký thông thường | 0,0% | 97 / 1271 | giữ nguyên | 363/386 | 100,0% | 100,0% | có | 99,5% |
| văn bản điện tử | 0,0% | không đếm / không đếm | giữ nguyên | — | 100,0% | 100,0% | có | 98,9% |
| văn bản điện tử + watermark 55° (không có ảnh scan) | 0,0% | không đếm / không đếm | giữ nguyên | — | 100,0% | 100,0% | có | 98,4% |
| văn bản điện tử trên ảnh nền toàn trang + watermark 55° | 71,5% | 1271 / 0 | giữ nguyên | 0/360 | 100,0% | 100,0% | có | 99,5% |
| scan có lớp văn bản **hiển thị** + watermark 55° ¹ | 71,5% | 1271 / 0 | giữ nguyên | 0/497 | 15,2% | 15,2% | có | 65,8% |
| văn bản điện tử + ảnh chiếm nửa trang + watermark 55° | 52,0% | 1271 / 0 | giữ nguyên | 0/212 | 100,0% | 100,0% | có | 98,1% |
| watermark **ngang** cỡ lớn (giới hạn đã biết) ² | 0,0% | 8 / 1271 | giữ nguyên | 336/358 | 92,3% | 92,3% | có | 95,6% |
| dòng 55° ngắn, cỡ 10 pt (dưới ngưỡng) ² | 1,1% | 0 / 1271 | giữ nguyên | 350/364 | 96,4% | 96,4% | có | 99,5% |
| hỗn hợp: 1 trang điện tử + 2 trang scan có watermark ³ | 92,8% | (nhiều trang) | hỗn hợp — giữ nguyên | 0/720 | 33,3% | 33,3% | có | 96,4% |

¹ Lớp văn bản hiển thị của fixture này là bản **không dấu** (phông chuẩn của PDF không có chữ tiếng Việt), còn recall được tính so với ground truth có dấu — con số thấp không phải là mất nội dung: kết quả chính là lớp văn bản của PDF, như trước. Ép toàn trang ở đây cho CER 63,8% vì chữ hiển thị đè lên ảnh scan khi dựng trang; không kích hoạt là đúng.
² Hai trường hợp nằm dưới ngưỡng theo thiết kế: còn mất 3,0–3,3 điểm phần trăm số từ (mục 13).
³ Giữ nguyên theo quy tắc tài liệu hỗn hợp (mục 6.3).

"Không đếm" = bộ phát hiện không cần đọc ký tự của trang đó: trang không có đối tượng text hiển thị nào, hoặc không phải trang scan và tài liệu không có trang nào có nguy cơ.

Ở các PDF văn bản điện tử, cột cuối cho thấy ép toàn trang làm **giảm** chất lượng (100% → 98,1–99,5%); đó là lý do quy tắc không bao giờ kích hoạt trên trang có lớp văn bản tốt.

Tổng hợp trên 38 PDF:

| Chỉ số | Giá trị |
|---|---|
| Tài liệu được kích hoạt | 23 — đầu ra **giống hệt từng byte** với Force Full Page thủ công ở cả 23 |
| Tài liệu không kích hoạt | 15 — đầu ra **giống hệt từng byte** với khi cờ tắt ở cả 15 |
| Kích hoạt nhầm (false positive) trong nhóm "trông giống" | **0 / 15** |
| Bỏ sót có mất nội dung | 2 — đều dưới ngưỡng theo thiết kế: khung bao 1,1% trang (mất 3,0 điểm) và watermark ngang cỡ lớn (mất 3,3 điểm) |
| Tổng thời gian 38 tài liệu | cờ tắt 248,2 s · cờ bật 246,3 s · Force Full Page 257,7 s |
| Chi phí phát hiện | 0,35 s cho cả 38 tệp (≈ 9 ms mỗi tệp); tài liệu thật 5 trang: dưới 0,1 s. PDF điện tử 300 trang × 400 đối tượng text: 0,8 s; × 2.000 đối tượng: 4,0 s |

**Bổ sung sau rà soát (4 PDF, đo riêng sau lần hiệu chuẩn chính).** Khi rà các trường hợp biên, phép đo cho thấy một
trang scan mang lớp văn bản **hiển thị** có các dòng nghiêng từ 1,5° (lớp văn bản đi theo độ lệch của bản scan) thỏa
cả ba điều kiện góc / phình / chiếm trống và sẽ bị kích hoạt nhầm — ép toàn trang ở đó làm recall giảm từ 100% xuống
43%. Quy tắc được bổ sung một điều kiện hình học: khung bao nghiêng chứa ký tự hiển thị **nhiều hơn** khoảng trống là
văn bản của trang, không phải lớp phủ. Watermark thì ngược lại, kể cả khi có nhiều ký tự. Không quyết định nào trong
38 PDF của lần hiệu chuẩn chính thay đổi (cùng quyết định, cùng tỷ lệ chiếm); 38 tệp được sinh lại giống hệt từng byte.

| PDF tổng hợp bổ sung | Chiếm trống / có chữ trong khung bao nghiêng | Quyết định | Ô OCR giữ / tạo ra (cờ tắt) | Recall cờ tắt | Recall cờ bật | Recall nếu ép Force Full Page | Cờ bật giống hệt |
|---|---|---|---|---|---|---|---|
| scan + lớp ẩn + watermark 9 dòng dài 30° (486 ký tự) | 59,4% / 18,3% | **kích hoạt** | 5/344 | 1,4% | 86,5% | 86,5% | Force Full Page thủ công |
| như trên, không có lớp ẩn | 59,4% / 18,3% | **kích hoạt** | 5/344 | 1,4% | 86,5% | 86,5% | Force Full Page thủ công |
| scan dưới lớp văn bản **hiển thị** có các dòng nghiêng 2° | 3,1% / 22,8% | giữ nguyên | 220/470 | 100,0% | 100,0% | 43,0% | cờ tắt |
| scan dưới lớp văn bản **hiển thị** có các dòng nghiêng 5° | 5,2% / 23,4% | giữ nguyên | 223/528 | 100,0% | 100,0% | 43,0% | cờ tắt |

## 6. PDF thông thường, năm engine và PDF hỗn hợp

### 6.1 PDF thông thường — không đổi

- 15 PDF tổng hợp không có nguy cơ (scan thường ở 150 / 200 / 300 DPI, scan + lớp OCR ẩn, scan + header / footer /
  chữ ký, văn bản điện tử, văn bản điện tử + watermark, văn bản trên nền ảnh + watermark, chữ dọc 90°, dấu nhỏ ở góc…):
  đầu ra khi cờ bật giống hệt từng byte khi cờ tắt. Hai PDF bổ sung ở mục 5 (lớp văn bản hiển thị nghiêng) cũng vậy.
- 7 fixture nghiệm thu của dự án (`tests/fixtures/ocr/*.pdf`, 9 trang): quyết định `none` ở cả 7; kết quả chuyển đổi
  khi cờ bật giống hệt từng byte khi cờ tắt (test pipeline thật, Tesseract Vietnamese Best).
- **Bộ benchmark Phase 10E chạy lại nguyên vẹn với cờ bật** (17 PDF pháp lý tổng hợp × 3 cấu hình model × Force Full
  Page tắt / bật = 102 lượt, trong container, image cuối), so với kết quả đã lưu của Phase 10E:

  | Cấu hình | Force Full Page | Số lượt | Văn bản giống hệt | Chỉ số giống hệt (CER, WER, dấu, tiêu đề, Điều / Khoản / Điểm, số hiệu, ngày, lỗi pháp lý) | CER trung bình trước → sau | Lý do ghi log |
  |---|---|---|---|---|---|---|
  | Tesseract Best | tắt | 17 | 17 | 17 | 3,31% → 3,31% | `no_risk` |
  | Tesseract Best | bật | 17 | 17 | 17 | 2,81% → 2,81% | `manual_full_page` |
  | Agri v1 | tắt | 17 | 17 | 17 | 3,21% → 3,21% | `no_risk` |
  | Agri v1 | bật | 17 | 17 | 17 | 3,28% → 3,28% | `manual_full_page` |
  | Agri v1 + English | tắt | 17 | 17 | 17 | 3,52% → 3,52% | `no_risk` |
  | Agri v1 + English | bật | 17 | 17 | 17 | 3,59% → 3,59% | `manual_full_page` |
  | **Tổng** | | **102** | **102** | **102** | | 51 `no_risk` · 51 `manual_full_page` · 0 lỗi |

  Thời gian (tổng 17 PDF, bốn cấu hình Agri chạy khi máy không có tải khác): 122,2 → 122,9 s · 132,0 → 132,1 s ·
  130,9 → 130,7 s · 140,8 → 140,7 s, tức chênh dưới 1%. Hai cấu hình Tesseract Best chạy trùng lúc với một lượt test
  khác trên máy chủ nên thời gian của chúng (131 → 190 s, 138 → 170 s) không dùng để so sánh.
- Bộ phát hiện trên cả 24 PDF này (38 trang, 34 trang scan): 0 khung bao nghiêng, 0 trang có nguy cơ.
- Qua API + worker, đường RapidOCR mặc định: scan thường và văn bản điện tử **vẫn đi Content Core**, số ký tự kết quả
  bằng nhau khi cờ bật và tắt (1.511 và 1.633).

### 6.2 Năm engine

Qua API + worker thật của stack thử nghiệm, PDF tổng hợp tái hiện cấu trúc lỗi (scan 1-bit 300 DPI + lớp OCR ẩn +
watermark 55°), Force Full Page **tắt**, cờ **bật**:

| Engine đang chọn | Trạng thái | Đường xử lý | Model OCR thực chạy | Chế độ cấu hình → hiệu lực | Lý do | Recall | Ký tự | Giây |
|---|---|---|---|---|---|---|---|---|
| RapidOCR | completed | lớp OCR của dự án | `RapidOcrModel` | default → **full_page** | `tilted_text_box_over_scan` | 37,7% | 1369 | 26,5 |
| Tesseract Vietnamese Fast | completed | lớp OCR của dự án | `TesseractOcrCliModel` | default → **full_page** | `tilted_text_box_over_scan` | 97,5% | 1670 | 8,9 |
| Tesseract Vietnamese Best | completed | lớp OCR của dự án | `TesseractOcrCliModel` | default → **full_page** | `tilted_text_box_over_scan` | 98,1% | 1669 | 9,0 |
| EasyOCR | completed | lớp OCR của dự án | `EasyOcrModel` | default → **full_page** | `tilted_text_box_over_scan` | 98,6% | 1692 | 26,2 |
| Tesseract Vietnamese Agri (v1) | completed | lớp OCR của dự án | `TesseractOcrCliModel` | default → **full_page** | `tilted_text_box_over_scan` | 99,5% | 1669 | 9,0 |

Sau năm lượt tự động, giá trị Force Full Page đã lưu vẫn là `false`.

Đo trong container cho từng engine (ô OCR trước / sau bước ghép của Docling, recall, CER). Thời gian không được ghi ở
bảng này vì lúc đo máy chủ đang chạy song song các kiểm thử khác; thời gian qua API + worker ở bảng trên được đo riêng.

| Engine | PDF tổng hợp | Ô OCR giữ / tạo ra: cờ tắt | Ô OCR giữ / tạo ra: cờ bật | Recall tắt → bật | Recall thủ công | CER tắt → bật | Cờ bật = thủ công |
|---|---|---|---|---|---|---|---|
| RapidOCR | scan 1-bit 300 DPI | 0/38 | 37/37 | 0,0% → 37,7% | 37,7% | 98,2% → 28,9% | có |
| RapidOCR | scan 200 DPI | 0/40 | 39/39 | 0,0% → 41,6% | 41,6% | 98,2% → 26,6% | có |
| RapidOCR | scan 150 DPI | 0/40 | 41/41 | 0,0% → 43,0% | 43,0% | 98,2% → 17,8% | có |
| Tesseract Vietnamese Fast | scan 1-bit 300 DPI | 0/356 | 356/356 | 0,0% → 97,5% | 97,5% | 98,2% → 1,7% | có |
| Tesseract Vietnamese Fast | scan 200 DPI | 0/357 | 358/358 | 0,0% → 93,7% | 93,7% | 98,2% → 2,4% | có |
| Tesseract Vietnamese Fast | scan 150 DPI | 0/366 | 373/373 | 0,0% → 89,0% | 89,0% | 98,2% → 22,7% | có |
| Tesseract Vietnamese Best | scan 1-bit 300 DPI | 0/359 | 359/359 | 0,0% → 98,1% | 98,1% | 98,2% → 1,4% | có |
| Tesseract Vietnamese Best | scan 200 DPI | 0/362 | 362/362 | 0,0% → 94,8% | 94,8% | 98,2% → 1,9% | có |
| Tesseract Vietnamese Best | scan 150 DPI | 0/364 | 376/376 | 0,0% → 90,4% | 90,4% | 98,2% → 23,1% | có |
| EasyOCR | scan 1-bit 300 DPI | 0/66 | 71/71 | 0,0% → 98,6% | 98,6% | 98,2% → 22,2% | có |
| EasyOCR | scan 200 DPI | 0/94 | 102/102 | 0,0% → 94,5% | 94,5% | 98,2% → 24,0% | có |
| EasyOCR | scan 150 DPI | 0/84 | 101/101 | 0,0% → 73,8% | 73,8% | 98,2% → 25,8% | có |
| Tesseract Vietnamese Agri (v1) | scan 1-bit 300 DPI | 0/363 | 363/363 | 0,0% → 99,5% | 99,5% | 98,2% → 0,7% | có |
| Tesseract Vietnamese Agri (v1) | scan 200 DPI | 0/363 | 363/363 | 0,0% → 97,8% | 97,8% | 98,2% → 1,0% | có |
| Tesseract Vietnamese Agri (v1) | scan 150 DPI | 0/361 | 366/366 | 0,0% → 92,3% | 92,3% | 98,2% → 11,9% | có |

| Engine | Tài liệu kích hoạt: giống hệt Force Full Page thủ công | Tài liệu không kích hoạt: giống hệt cờ tắt | Lỗi chuyển đổi |
|---|---|---|---|
| RapidOCR | 4 / 4 | 4 / 4 | 0 |
| Tesseract Vietnamese Fast | 4 / 4 | 4 / 4 | 0 |
| Tesseract Vietnamese Best | 4 / 4 | 4 / 4 | 0 |
| EasyOCR | 4 / 4 | 4 / 4 | 0 |
| Tesseract Vietnamese Agri (v1) | 4 / 4 | 4 / 4 | 0 |

RapidOCR dùng model mặc định không viết dấu tiếng Việt nên recall so với ground truth có dấu luôn thấp: sau khi sửa
đạt 41,6% ở 200 DPI, so với 43,2–46,8% của chính nó trên cùng bản scan không có watermark (số từ trong kết quả:
357 so với 347–363).

**Đường RapidOCR mặc định qua Content Core** (container không cài EasyOCR, giống production; kiểm bằng worker thật):

| PDF tổng hợp | Cờ tắt | Cờ bật |
|---|---|---|
| Scan thường | Content Core · 1.511 ký tự | Content Core · 1.511 ký tự (`no_risk`) |
| Văn bản điện tử | Content Core · 1.633 ký tự | Content Core · 1.633 ký tự (`no_risk`) |
| Scan 1-bit 300 DPI + lớp ẩn + watermark 55° | Content Core · **102 ký tự / 15 từ** | lớp OCR, `RapidOcrModel`, full page · **1.369 ký tự / 334 từ** |
| Scan 200 DPI + lớp ẩn + watermark 55° | Content Core · **102 ký tự / 15 từ** | lớp OCR, `RapidOcrModel`, full page · **1.494 ký tự / 357 từ** |
| 5 trang scan có watermark | Content Core · **728 ký tự** | lớp OCR, full page · **4.034 ký tự** |
| Hỗn hợp | Content Core · 1.841 ký tự | Content Core · 1.841 ký tự (`mixed_document`, có cảnh báo) |

Cơ chế tự động **không bị bỏ qua** trên đường mặc định, và tài liệu không có nguy cơ không rời Content Core.

### 6.3 PDF hỗn hợp — giữ nguyên hành vi, có cảnh báo

PDF tổng hợp 3 trang: 1 trang văn bản điện tử tốt + 2 trang scan dưới watermark.

| | Giữ chế độ mặc định (hành vi hiện tại, cũng là hành vi khi cờ bật) | Nếu ép Force Full Page cho cả tài liệu |
|---|---|---|
| Recall toàn tài liệu | 33,3% | 96,4% |
| CER toàn tài liệu | 65,4% | 1,3% |
| Trang văn bản điện tử (đo riêng trên `text_only`) | recall 100%, CER 0,0% | recall 98,9%, CER 0,3% |
| Trang scan dưới watermark | gần như mất hết | khôi phục |

Theo yêu cầu, cơ chế tự động **không** OCR lại toàn bộ tài liệu hỗn hợp: ép toàn trang làm lớp văn bản tốt giảm
1,1–1,9 điểm phần trăm số từ (đo trên ba PDF điện tử tổng hợp), và Docling 2.129.0 không có API chính thức để đặt
chế độ OCR theo từng trang. Tài liệu hỗn hợp được ghi `WARNING` kèm số trang hai loại; người vận hành có thể xử lý
riêng tệp đó với Force Full Page thủ công nếu các trang scan quan trọng hơn. Không xây cơ chế tách / ghép PDF.

Các kiểm thử cài đặt khác (qua API + worker): Force Full Page bật thủ công → giữ nguyên, lý do `manual_full_page`,
không phân tích; OCR tắt → không có dòng `OCR mode`, tài liệu đi Content Core, OCR **không** bị tự bật; sau các lượt
tự động, giá trị Force Full Page đã lưu vẫn là `false`; cấu hình stack được trả về đúng như lúc bắt đầu.

## 7. Nghiệm thu trên tài liệu thật

Chính PDF 5 trang đã phát hiện lỗi, xử lý hoàn toàn trong container thử nghiệm; script chỉ xuất số đếm, tỷ lệ và
mã băm của kết quả.

| Số đo mỗi trang | Giá trị |
|---|---|
| Ảnh scan | phủ 100% trang, 1-bit, 300 DPI |
| Đối tượng text ẩn / ký tự ẩn | 59–131 đối tượng / 1.498–1.815 ký tự |
| Đối tượng text hiển thị | 1 (khung bao nghiêng); 0 ký tự hiển thị thông thường |
| Khung bao nghiêng | nghiêng 37° so với trục gần nhất, bbox 83,9–84,3% trang, phình 11,06 lần |
| Chiếm trống trên ảnh | 79,5–79,9% trang ⇒ cả 5 trang có nguy cơ |

| Engine | Chế độ | Ô OCR giữ / tạo ra | Ký tự | Từ | Chuỗi watermark trong kết quả | So với Force Full Page thủ công |
|---|---|---|---|---|---|---|
| Tesseract Vietnamese Agri (v1) | cờ tắt | 58 / 2.129 | 974 | 165 | 15 | 2,7% số từ |
| Tesseract Vietnamese Agri (v1) | **cờ bật** (tự động) | 2.132 / 2.132 | **10.606** | **2.205** | 0 | **giống hệt từng byte** |
| Tesseract Vietnamese Agri (v1) | Force Full Page thủ công | 2.132 / 2.132 | 10.606 | 2.205 | 0 | — |
| Tesseract Vietnamese Best | cờ tắt | 59 / 2.129 | 975 | 165 | 15 | 2,5% số từ |
| Tesseract Vietnamese Best | **cờ bật** (tự động) | 2.135 / 2.135 | **10.636** | **2.211** | 0 | **giống hệt từng byte** |
| Tesseract Vietnamese Best | Force Full Page thủ công | 2.135 / 2.135 | 10.636 | 2.211 | 0 | — |

Thời gian xử lý không tăng (Agri 32,0 s → 29,1 s; Best 35,5 s → 33,4 s). Tệp PDF không bị sửa (kích thước và SHA-256
giống hệt trước / sau). Lượt Agri dùng đúng model v1 (đối chiếu SHA-256 với manifest).

Chưa có ground truth của tài liệu này, nên phép đo ở đây là "khôi phục tương đương Force Full Page thủ công", không
phải độ chính xác ký tự.

## 8. Kiểm thử

| Nhóm | Nội dung | Kết quả |
|---|---|---|
| Test đơn vị mới | `tests/test_ocr_auto_full_page.py`: số đo, 12 trường hợp trông giống, tài liệu nhiều trang / hỗn hợp, ngưỡng, quyết định, chuyển đổi, định tuyến mặc định, đồ thị nguồn | **103 đạt** |
| Test pipeline thật | `tests/test_ocr_auto_full_page_pipeline.py` (chỉ chạy khi `OCR_FULL_PIPELINE=1`) | **12 đạt, 4 bỏ qua** trên mã chạy cuối (máy phát triển): nội dung quay lại và giống hệt Force Full Page thủ công với RapidOCR, Tesseract Best, Tesseract Agri trên hai PDF gây lỗi; 4 PDF thường + 7 fixture nghiệm thu của dự án giống hệt từng byte khi cờ bật / tắt; PDF hỗn hợp giữ nguyên. 4 bỏ qua = Tesseract Fast và EasyOCR không cài trên máy phát triển — hai engine này được đo trong container (mục 6.2). Lần chạy đầu có 1 lỗi do **tiêu chí của test** đặt sai cho RapidOCR (đòi recall chữ có dấu tăng 40 điểm, trong khi model mặc định của RapidOCR không viết dấu: 0% → 38%); tiêu chí được sửa thành "số từ quay lại ≥ 80% số từ của trang và giống hệt Force Full Page thủ công", ngưỡng của ba engine Tesseract giữ nguyên |
| Cấu trúc gây lỗi | scan toàn trang + lớp OCR ẩn + watermark 55° khung bao lớn; 150 / 200 / 300 DPI và 1-bit 300 DPI | kích hoạt, khôi phục 86–99% |
| PDF scan không watermark | 150 / 200 / 300 DPI | giữ nguyên, giống hệt từng byte |
| PDF chỉ có lớp text điện tử | `text_only` | giữ nguyên, giống hệt từng byte |
| OCR ẩn, không watermark | `scan200_hidden` | giữ nguyên, giống hệt từng byte |
| Header / footer / chữ ký thông thường | `scan200_hidden_header_footer` | giữ nguyên; kèm watermark thì kích hoạt |
| Watermark trên tài liệu điện tử | `text_wm55`, `text_background_wm55` | giữ nguyên |
| Watermark nhỏ | dấu 45° ở góc; dòng 55° ngắn (1,1% trang) | giữ nguyên |
| Lớp văn bản hiển thị nghiêng trên ảnh scan | các dòng nghiêng 1,5° – 8° | giữ nguyên (văn bản của trang) |
| Watermark nhiều ký tự | 9 dòng dài 30°, 486 ký tự, có và không có lớp ẩn | kích hoạt |
| PDF hỗn hợp | 1 trang điện tử + 2 trang scan có watermark | giữ nguyên + `WARNING` |
| PDF nhiều trang | 5 trang đều có watermark; 3 trang scan chỉ trang 2 có watermark | kích hoạt cả tài liệu |
| OCR bị tắt | qua API + worker | không kích hoạt, không tự bật OCR |
| Force Full Page thủ công | qua API + worker | giữ nguyên, không phân tích |
| Cờ tắt | đơn vị + worker | không phân tích, không log, không metadata mới; kết quả như trước |
| Cả năm engine | qua API + worker và đo trong container | mục 6.2 |
| Watermark trong Form XObject, watermark lát nhiều ô nhỏ, khổ Letter / ngang / A0 | đơn vị + hiệu chuẩn | kích hoạt đúng |
| Tệp hỏng, không phải PDF, tệp không tồn tại | đơn vị | không lỗi, không kích hoạt; log lỗi không chứa đường dẫn tệp |
| Không hardcode | test cấu trúc trên mã nguồn `pdf_prep.py` + test hành vi | mã đo trang không gọi API đọc nội dung chữ (chỉ phân biệt ký tự có mực với khoảng trắng), nên không thể so khớp tên tổ chức hay chuỗi watermark; đổi chuỗi watermark không đổi quyết định |

## 9. Hồi quy

Trên commit `7eb737a`. "Trước" = cuối Phase 10 (`0d404f0`).

| Kiểm tra | Trước | Sau | Ghi chú |
|---|---|---|---|
| `pytest tests/` (backend, toàn bộ) | 1.562 đạt · 10 lỗi · 48 bỏ qua | **1.665 đạt · 10 lỗi · 64 bỏ qua** | +103 test mới. 10 lỗi là **đúng 10 lỗi có sẵn** của baseline `v1.1.0-rc.1` (so danh sách: giống hệt), không liên quan OCR. +16 bỏ qua = test pipeline thật, chỉ chạy khi `OCR_FULL_PIPELINE=1` |
| `pytest tests/ -k ocr` | 556 đạt | **572 đạt**, 0 lỗi | Không test OCR cũ nào bị sửa trong phase này |
| `ruff check .` | 2 lỗi sẵn có trong `tests/` | như cũ | Mã của phase này: 0 lỗi; `ruff format` sạch |
| `mypy open_notebook api commands` | sạch | **sạch** (113 tệp) | |
| Kiểm tra lệnh trong tài liệu (`check_doc_commands.py`) | đạt | **đạt** (83 khối lệnh, 38 tệp) | |
| Frontend, API, `pyproject.toml`, `uv.lock`, `Dockerfile` | — | **không đổi** (0 tệp khác so với `0d404f0`) | Không chạy lại test frontend vì không có thay đổi |
| Build image `chatbot5400:agri-test` | đạt | **đạt** (từ `7eb737a`) | Đang chạy trên stack thử nghiệm |
| Docker acceptance của dự án (`scripts/ocr/docker-acceptance.sh`, nâng cấp từ `v1.1.0-rc.1`, online → offline → restart → update; kịch bản `rapidocr` + `tesseract_best`) | 53 PASS · 0 FAIL | **53 PASS · 0 FAIL · 0 NOT VERIFIED** (`EXIT=0`) | Cùng đúng 53 kiểm tra như lần chạy Phase 10. Chạy với cấu hình mặc định (cờ **tắt**) trên project và thư mục tạm riêng; image tạm đã xoá |
| Model Agri trên stack thử nghiệm sau các lần tạo lại container | v1 `offline_ready` | **v1 đang kích hoạt, `offline_ready`**, SHA-256 không đổi | |

Vì cờ mặc định tắt, đường mã của mọi engine khi không bật cờ là đường cũ: `decide_ocr_mode` trả về ngay, không mở tệp,
không ghi log, không thêm metadata (có test). Docker acceptance ở trên chạy đúng trạng thái đó.

**Dữ liệu kiểm thử còn lại trên stack thử nghiệm.** Các lượt kiểm thử qua API tạo 7 sổ tay tên bắt đầu bằng
"Phase 10G …" (3 "auto full page", 4 "RapidOCR default route") chỉ chứa PDF tổng hợp; chúng được giữ lại để chủ dự án
xem kết quả trên giao diện và có thể xoá bất cứ lúc nào. Cấu hình OCR của stack được trả về đúng như lúc bàn giao sau
mỗi lượt (engine Tesseract Vietnamese Agri, Force Full Page tắt); không có thay đổi nào khác trong cơ sở dữ liệu thử
nghiệm.

## 10. Production

Đối chiếu chỉ-đọc thư mục và container production với mốc ghi trước Phase 10 — lần cuối sau mọi kiểm thử và lần dựng
image cuối của phase này:

| Hạng mục | Kết quả so với mốc |
|---|---|
| Git HEAD và trạng thái working tree | giống hệt |
| Container ứng dụng và container cơ sở dữ liệu | cùng container, cùng image, cùng thời điểm khởi động — **không restart** |
| Các tệp cấu hình của production | mã băm giống hệt |
| Sức khỏe API và giao diện | đạt |
| Cổng đang nghe | giống hệt; stack thử nghiệm vẫn chỉ nghe trên loopback |
| Danh sách image trên máy | cùng tên và cùng id như mốc (ngoài image của stack thử nghiệm); hai image tạm của Docker acceptance đã xoá |
| Cờ `OCR_AUTO_FULL_PAGE_ON_WATERMARK` | **không có** trong cấu hình và biến môi trường của container production |

Không có lệnh nào ghi vào thư mục, cơ sở dữ liệu, volume hay container production. Tài liệu trong production không
được đọc. Không merge, không push, không tạo release.

## 11. Danh sách tệp thay đổi

| Tệp | Thay đổi |
|---|---|
| `open_notebook/ocr/pdf_prep.py` | Đo trang (`overlay_scan`), quyết định chế độ (`decide_ocr_mode`), cờ và ngưỡng |
| `open_notebook/ocr/docling_extract.py` | Áp dụng chế độ hiệu lực trong `convert_document`; ngoại lệ định tuyến cho đường RapidOCR mặc định; dòng log |
| `tests/test_ocr_auto_full_page.py` | 103 test đơn vị (mới) |
| `tests/test_ocr_auto_full_page_pipeline.py` | Test pipeline thật, có điều kiện (mới) |
| `scripts/ocr/generate_overlay_fixtures.py` | Bộ sinh PDF tổng hợp, tự ghi PDF, không cần thư viện ngoài (mới) |
| `scripts/ocr/overlay_calibration.py` | Phép đo hiệu chuẩn trước / sau (mới) |
| `deploy/agri-test/docker-compose.yml` | Khai báo cờ cho stack thử nghiệm. Từ Phase 10H mặc định trong tệp là **tắt**; stack thử nghiệm bật bằng `.env` riêng (không commit) |
| `docker-compose.yml`, `.env.example` | Chỉ thêm dòng chú thích mô tả cờ (không bật) |
| `docs/ocr/DECISIONS.md` (D-33), `OCR_CONFIGURATION.md`, `OCR_OPERATOR_GUIDE.md`, `OCR_AGRI_MODEL_GUIDE.md`, `OCR_ROLLBACK.md`, báo cáo này | Tài liệu |

Không đổi: Docling, Content Core, mọi model OCR, `pyproject.toml`, `uv.lock`, `Dockerfile`, frontend, lược đồ cơ sở
dữ liệu, API. Không có PDF hay dữ liệu nghiệp vụ nào trong kho mã: fixture được sinh lúc chạy test.

Commit (chỉ cục bộ, chưa push), cả hai nằm sau `0d404f0` (cuối Phase 10): `7eb737a` — toàn bộ mã, test, cấu hình và
tài liệu vận hành của phase · commit tài liệu chứa báo cáo này và ghi chú rollback.

**Bản build dùng cho từng phép đo.** Trong phase này image `chatbot5400:agri-test` được dựng ba lần. Bản thứ hai và
bản cuối có mã chạy giống hệt nhau (hai cây mã nguồn chỉ khác một tệp test); bản thứ nhất chưa có điều kiện "đầy hơn
trống" và còn ghi thông báo lỗi kèm đường dẫn tệp — quyết định của nó trên toàn bộ 38 PDF hiệu chuẩn giống hệt bản cuối,
nên đường chuyển đổi cũng giống hệt.

| Phép đo | Chạy trên |
|---|---|
| Hiệu chuẩn 38 PDF × 3 chế độ (mục 4–5) | máy phát triển, mã của bản dựng thứ nhất |
| 4 PDF bổ sung (mục 5), test pipeline thật (mục 8) | máy phát triển, mã chạy cuối |
| Hồi quy backend, lint, kiểm tra kiểu (mục 9) | commit `7eb737a` |
| Năm engine trong container, đo ô OCR / recall / CER (mục 6.2) | bản dựng thứ nhất |
| Quyết định trên 42 PDF tổng hợp trong container | bản dựng cuối (từ `7eb737a`) — giống hệt máy phát triển |
| Năm engine qua API + worker, các kiểm thử cài đặt (mục 6) | bản dựng cuối (đã chạy trên cả ba bản, kết quả giống nhau) |
| Đường RapidOCR mặc định, cờ bật / tắt (mục 6.2) | bản dựng thứ hai (đã chạy cả trên bản thứ nhất, kết quả giống nhau) |
| Tài liệu thật (mục 7) | bản dựng cuối (đã chạy trên cả ba bản, mã băm kết quả giống nhau) |
| Benchmark Phase 10E chạy lại (mục 6.1) | bản dựng thứ hai |
| Docker acceptance (mục 9) | image tạm dựng từ mã chạy cuối |

## 12. Bật, tắt và rollback

Cờ **mặc định tắt** — trong ứng dụng và, từ Phase 10H, trong mọi tệp compose của kho mã. Stack thử nghiệm bật nó
bằng dòng `OCR_AUTO_FULL_PAGE_ON_WATERMARK=true` trong `.env` riêng của stack (không commit).

Tắt để trở về hoàn toàn hành vi trước Phase 10G (không cần build lại image):

```bash
cd /srv/example/chatbot5400-agri-test/deploy/agri-test
sed -i 's/^OCR_AUTO_FULL_PAGE_ON_WATERMARK=.*/OCR_AUTO_FULL_PAGE_ON_WATERMARK=false/' .env
docker compose up -d --no-deps open_notebook
docker compose exec open_notebook sh -c 'echo $OCR_AUTO_FULL_PAGE_ON_WATERMARK'
```

Bật lại: sửa dòng đó thành `true` rồi chạy lại lệnh `up -d --no-deps open_notebook`.

Khi cờ tắt: không tệp nào được phân tích, không có dòng `OCR mode`, metadata nguồn không có trường mới, mọi tài liệu
đi đúng đường cũ. Tài liệu đã xử lý trước đó không tự đổi — muốn có kết quả mới thì xử lý lại nguồn.

Rollback mã: tính năng nằm trọn trong các commit sau `0d404f0` (cuối Phase 10); `git revert` các commit đó, hoặc dùng
lại image trước đó, đưa mã về trạng thái Phase 10 mà không ảnh hưởng dữ liệu (không có migration, không có dữ liệu mới).

Trên production trong phase này: **không bật**. Compose production không đặt biến này nên kể cả khi mã được triển
khai, hành vi vẫn như cũ cho tới khi chủ dự án quyết định bật.

## 13. Giới hạn

1. **PDF hỗn hợp** không được sửa (mục 6.3).
2. **Watermark ngang cỡ lớn**: bbox khít chữ nên không được phát hiện; mất 3,3 điểm phần trăm số từ ở PDF tổng hợp
   (chỉ các dòng nằm trong dải chữ watermark).
3. **Khung bao nghiêng chiếm dưới 2% trang**: không kích hoạt; mất tối đa khoảng 3 điểm.
4. **Trang văn bản điện tử** được xác định bằng số ký tự hiển thị thông thường (≥ 400). Trang scan mang rất nhiều
   chữ hiển thị do phần mềm thêm vào (trên ngưỡng này và nhiều hơn lớp ẩn) sẽ bị coi là trang văn bản và không kích
   hoạt; chỉnh bằng `OCR_AUTO_FULL_PAGE_TEXT_PAGE_CHARS`. Điều kiện "đầy hơn trống" cho chữ nghiêng được kiểm ở độ
   lệch 1,5° – 8°; lớp văn bản hiển thị nghiêng nhiều hơn, hoặc ít ký tự hơn lớp ẩn, vẫn có thể bị coi là lớp phủ.
5. **Nguồn từ URL** với cấu hình RapidOCR mặc định do Content Core tự tải và xử lý, không qua bước này. Với bốn engine
   còn lại, nguồn URL được tải về rồi đi qua cùng hàm `convert_document` nên quy tắc được áp dụng (theo mã nguồn; không
   kiểm thử đầu-cuối vì URL ingestion đang tắt theo D-29).
6. Ngưỡng được hiệu chuẩn trên PDF tổng hợp và **một** tài liệu thật. Nên kiểm thêm trên các mẫu tài liệu khác của đơn
   vị (dòng log `OCR mode` cho biết từng tệp được xử lý thế nào mà không lộ nội dung).
7. Chế độ toàn trang bỏ qua mọi text của PDF trên tài liệu được kích hoạt, kể cả lớp OCR ẩn có sẵn. Trên tài liệu
   thật lớp ẩn chỉ trùng 36–38% số từ với Tesseract nên không phải mất mát đáng kể, nhưng đây là thay đổi có chủ đích.
8. Nên báo lỗi lên dự án Docling: tiêu chí giao bbox thẳng trục khiến một ô text xoay loại gần hết ô OCR của trang.
   Khi Docling sửa, cờ này có thể tắt.
9. *(Bổ sung ở Phase 10H.)* Watermark được ghi **mỗi ký tự một đối tượng text** không được phát hiện: quy tắc đo theo
   đối tượng text của PDF, còn Docling ghép các ký tự thành dòng. Hướng an toàn — tài liệu được xử lý như trước.
10. *(Bổ sung ở Phase 10H.)* Bước đo có giới hạn (2.000 trang; 20.000 đối tượng và 100.000 ký tự mỗi trang; 20 giây):
    tài liệu vượt giới hạn giữ chế độ đã cấu hình, lý do `check_failed`. Trang xoay (`/Rotate`) và trang có page box
    không bắt đầu ở (0, 0) từ Phase 10H được đo đúng (trước đó quy tắc có thể không áp dụng trên các trang này).
