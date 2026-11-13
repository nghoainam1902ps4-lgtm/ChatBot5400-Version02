# Phân tích nguyên nhân 15 bài full pipeline thất bại ở Phase 8B (Phase 8C.1)

Cập nhật: 2026-11-13 · Branch `local/ocr-phase8c` · Baseline: commit `f172645` (cuối Phase 8B)

Tài liệu này trả lời: dữ liệu bị sai hoặc bị mất **ở bước nào**, và lỗi thuộc nhóm nào. Cách sửa và
số đo sau sửa nằm ở [OCR_QUALITY_OPTIMIZATION.md](OCR_QUALITY_OPTIMIZATION.md) và
[OCR_QUALITY_BENCHMARK.md](OCR_QUALITY_BENCHMARK.md).

## 1. Cách tái hiện baseline

Baseline được đo lại trên đúng mã Phase 8B (git worktree của `f172645`), cùng môi trường Python và
cùng model, không sửa gì:

```bash
git worktree add --detach ../baseline-8b-src f172645
uv run python scripts/ocr/quality_eval.py --src ../baseline-8b-src \
    --engine tesseract_best --dir tests/fixtures/ocr --out baseline/fixtures-tesseract_best.json
```

Bằng chứng: `evidence/phase8c/baseline/fixtures-<engine>.{json,txt}` (số đo + markdown nhận dạng
được của từng fixture), `evidence/ocr-acceptance.run1.json` (kết quả 48 bài của Phase 8B).

Phiên bản: Docling 2.129.0 · RapidOCR 3.9.2 (torch) · EasyOCR 1.7.2 · Tesseract 5.5.0 ·
PyTorch 2.14.0 · Layout Heron + TableFormer accurate.

## 2. Bộ fixture

Cả 7 PDF là dữ liệu tổng hợp, sinh bởi `scripts/ocr/generate_acceptance_fixtures.py`. Không sửa
fixture, không sửa ground truth, không đổi ngưỡng.

| Fixture | Trang | Khổ / DPI | Lớp text | Bảng | Ghi chú |
|---|---|---|---|---|---|
| `vb_text` | 1 | A4 | có | 0 | PDF sinh từ phần mềm |
| `bang_gop_text` | 1 | A4 | có | 1 | bảng 6×5 có ô gộp |
| `vb_scan` | 1 | A4, 150 DPI (1241×1754 px, JPEG) | không | 0 | công văn scan |
| `vb_xoay_scan` | 1 | như trên, xoay 90° | không | 0 | trang nằm ngang |
| `bang_gop_scan` | 1 | A4, 150 DPI | không | 1 | bảng 6×5, tiêu đề 2 tầng, ô gộp |
| `nhieu_trang_scan` | 2 | A4, 150 DPI | không | 1 | công văn + bảng |
| `hon_hop` | 1 | A4; ảnh bảng 149,9 DPI nhúng trong trang có text | một phần | 1 | text + ảnh |

Ngưỡng nghiệm thu (không đổi): recall trường khóa (số tiền, ngày, số hiệu) ≥ 1,0 (Tesseract Best),
≥ 0,9 (Tesseract Fast, EasyOCR), ≥ 0,8 (RapidOCR, chỉ trường số); CER ≤ 0,08 / 0,10 / 0,15; các cụm
từ theo thứ tự đọc phải xuất hiện **đúng từng dấu**; mỗi dòng bảng phải khớp đủ nhãn và các ô; phải
nhận ra ô tiêu đề gộp.

## 3. Phân nhóm lỗi

| Nhóm | Ý nghĩa |
|---|---|
| A | Cấu hình ChatBot5400 |
| B | Tích hợp Docling |
| C | OCR engine hoặc model |
| D | Tiền xử lý / render ảnh |
| E | Nhận diện hướng trang |
| F | Lọc theo confidence |
| G | Layout/TableFormer, hoặc OCR làm hỏng bảng |
| H | Thứ tự đọc |
| I | Fixture hoặc ground truth |
| J | Giới hạn cố hữu của model |

## 4. Từng bài thất bại

