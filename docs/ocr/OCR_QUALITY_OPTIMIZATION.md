# Tối ưu chất lượng OCR (Phase 8C)

Cập nhật: 2026-11-13 · Branch `local/ocr-phase8c` · Quyết định: [D-25, D-26](DECISIONS.md)

Nguyên nhân gốc của từng lỗi: [OCR_FAILURE_ANALYSIS.md](OCR_FAILURE_ANALYSIS.md).
Số đo trước/sau và holdout: [OCR_QUALITY_BENCHMARK.md](OCR_QUALITY_BENCHMARK.md).

## 1. Thay đổi đã triển khai

| # | Thay đổi | Áp dụng cho | Cơ chế | Tắt bằng |
|---|---|---|---|---|
| 1 | Bỏ qua kết quả dò hướng có độ tin cậy thấp trên từng vùng OCR | Tesseract Fast, Best | `tesseract_gate.py` đặt qua tùy chọn chính thức `TesseractCliOcrOptions.tesseract_cmd` | `OCR_TESSERACT_OSD_GATE=false` |
| 2 | Dò hướng **cả trang** scan và sửa `/Rotate` trong bản sao tạm | mọi engine (khi có `osd.traineddata`) | `pdf_prep.py` (pypdfium2 + `tesseract --psm 0`) | `OCR_PDF_PREP=false` |
| 3 | Scale render OCR theo độ phân giải thật của ảnh scan | Tesseract Fast, Best | tùy chọn chính thức `OcrOptions.scale` | `OCR_PDF_PREP=false` |
| 4 | Khai báo độ phân giải cho Tesseract | Tesseract Fast, Best | `user_defined_dpi 216` trong file config `tsv` của thư mục tessdata riêng | — |
| 5 | Ngưỡng confidence 0,2 thay cho 0,5 | EasyOCR | tùy chọn chính thức `EasyOcrOptions.confidence_threshold` | `OCR_EASYOCR_CONFIDENCE=0.5` |

Không đổi: Layout Heron, TableFormer accurate, `DocumentConverter`, PDF backend, model của cả 4 lựa
chọn, dependency lock, RapidOCR backend torch, luồng xử lý source, readiness, bảo mật job. Không sửa
Docling, Content Core hay site-packages; không monkey patch; không subclass `BaseOcrModel`.

Mọi biến môi trường ở trên là cấu hình **toàn deployment**, đọc khi dựng options; không có biến nào
đổi theo từng job.

## 2. Tesseract

### 2.1. Docling 2.129 làm gì

Đọc từ `docling/models/stages/ocr/tesseract_ocr_cli_model.py` và `base_ocr_model.py`:

- Vùng OCR: `OcrMode.DEFAULT` = `PDF_AWARE_LAYOUT_REGIONS` — bbox của từng cluster layout, trừ cluster
  chỉ chứa text PDF. `FULL_PAGE` OCR cả trang; `LAYOUT_REGIONS` không trừ text PDF.
- Render: `page._backend.get_page_image(scale=options.scale, cropbox=rect)`, mặc định scale 3
  (216 DPI), lưu PNG **không** có metadata DPI.
- OSD: với mỗi vùng, `tesseract --psm 0 -l osd <png> stdout`; lấy `Orientation in degrees` rồi
  `image.rotate(-orientation, expand=True)`. `Orientation confidence` không được dùng. Nếu lệnh OSD
  lỗi (ví dụ "Too few characters") và có khai báo ngôn ngữ thì bỏ qua xoay, vẫn OCR.
- Nhận dạng: `tesseract -l <lang> --tessdata-dir <path> [--psm N] <png> stdout tsv`. OEM mặc định
  của Tesseract (LSTM). Tọa độ ô chữ được Docling quy đổi lại theo `scale` và `orientation`.
- Tùy chọn chính thức: `lang`, `path`, `tesseract_cmd`, `psm`, `scale`, `mode`. **Không có** tùy chọn
  tắt OSD, ngưỡng confidence hay lề ảnh.

### 2.2. Thử các tùy chọn chính thức

Trung bình trên 5 fixture scan, 150 DPI; "dòng" = số dòng bảng khớp đủ nhãn và ô
(`evidence/phase8c/experiments-session1/grid/`, đo trước khi có thay đổi 2 và 4 nên CER còn gồm
trang xoay):

