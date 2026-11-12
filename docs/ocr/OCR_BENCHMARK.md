# OCR Benchmark

> Số liệu dưới đây là **đo thực tế** trong Claude Code Cloud ngày 2026-11-12 bằng
> `scripts/ocr/benchmark.py`. Không có số liệu ước đoán. Ô "—" = không áp dụng / không đo được.

## 1. Phạm vi và giới hạn — đọc trước khi dùng số liệu

| Hạng mục | Thực tế |
|---|---|
| Chế độ | **OCR stage thuần** (`--mode ocr-stage`): trang được nạp qua backend PDF + preprocessing của Docling, rồi chạy **chính class OCR của Docling** do `get_ocr_factory()` tạo với options của ChatBot5400, `OcrMode.FULL_PAGE`. |
| Không đo | **Toàn bộ pipeline Docling** (Layout Heron + TableFormer + OCR): Hugging Face bị chặn trong Cloud ⇒ dùng `--mode pipeline` trên máy triển khai (§5). Do đó *độ chính xác bảng biểu theo cấu trúc* **chưa đo**; chỉ đo văn bản trong ảnh bảng. |
| RapidOCR | Cấu hình production dùng backend **torch** (trọng số `.pth` tải từ `modelscope.cn` — bị chặn trong Cloud ⇒ **không đo được**). Hàng "RapidOCR (onnxruntime)" dùng **cùng họ model PP-OCRv6 small** đóng gói sẵn trong wheel `rapidocr` 3.9.2 dạng ONNX, chạy qua overlay `uv run --with onnxruntime` (không cài vào venv dự án). Đây là xấp xỉ gần nhất, **không** phải số liệu của backend torch. |
| Dữ liệu | 8 mẫu **tổng hợp, hư cấu, không nhạy cảm** do `scripts/ocr/generate_samples.py` tạo (font DejaVu Sans, ~200 DPI), có ground truth. Bộ nhỏ ⇒ **không đủ để đổi engine mặc định**. |
| Máy | 4 vCPU, 15 GiB RAM, không GPU; luồng = mặc định Docling (4). |
| Thứ tự đọc | Harness ghép ô OCR theo dòng (trên→dưới, trái→phải). Với trang **xoay**, thứ tự dòng bị đảo ⇒ CER/WER phạt cả thứ tự; xem thêm **Word recall** (không phụ thuộc thứ tự). |

Chỉ số: **CER/WER** (Levenshtein ký tự/từ, sau chuẩn hoá NFC + khoảng trắng),
**Word recall** (tỷ lệ từ ground truth xuất hiện đúng nguyên văn, không phụ thuộc thứ tự),
**Dấu** (trong các từ có dấu tìm thấy, tỷ lệ dấu đúng), **Tiền/Ngày/Số hiệu** (tỷ lệ trường
khoá xuất hiện nguyên văn).

## 2. Kết quả theo mẫu

### Tesseract Vietnamese Fast (`TesseractOcrCliModel`, tessdata_fast 4.1.0)

| Mẫu | CER | WER | Word recall | Dấu | Tiền | Ngày | Số hiệu | s/trang |
|---|---|---|---|---|---|---|---|---|
| scan_cong_van (PNG) | 0.004 | 0.010 | 0.990 | 0.988 | 1.00 | 1.00 | 0.50 | 6.03* |
| scan_cong_van_pdf | 0.000 | 0.000 | 1.000 | 1.000 | 1.00 | 1.00 | 1.00 | 1.93 |
| scan_bang_bieu (bảng) | 0.507 | 0.525 | 0.475 | 1.000 | 0.50 | 0.50 | — | 1.12 |
| scan_nhieu_trang (2 trang) | 0.159 | 0.147 | 0.853 | 0.990 | 0.60 | 0.71 | 1.00 | 1.53 |
| scan_chat_luong_thap | 0.357 | 0.660 | 0.534 | 0.862 | 1.00 | 0.67 | 0.50 | 5.46 |
| scan_xoay (xoay 90°) | 0.805 | 0.971 | 0.981 | 0.976 | 1.00 | 0.67 | 0.50 | 4.77 |
| text_native (PDF có text) | 0.006 | 0.019 | 0.981 | 0.976 | 1.00 | 1.00 | 0.50 | 13.95* |
| hon_hop (text + ảnh) | 0.194 | 0.289 | 0.711 | 0.923 | 0.50 | 0.80 | 1.00 | 6.13 |

### Tesseract Vietnamese Best (`TesseractOcrCliModel`, tessdata_best 4.1.0)