Số đo là của baseline Phase 8B, đo lại trong Phase 8C. "Bước sai" là bước đầu tiên trong chuỗi
*engine độc lập → OCR stage của Docling → full pipeline → Markdown* mà dữ liệu bị sai hoặc mất.

| # | Engine – fixture | Assertion thất bại | CER | WER | Word recall | Trường khóa (tiền / ngày / số hiệu) | Bảng | Nhóm | Bước sai |
|---|---|---|---|---|---|---|---|---|---|
| 1 | rapidocr – vb_xoay_scan | recall trường số 0,33 < 0,8 | 0,558 | 0,835 | 0,22 | 1,00 / 0,33 / 0,00 | – | E, J | engine: không đọc được dòng chữ xoay 90° |
| 2 | tesseract_fast – bang_gop_scan | recall 0 < 0,9 | 0,710 | 1,083 | 0,10 | 0 / 0 / – | 6×5, 0/4 dòng | **E**, D | OCR stage: crop bảng bị xoay 180° |
| 3 | tesseract_fast – hon_hop | thiếu dòng bảng | 0,121 | 0,209 | 0,85 | 0,88 / 1 / 1 | 5×5, 3/4 dòng | D, G | OCR stage: sai chữ số trong ô → TableFormer gộp dòng |
| 4 | tesseract_fast – nhieu_trang_scan | recall 0,22 < 0,9 | 0,261 | 0,364 | 0,70 | 0,11 / 0,43 / 0,50 | 6×5, 0/4 dòng | **E**, D | như #2 (trang 2) |
| 5 | tesseract_fast – vb_scan | recall 0,83 < 0,9 | 0,008 | 0,029 | 0,97 | 1 / 1 / 0,50 | – | D, C | OCR stage: sai một số hiệu ở ảnh phóng 150 → 216 DPI |
| 6 | tesseract_fast – vb_xoay_scan | recall 0 | 0,830 | 1,000 | 0,02 | 0 / 0 / 0 | – | **E** | OCR stage: OSD trên crop sai hướng |
| 7 | tesseract_best – bang_gop_scan | recall 0 < 1,0 | 0,685 | 0,979 | 0,10 | 0 / 0 / – | 6×5, 0/4 dòng | **E**, D | như #2 |
| 8 | tesseract_best – hon_hop | recall < 1,0 (Phase 8B) | 0,053 | 0,088 | 0,96 | 1 / 1 / 1 (đo lại) | 6×5, 4/4 | D | không tái hiện ổn định, xem §5.4 |
| 9 | tesseract_best – nhieu_trang_scan | recall 0,35 < 1,0 | 0,259 | 0,331 | 0,71 | 0,11 / 0,43 / 1 | 6×5, 0/4 dòng | **E**, D | như #2 (trang 2) |
| 10 | tesseract_best – vb_xoay_scan | recall 0 | 0,824 | 0,990 | 0,02 | 0 / 0 / 0 | – | **E** | như #6 |
| 11 | easyocr – bang_gop_scan | recall 0,33 < 0,9 | 0,591 | 0,729 | 0,29 | 0 / 1 / – | 6×**4**, 0/4 | **F**, J | OCR stage: Docling bỏ dòng confidence < 0,5; phần còn lại engine đọc sai số |
| 12 | easyocr – hon_hop | thiếu cụm từ theo thứ tự | 0,087 | 0,143 | 0,97 | 1 / 1 / 1 | 6×5, 2/4 | J | engine: sai dấu trong tiêu đề và nhãn dòng |
| 13 | easyocr – nhieu_trang_scan | recall 0,28 < 0,9 | 0,754 | 0,868 | 0,15 | 0 / 0,71 / 0 | 6×**4**, 0/4 | **F**, J | như #11 |
| 14 | easyocr – vb_scan | recall 0,17 < 0,9 | 0,848 | 0,932 | 0,07 | 0 / 0,33 / 0 | – | **F**, J | như #11 |
| 15 | easyocr – vb_xoay_scan | recall 0 | 0,933 | 1,000 | 0,00 | 0 / 0 / 0 | – | E, F, J | engine: không đọc được trang xoay 90° |