| Biến | Giá trị | Best: CER / trường khóa / dòng | Fast: CER / trường khóa / dòng |
|---|---|---|---|
| Baseline (không ngưỡng OSD) | scale 3 | 0,374 / 0,45 / 3 trên 12 | 0,387 / 0,39 / 3 trên 12 |
| Ngưỡng OSD 2,0 | scale 3, PSM mặc định | 0,122 / 0,90 / 9 | 0,124 / 0,82 / 9 |
| PSM | 1, 4 | như mặc định | như mặc định |
| PSM | 6, 11, 12 | 0,28–0,32 / 0,50–0,61 / **0** | 0,28–0,32 / 0,42–0,61 / **0** |
| Mode | `FULL_PAGE` | 0,122 / 0,90 / 9 | 0,129 / 0,81 / 9 |
| Scale | 2,0833 (= 150 DPI) | **0,062 / 1,00 / 10** | **0,064 / 1,00** / 6 |
| Scale | 4 – 4,17 | 0,12–0,14 / 0,80–0,83 / 6 | 0,14–0,15 / 0,80–0,89 / 4–6 |
| Scale | 5 | 0,250 / 0,61 / 0 | 0,248 / 0,58 / 0 |

- PSM mặc định là tốt nhất; PSM 6/11/12 phá bảng. Không đặt `psm`.
- `FULL_PAGE` không tốt hơn vùng layout khi đã có ngưỡng OSD, và sẽ OCR đè lên text layer của PDF
  sinh từ phần mềm → không bật.
- Scale đúng bằng độ phân giải scan cho kết quả tốt nhất; phóng to làm kém đi.

### 2.3. Lề trắng (nghiên cứu, không triển khai)

1 340 phép đo OSD trên crop thật (bảng ở OCR_FAILURE_ANALYSIS §5.1): lề 0 / 30 / 60 / 100 / 150 px cho
38 / 41 / 39 / 43 / 42 câu sai trên 182. **Lề không cải thiện OSD.** Thêm lề cho từng vùng cũng chỉ
làm được bằng adapter riêng hoặc sửa Docling (phải dịch lại tọa độ TSV), nằm ngoài giới hạn. Kết
luận: không dùng lề.

### 2.4. Phương án đã chọn (D-25)

**(1) Ngưỡng OSD trên vùng — `open_notebook/ocr/tesseract_gate.py`.**
`tesseract_cmd` (tùy chọn chính thức của Docling) trỏ tới file này. Nó chỉ làm một việc: với lệnh
`--psm 0`, chạy Tesseract thật, và nếu hướng ≠ 0 mà `Orientation confidence` < 2,0 thì trả về hướng
0. Mọi lệnh khác (`--version`, `--list-langs`, nhận dạng) được `exec` thẳng sang Tesseract thật,
tham số và kết quả nguyên vẹn. Chỉ dùng thư viện chuẩn; không đụng tới ảnh, tọa độ hay văn bản.

Gate chỉ được dùng sau khi `gate --version` chạy được (cần bit thực thi và `python3` trên PATH, có
sẵn trong image Docker); nếu không, ứng dụng gọi thẳng Tesseract và ghi một cảnh báo — OCR không bao
giờ hỏng vì gate.

Ngưỡng 2,0: trên 1 340 phép đo, câu sai có confidence ≤ 1,44; ở ngưỡng 2,0 giữ lại 83–94 câu đúng
và **0** câu sai. Đổi bằng `OCR_TESSERACT_OSD_MIN_CONFIDENCE`.

**(2) Hướng cả trang — `open_notebook/ocr/pdf_prep.py`.**
Trước khi gọi Docling, mỗi trang **scan** (có một ảnh phủ ≥ 50 % trang) được render và dò hướng một
lần trên cả trang. Nếu Tesseract báo trang nằm ngang/ngược với confidence ≥ 2,0, `/Rotate` của trang
được sửa trong một **bản sao tạm**; Docling chuyển đổi bản sao đó.

- File người dùng tải lên không bao giờ bị sửa (unit test so SHA-256 trước/sau).
- Không render lại, không nén lại: nội dung trang, ảnh và text layer là cùng các object; chỉ một số
  nguyên `/Rotate` đổi. Vì vậy tọa độ, bảng và text layer không lệch.
- Trang sinh từ phần mềm (không có ảnh lớn) không bị đụng tới và không tốn thời gian.
- Lỗi bất kỳ (PDF hỏng, có mật khẩu, thiếu pdfium, Tesseract lỗi) → ghi log cảnh báo và chuyển đổi
  file gốc như trước. Bản sao tạm bị xóa ngay sau khi chuyển đổi, kể cả khi lỗi.
- Ngưỡng 2,0: ở scale 3, câu sai có confidence ≤ 0,66, câu đúng ≥ 4,77 (384 phép đo trang). Đổi bằng
  `OCR_PAGE_OSD_MIN_CONFIDENCE`.
- Giới hạn: tối đa 200 trang đầu của mỗi tài liệu (`OCR_PAGE_OSD_MAX_PAGES`), 30 giây mỗi trang; một
  trang lỗi hoặc quá thời gian được bỏ qua, các trang khác không bị ảnh hưởng.