| Mẫu | CER | WER | Word recall | Dấu | Tiền | Ngày | Số hiệu | s/trang |
|---|---|---|---|---|---|---|---|---|
| scan_cong_van (PNG) | 0.000 | 0.000 | 1.000 | 1.000 | 1.00 | 1.00 | 1.00 | 5.97* |
| scan_cong_van_pdf | 0.000 | 0.000 | 1.000 | 1.000 | 1.00 | 1.00 | 1.00 | 2.09 |
| scan_bang_bieu (bảng) | 0.507 | 0.525 | 0.475 | 1.000 | 0.50 | 0.50 | — | 0.97 |
| scan_nhieu_trang (2 trang) | 0.159 | 0.147 | 0.853 | 0.990 | 0.60 | 0.71 | 1.00 | 1.61 |
| scan_chat_luong_thap | 0.343 | 0.680 | 0.485 | 0.758 | 0.00 | 0.33 | 1.00 | 2.90 |
| scan_xoay (xoay 90°) | 0.805 | 0.971 | **1.000** | 1.000 | 1.00 | 0.67 | 1.00 | 2.08 |
| text_native (PDF có text) | 0.000 | 0.000 | 1.000 | 1.000 | 1.00 | 1.00 | 1.00 | 1.94 |
| hon_hop (text + ảnh) | 0.185 | 0.265 | 0.735 | 0.925 | 0.75 | 0.80 | 1.00 | 1.31 |

### EasyOCR Vietnamese (`EasyOcrModel`, craft_mlt_25k + latin_g2, CPU)

| Mẫu | CER | WER | Word recall | Dấu | Tiền | Ngày | Số hiệu | s/trang |
|---|---|---|---|---|---|---|---|---|
| scan_cong_van (PNG) | 0.146 | 0.252 | 0.748 | 0.905 | 1.00 | 1.00 | 0.50 | 17.48 |
| scan_cong_van_pdf | 0.028 | 0.117 | 0.883 | 0.912 | 1.00 | 1.00 | 1.00 | 15.22 |
| scan_bang_bieu (bảng) | **0.009** | 0.050 | **0.950** | 0.917 | 1.00 | 1.00 | — | 6.62 |
| scan_nhieu_trang (2 trang) | 0.022 | 0.098 | 0.902 | 0.913 | 1.00 | 1.00 | 1.00 | 10.18 |
| scan_chat_luong_thap | 0.986 | 1.000 | 0.000 | 0.000 | 0.00 | 0.00 | 0.00 | 14.50 |
| scan_xoay (xoay 90°) | 0.941 | 1.000 | 0.010 | 0.000 | 0.00 | 0.00 | 0.00 | 13.82 |
| text_native (PDF có text) | 0.036 | 0.155 | 0.845 | 0.911 | 1.00 | 1.00 | 1.00 | 13.00 |
| hon_hop (text + ảnh) | 0.357 | 0.410 | 0.590 | 0.975 | 0.25 | 1.00 | 1.00 | 28.98 |

### RapidOCR (onnxruntime, PP-OCRv6 small bundled — xem §1)

| Mẫu | CER | WER | Word recall | Dấu | Tiền | Ngày | Số hiệu | s/trang |
|---|---|---|---|---|---|---|---|---|
| scan_cong_van (PNG) | 0.118 | 0.553 | 0.447 | 0.684 | 1.00 | 1.00 | 0.00 | 4.81 |
| scan_cong_van_pdf | 0.124 | 0.573 | 0.427 | 0.600 | 1.00 | 1.00 | 0.00 | 2.80 |
| scan_bang_bieu (bảng) | 0.093 | 0.525 | 0.475 | 0.667 | 1.00 | 1.00 | — | 2.34 |
| scan_nhieu_trang (2 trang) | 0.114 | 0.559 | 0.441 | 0.571 | 1.00 | 1.00 | 0.00 | 2.63 |
| scan_chat_luong_thap | 0.185 | 0.748 | 0.252 | 0.194 | 1.00 | 1.00 | 0.00 | 1.70 |
| scan_xoay (xoay 90°) | 0.195 | 0.621 | 0.379 | 0.676 | 1.00 | 1.00 | 0.00 | 1.90 |
| text_native (PDF có text) | 0.120 | 0.553 | 0.447 | 0.667 | 1.00 | 1.00 | 0.00 | 1.56 |
| hon_hop (text + ảnh) | 0.141 | 0.590 | 0.410 | 0.367 | 1.00 | 1.00 | 0.00 | 2.89 |

\* Mẫu đầu tiên của mỗi engine bao gồm thời gian khởi động lần đầu của tiến trình OCR; mẫu
`text_native` của Tesseract Fast chạy ngay sau mẫu PNG lớn — thời gian đơn lẻ có nhiễu, nên
so sánh theo trung bình.