Không bài nào thuộc nhóm A (cấu hình), H (thứ tự đọc) hay I (fixture/ground truth). Layout Heron và
TableFormer nhận đúng hình dạng bảng 6×5 trong mọi trường hợp OCR trả đủ chữ; chỗ bảng sai (5×5,
6×4) đều là hệ quả của chữ OCR bị thiếu hoặc sai (nhóm G theo nghĩa "OCR ảnh hưởng lên bảng").

## 5. Bằng chứng cho từng nguyên nhân

### 5.1. Tesseract: dò hướng trên từng crop (nhóm E) — 7 bài

Mã Docling 2.129 (`models/stages/ocr/tesseract_ocr_cli_model.py`):

- OCR chạy trên **từng vùng layout** (`OcrMode.DEFAULT` = `PDF_AWARE_LAYOUT_REGIONS`), không phải cả
  trang. Với `bang_gop_scan` có 2 crop: tiêu đề 642×96 px và bảng 1590×543 px (scale 3 = 216 DPI).
- Với mỗi crop, Docling gọi `tesseract --psm 0 -l osd <crop> stdout`, đọc `Orientation in degrees`
  và **xoay crop theo giá trị đó mà không xét `Orientation confidence`**. Không có tùy chọn chính
  thức nào để tắt bước này hoặc đặt ngưỡng (`TesseractCliOcrOptions` chỉ có `lang`, `path`,
  `tesseract_cmd`, `psm`, `scale`, `mode`; `psm` chỉ áp cho lệnh nhận dạng).
- Crop được lưu PNG không có metadata độ phân giải, nên Tesseract báo
  `Invalid resolution 0 dpi. Using 70 instead`.

Số đo trên crop bảng của `bang_gop_scan`: OSD trả 180°, confidence 0,16 → bảng bị lật ngược, mọi ô
thành rác. Trang xoay: OSD trên các crop trả 90° với confidence 0,02.

Khảo sát 67 crop thật lấy từ pipeline × 4 hướng xoay × 5 mức lề (1 340 phép đo,
`evidence/phase8c/experiments-session1/osdstudy.json`):

| Lề trắng | Có trả lời | Đúng | Sai | Confidence cao nhất của câu sai |
|---|---|---|---|---|
| 0 px | 182 / 268 | 144 | 38 | 1,41 |
| 30 px | 182 / 268 | 141 | 41 | 1,41 |
| 60 px | 182 / 268 | 143 | 39 | 1,44 |
| 100 px | 182 / 268 | 139 | 43 | 0,98 |
| 150 px | 182 / 268 | 140 | 42 | 0,98 |

Hai kết luận: (1) **lề trắng không làm OSD trên crop đáng tin hơn** — kết quả "lề 60 px sửa được"
của Phase 8B chỉ đúng với hai mẫu đã thử, không tổng quát; (2) mọi câu trả lời sai đều có confidence
≤ 1,44, nên một ngưỡng confidence tách được sai khỏi đúng. Trong 45 crop đứng thẳng có trả lời, 10
crop (22 %) bị xoay sai nếu không có ngưỡng.

Trên **cả trang** thì OSD đáng tin: 384 phép đo trang (32 trang × 4 hướng × 3 scale, 372 có trả lời;
`evidence/phase8c/preflight/pagestudy.json`): ở scale 3 có 4 câu sai với confidence ≤ 0,66, mọi câu
đúng có confidence ≥ 4,77.

### 5.2. Tesseract: độ phân giải render (nhóm D) — góp phần vào #2–#5, #7–#9

- Docling render crop ở 72 × `scale` DPI (mặc định 216 DPI). Ảnh scan 150 DPI bị **phóng lên 1,44
  lần** bằng bộ render của Docling (mềm hơn pdfium: gradient trung bình 1,44 so với 1,71). Dấu tiếng
  Việt và chữ số nhỏ bị nhòe.