- Cần binary Tesseract và `osd.traineddata` (được cài cùng Tesseract Fast hoặc Best). Thiếu thì bỏ
  qua bước này, không gọi tiến trình nào.

**(3) Scale theo độ phân giải scan.** `scale = max(2,0; DPI_scan / 72)`, và không bao giờ vượt mặc
định 3 của Docling (ảnh ≥ 216 DPI giữ nguyên hành vi cũ). Docling chỉ có một `OcrOptions` cho cả tài
liệu, nên `DPI_scan` là độ phân giải **cao nhất** trong các trang scan: không trang nào bị render thấp
hơn độ phân giải của chính nó hay thấp hơn trước Phase 8C. Truyền qua `OcrOptions.scale`. Chỉ áp cho
Tesseract vì chỉ Tesseract được đo; EasyOCR không lợi (mục 3), RapidOCR giữ nguyên để tương thích.

**(4) `user_defined_dpi 216`** trong `tessdata/configs/tsv` (file do ứng dụng tự ghi từ Phase 3).
Đây là biến cấu hình chuẩn của Tesseract (tương đương `--dpi`). 150 / 216 / 300 cho kết quả giống
nhau; điều quan trọng là có một độ phân giải hợp lệ thay cho 70 DPI.

### 2.5. Giới hạn còn lại của Tesseract

- Tiêu đề in đậm chữ hoa có dấu chồng (`BẢNG KÊ … MẪU`, DejaVu Sans Bold ~9,6 pt) bị model Best đọc
  thành `BANG KE …` **ngay trên ảnh gốc** khi chạy Tesseract độc lập. Tái hiện:

  ```bash
  # trích ảnh trang (150 DPI) rồi chạy Tesseract trực tiếp
  tesseract --tessdata-dir "$OCR_DATA/models/tesseract" -l best/vie+best/eng --dpi 216 page.png stdout
  ```

  Không tùy chọn chính thức nào sửa được (đã thử scale 2,08–5, PSM 1–12, `FULL_PAGE`, DPI 150–300,
  ảnh scan 150/200/300 DPI thật). 5 bài nghiệm thu còn FAIL của Tesseract đều do đúng điểm này.
- Trang vừa có text layer vừa có ảnh scan lớn **và** ảnh đó nằm ngang so với text: `/Rotate` xoay cả
  trang, nên không được sửa (OSD cả trang không đạt ngưỡng). Chưa có fixture cho trường hợp này.
- Chi phí: mỗi trang scan tốn thêm khoảng 1 giây (render + OSD); số đo ở OCR_QUALITY_BENCHMARK §4.

### 2.6. Điểm cần chủ dự án xác nhận

`tesseract_gate.py` không phải OCR adapter (không subclass, không xử lý ảnh, không thay engine) và
không sửa Docling, nhưng nó **đứng giữa Docling và Tesseract** và sửa một dòng trong kết quả OSD. Tôi
coi đây là dùng đúng tùy chọn chính thức `tesseract_cmd`, song vì ranh giới "không viết adapter"
là của chủ dự án nên nêu rõ để quyết định. Nếu không chấp nhận: đặt `OCR_TESSERACT_OSD_GATE=false`
(hoặc xóa file và hàm `tesseract_command`); thay đổi 2–4 vẫn hoạt động độc lập. Khi tắt gate, bảng
scan đứng thẳng lại có thể bị lật 180° (10/45 crop đứng thẳng trong khảo sát).

## 3. EasyOCR (D-26)

- Tùy chọn chính thức có thể chỉnh: `confidence_threshold`, `scale`, `recog_network`, `lang`.
  Docling gọi `readtext(im)` không tham số, nên decoder, beam width, contrast, text threshold,
  low-text threshold **không** chỉnh được qua API chính thức → không dùng.
- Quét ngưỡng 0,0–0,5 trên ảnh 150 và 200 DPI, phân tích từng dòng (OCR_FAILURE_ANALYSIS §5.5):
  - dưới 0,2 chỉ có dòng rác (1 dòng mỗi tài liệu đứng thẳng; nhiều trên trang xoay);
  - từ 0,2 đến 0,5 là dòng tốt hoặc đúng một phần — ở ngưỡng 0,5 `vb_scan` mất 10/15 dòng, không
    dòng nào là rác;
  - kết quả ở 0,0 / 0,1 / 0,2 giống nhau trên trang đứng thẳng.
- **Chọn 0,2**: thấp nhất mà vẫn loại được nhóm dòng rác đã quan sát; không chọn 0 vì khi đó mọi dòng
  rác trên trang xoay/nhiễu đều vào kết quả. Đổi bằng `OCR_EASYOCR_CONFIDENCE` (0–1; giá trị không hợp
  lệ → dùng 0,2). Không thêm vào giao diện Settings: một ngưỡng duy nhất, mặc định đã đo.