Ví dụ lỗi đặc trưng của RapidOCR (model mặc định ch/Latin) — mất chữ cái có dấu phức:
`"CNG HÒA XÃ HI CH NGHÎA VIT NAM"`, `"S: 1234/2024/QD-MÃU"` (gốc: `CỘNG HÒA XÃ HỘI CHỦ NGHĨA
VIỆT NAM`, `Số: 1234/2024/QĐ-MẪU`).

## 3. Tổng hợp tài nguyên

| Engine | Model trên đĩa | Cold start (khởi tạo model) | Tổng thời gian 8 mẫu | RAM đỉnh |
|---|---|---|---|---|
| Tesseract Fast | 15.2 MB (vie 0.5 + eng 4.1 + osd 10.6 dùng chung) | 2.88 s | 51.8 s | ~830 MB tiến trình (gồm Docling/torch import) |
| Tesseract Best | 38.4 MB (vie 12.4 + eng 15.4 + osd 10.6 dùng chung) | 0.02 s | 22.1 s | không tăng thêm so với Fast |
| EasyOCR | 98.6 MB (craft 83.2 + latin_g2 15.4) | 2.02 s | 161.2 s | +3.9 GB so với trước (đỉnh tiến trình ~4.8 GB) |
| RapidOCR (onnx) | ~32 MB (gói `rapidocr`) | 4.08 s | 30.5 s | ~1.4 GB tiến trình (lần chạy riêng) |

RAM là `ru_maxrss` (đỉnh tích luỹ của tiến trình), nên chỉ có ý nghĩa so sánh thô. CPU: tất
cả chạy CPU-only; không đo % CPU riêng từng engine.

## 4. Nhận xét (dựa trên số liệu trên, bộ mẫu nhỏ)

1. **Văn bản hành chính scan sạch** (công văn, quyết định): Tesseract Best đạt CER 0.000 trên
   cả PNG và PDF scan; Tesseract Fast gần như tương đương (CER ≤ 0.004). Dấu tiếng Việt, số
   tiền, ngày tháng, số hiệu văn bản đều đúng nguyên văn.
2. **RapidOCR mặc định** (model ch/Latin) mất hầu hết chữ có dấu phức (ộ, ậ, ự, ữ…): WER ≈
   0.55, số hiệu văn bản `QĐ-MẪU` đọc sai ở mọi mẫu. Đây là nguyên nhân chính của chất lượng
   OCR tiếng Việt kém hiện nay.
3. **Bảng biểu ở chế độ full-page OCR**: EasyOCR tốt nhất (CER 0.009); Tesseract bỏ sót 2/4
   dòng của bảng có kẻ khung. Trong pipeline thật, Layout Heron + TableFormer cắt vùng bảng
   trước khi OCR ⇒ cần đo lại bằng `--mode pipeline`.
4. **Trang xoay 90°**: Tesseract (OSD) nhận dạng đúng gần như toàn bộ từ (word recall 0.98–1.0;
   CER cao chỉ vì thứ tự dòng của harness). EasyOCR và RapidOCR không xử lý được.
5. **Scan chất lượng thấp** (mờ + nhiễu): mọi engine đều kém; EasyOCR thất bại hoàn toàn.
6. **Tốc độ CPU**: Tesseract ~1–2 s/trang PDF; RapidOCR (onnx) ~2–3 s/trang; EasyOCR 7–15 s/trang
   và tốn RAM nhiều nhất.

**Đề xuất (có điều kiện):** với văn bản nghiệp vụ tiếng Việt, **Tesseract Vietnamese Best**
là lựa chọn có bằng chứng tốt nhất trong bộ đo này (chính xác nhất cho văn bản, xử lý trang
xoay, nhanh, ít RAM); cân nhắc **EasyOCR** cho tài liệu nhiều bảng sau khi đo lại bằng pipeline
đầy đủ. **Không tự động đổi engine mặc định** (RapidOCR vẫn mặc định để tương thích ngược);
quản trị viên chọn trong Settings sau khi nghiệm thu trên tài liệu thật (không đưa lên
GitHub).

## 5. Tái lập

```bash
uv run --with reportlab python scripts/ocr/generate_samples.py --out ./data/ocr-samples
uv run python -m open_notebook.ocr.cli install-model tesseract_fast   # và tesseract_best, easyocr
uv run python scripts/ocr/benchmark.py --samples ./data/ocr-samples --mode ocr-stage --out bench.json
# Trên máy triển khai (có model Docling Layout/TableFormer):
uv run python scripts/ocr/benchmark.py --samples ./data/ocr-samples --mode pipeline --out bench-pipeline.json
```

`bench.json` chứa văn bản nhận dạng của từng mẫu; `--rescore bench.json` tính lại chỉ số
từ văn bản đã lưu mà không chạy lại OCR.