- Đặt `scale` bằng độ phân giải thật của ảnh scan (150 DPI → 2,0833, không nội suy) cho bảng đúng
  4/4 dòng; để scale 3 thì còn 3/4 (Best) hoặc 1/4 (Fast). Bảng số ở
  [OCR_QUALITY_BENCHMARK.md](OCR_QUALITY_BENCHMARK.md) §3.
- `user_defined_dpi` (bất kỳ giá trị hợp lý nào: 150 / 216 / 300 cho kết quả giống nhau) loại bỏ
  cảnh báo 70 DPI và làm phân đoạn bảng ổn định.

### 5.3. Tesseract: tiêu đề in đậm "BẢNG KÊ" (nhóm J) — lộ ra sau khi sửa 5.1 và 5.2

Sau khi bảng và hướng trang đã đúng, 5 bài Tesseract vẫn thất bại ở đúng một chỗ: tiêu đề
`BẢNG KÊ CHI TIẾT KHOẢN MỤC MẪU` bị đọc thành `BANG KE CHI TIẾT KHOẢN MỤC MẪU` (hoặc `… MAU`).
Assertion đòi cụm từ này xuất hiện đúng từng dấu.

So sánh bốn bước (ảnh `bang_gop_scan`, `evidence/phase8c/` — lệnh ở OCR_QUALITY_OPTIMIZATION §2.5):

| Bước | Kết quả đọc tiêu đề |
|---|---|
| Tesseract độc lập, ảnh gốc 150 DPI, `best/vie+best/eng` | `BANG KE … MAU` — **sai ngay ở engine** |
| Tesseract độc lập, ảnh gốc 150 DPI, `best/vie` | `BẰNG KÊ …` — sai kiểu khác |
| Tesseract độc lập, ảnh gốc 150 DPI, `fast/vie+fast/eng` | đúng |
| Tesseract độc lập, pdfium phóng 216 DPI (mọi model) | đúng |
| Đúng crop Docling gửi (642×96 px, 216 DPI, render của Docling), Best | `BANG KE …` |
| Docling `OcrMode.FULL_PAGE`, scale 2,08 / 3,0, Best | `BANG KE …` |
| Docling scale 2,25 → 4,17, ảnh 150 / 300 DPI thật, Best và Fast | `BANG KE …` hoặc `BẰNG KE …` |

Tức là model Best đọc sai chữ hoa in đậm có dấu chồng (Ả, Ê, Ẫ) của font DejaVu Sans Bold cỡ ~9,6 pt
ngay trên ảnh gốc; kết quả chỉ đúng với một kiểu nội suy cụ thể mà Docling không tạo ra. Không tùy
chọn chính thức nào (scale, PSM, mode, DPI) sửa được. Đây là **giới hạn của model với mẫu chữ này**,
không phải lỗi tích hợp. Cùng bảng đó nhúng trong `hon_hop` thì Best đọc đúng ở scale ≥ 2,25 —
cho thấy kết quả nằm sát ngưỡng.

Trên tập holdout (font serif, tiêu đề khác) hiện tượng này được đo riêng, xem
[OCR_QUALITY_BENCHMARK.md](OCR_QUALITY_BENCHMARK.md) §2.

### 5.4. Bài #8 (tesseract_best – hon_hop)

Phase 8B ghi thất bại ở assertion recall trường khóa. Đo lại baseline trong Phase 8C cho recall
1,00 / 1,00 / 1,00 và bảng 4/4 dòng. Chưa xác định được vì sao hai lượt khác nhau (cùng mã, cùng
model); khả năng cao nhất là OSD trên crop nằm sát ngưỡng nên kết quả phụ thuộc bbox layout của từng
lượt. Ghi nhận là **không tái hiện ổn định**; sau Phase 8C bài này thất bại ở tiêu đề (mục 5.3).

### 5.5. EasyOCR: ngưỡng confidence (nhóm F) và chất lượng nhận dạng (nhóm J) — 5 bài