- `scale` 2,08 / 3 / 4,17 / 5: không cải thiện, tốn thêm thời gian và RAM → giữ mặc định.
- Chỉ ảnh hưởng EasyOCR.

**Giới hạn:** ở 150 DPI EasyOCR (Latin Gen2) đọc sai chữ số và dấu (`1.250,000,000`,
`18,750 000`), kể cả khi giữ mọi dòng. Ở 200 DPI khá hơn nhiều nhưng số hiệu có dấu vẫn sai. Đây là
giới hạn model; không thay model.

## 4. RapidOCR

- Giữ nguyên: RapidOCR 3.9.2, model PP-OCR hiện tại (det / cls / rec), backend torch, lưu trữ bền
  (D-08, sửa ở Phase 8B). Không đổi sang ONNX.
- Bộ phân loại hướng (`use_cls`) chỉ phân biệt dòng chữ 0° / 180° sau khi detector đã tìm ra dòng;
  không xử lý trang xoay 90° / 270°. Docling không dò hướng trang cho RapidOCR.
- **Tái dùng thay đổi 2:** khi trang được chuẩn hóa hướng trước, RapidOCR đọc `vb_xoay_scan` ngang
  với `vb_scan` (CER 0,558 → 0,136; ngày 0,33 → 1,00) và bài nghiệm thu chuyển sang PASS. Không đổi
  tùy chọn nào của RapidOCR.
- Tương thích ngược: tài liệu đứng thẳng cho kết quả y hệt trước (7 fixture: không số đo nào đổi).
  Trên deployment chưa cài Tesseract Fast/Best thì không có `osd.traineddata`, bước dò hướng không
  chạy và hành vi giống hệt Phase 8B.
- Giới hạn cố hữu: model mặc định không có bảng ký tự tiếng Việt, mất dấu trên trang scan (độ chính
  xác dấu 0,18–0,43). Không sửa được nếu không thay model.

## 5. Tesseract Fast và độ phân giải

- Fixture là ảnh **thật sự** 150 DPI (1241×1754 px cho A4), không phải khai báo sai DPI.
- Docling render ở 216 DPI: ảnh bị phóng 1,44 lần. Lỗi số hiệu của Fast ở Phase 8B (`vb_scan`,
  `QĐ-MẪU`) xuất hiện ở ảnh phóng, không xuất hiện ở scale gốc → nhóm D, sửa bằng thay đổi 3.
- Ma trận ảnh thật 150 / 200 / 300 DPI × scale (cùng nội dung, sinh lại ở độ phân giải khác;
  `evidence/phase8c/experiments-session1/dpi2/`): số dòng bảng đúng cao nhất khi scale khớp độ phân
  giải scan (150 DPI → 2,08; 200 DPI → 2,08–2,78; 300 DPI → 3,0). Phóng ảnh 150 DPI lên 300 DPI
  (scale 4,17) không khôi phục chi tiết: dòng bảng đúng giảm.
- Sau Phase 8C, Fast đạt trường khóa 1,00 trên cả 7 fixture; còn FAIL 2 bài do tiêu đề (mục 2.5).
  Fast vẫn kém Best ở nhãn dòng trong bảng. Không tự chuyển Fast sang Best; không hạ ngưỡng.

## 6. Cấu hình

| Biến môi trường | Mặc định | Ý nghĩa |
|---|---|---|
| `OCR_TESSERACT_OSD_GATE` | bật | `false` = gọi thẳng Tesseract, không lọc OSD |
| `OCR_TESSERACT_OSD_MIN_CONFIDENCE` | `2.0` | ngưỡng confidence OSD trên vùng OCR |
| `OCR_PDF_PREP` | bật | `false` = không dò hướng trang, không chỉnh scale |
| `OCR_PAGE_OSD_MIN_CONFIDENCE` | `2.0` | ngưỡng confidence OSD trên cả trang |
| `OCR_PAGE_OSD_MAX_PAGES` | `200` | số trang scan tối đa được dò hướng trong một tài liệu |
| `OCR_EASYOCR_CONFIDENCE` | `0.2` | ngưỡng confidence dòng của EasyOCR, 0–1 |

Giá trị không hợp lệ (`nan`, số âm, ngoài phạm vi) bị bỏ qua và dùng mặc định.

Biến nội bộ `OCR_TESSERACT_REAL` do ứng dụng tự đặt (đường dẫn Tesseract thật cho gate); cùng giá trị
cho mọi job nên không có tranh chấp giữa các job.

## 7. Metadata và log

`metadata` của source có thêm `ocr_scale`, `scan_dpi`, `rotated_pages` (số trang → số độ đã xoay).
Dòng log `Docling OCR finished` ghi thêm ba giá trị này. Không ghi nội dung văn bản OCR.