Docling (`easyocr_model.py`) gọi `reader.readtext(im)` **không tham số** và chỉ giữ dòng có
`confidence >= options.confidence_threshold` (mặc định 0,5). Tùy chọn chính thức của
`EasyOcrOptions`: `lang`, `use_gpu`, `confidence_threshold`, `model_storage_directory`,
`recog_network`, `download_enabled`, `scale`, `mode`. Decoder, beam width, contrast, text/low-text
threshold **không** truyền được qua API chính thức.

Phân tích từng dòng EasyOCR trả về (`evidence/phase8c/experiments-session1/easy/`, `easy_lines.py`;
"tốt" = sai ≤ 10 % ký tự so với ground truth, "rác" = sai > 30 %), `vb_scan` 150 DPI:

| Ngưỡng | Dòng giữ | Dòng bị bỏ (tốt / đúng một phần / rác) | CER | Word recall |
|---|---|---|---|---|
| 0,5 (mặc định Docling) | 5 / 15 | 2 / 8 / 0 | 0,848 | 0,07 |
| 0,4 | 7 / 15 | 2 / 6 / 0 | 0,793 | 0,10 |
| 0,3 | 12 / 15 | 0 / 3 / 0 | 0,385 | 0,33 |
| 0,2 | 15 / 15 | 0 / 0 / 0 | 0,160 | 0,43 |
| 0,0 | 15 / 15 | 0 / 0 / 0 | 0,160 | 0,43 |

- **Nhóm F (Docling bỏ dòng):** ở ngưỡng 0,5, 10/15 dòng bị bỏ và không dòng nào là rác. Đây là
  nguyên nhân CER 0,85.
- **Nhóm J (engine đọc sai):** kể cả giữ hết dòng, ở 150 DPI word recall chỉ 0,43 và recall số tiền
  0: EasyOCR đọc `1.250.000.000` thành `1.250,000,000`, `18.750.000` thành `18,750 000`. Ở ảnh
  200 DPI thật: CER 0,12, word recall 0,77, số tiền 1,00 nhưng số hiệu (cần dấu `QĐ-MẪU`) vẫn 0.
  `scale` 2,08 / 3 / 4,17 / 5 không cải thiện (`evidence/phase8c/easyocr-scale/`).
- Trang xoay: dưới ngưỡng 0,2 là các dòng rác do đọc chữ nằm ngang; EasyOCR không tự xử lý trang
  xoay 90°.

### 5.6. RapidOCR: trang xoay (nhóm E, J) — 1 bài

RapidOCR 3.9.2 có bộ phân loại hướng (`use_cls`, model PP-OCRv4 cls) nhưng bộ này chỉ phân biệt dòng
chữ **0° / 180°** sau khi detector đã tìm ra dòng; nó không xử lý trang xoay 90° / 270°. Docling
không dò hướng trang cho RapidOCR. `vb_xoay_scan`: word recall 0,22, ngày 0,33.

Ngoài ra RapidOCR (model PP-OCR mặc định, không có bảng ký tự tiếng Việt) mất dấu trên mọi trang
scan (độ chính xác dấu 0,18–0,43). Đây là giới hạn đã biết từ Phase 7, bài test chỉ kiểm trường số
nên các bài đó vẫn PASS.

## 6. Tổng hợp

| Nguyên nhân gốc | Nhóm | Bài | Sửa được trong phạm vi cho phép? |
|---|---|---|---|
| Docling xoay crop theo OSD bất kể confidence | E (B) | #2, #4, #6, #7, #9, #10 | Có — D-25 |
| Không dò hướng ở cấp trang | E | #1, #6, #10, #15 | Có — D-25 |
| Phóng ảnh 150 → 216 DPI, PNG không có DPI | D | #3, #5 và góp phần #2, #4, #7, #9 | Có — D-25 |
| Docling bỏ dòng EasyOCR có confidence < 0,5 | F | #11, #13, #14 | Có một phần — D-26 |
| EasyOCR đọc sai số / dấu ở 150 DPI | J | #11–#15 | Không |
| Tesseract đọc sai dấu tiêu đề in đậm | J | lộ ra ở #2, #4, #7, #8, #9 sau khi sửa | Không |
| RapidOCR không có dấu tiếng Việt | J | (không làm FAIL) | Không |
