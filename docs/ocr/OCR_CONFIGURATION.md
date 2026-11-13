# OCR Configuration

## 1. Trường Settings (record `open_notebook:content_settings`)

| Trường | Kiểu | Mặc định | Ghi chú |
|---|---|---|---|
| `docling_ocr` | bool | `true` (có sẵn) | Bật/tắt OCR cho PDF qua Docling |
| `docling_ocr_engine` | `rapidocr \| tesseract_fast \| tesseract_best \| easyocr` | `rapidocr` | Chỉ đổi qua `POST /api/ocr/engines/{id}/activate` |
| `docling_ocr_device` | `cpu` | `cpu` | Thông tin; OCR luôn CPU |
| `docling_ocr_num_threads` | int 1–64 \| null | `null` | `null` = mặc định Docling (4 / `OMP_NUM_THREADS`); khi đặt ⇒ `AcceleratorOptions(num_threads=N)` |
| `docling_ocr_force_full_page` | bool | `false` | `OcrMode.FULL_PAGE` |

**Không có migration**: bản ghi cũ không có các trường mới ⇒ Pydantic dùng mặc định ⇒ hành vi
cũ. Không ghi gì vào DB cho tới khi admin lưu.

## 2. Biến môi trường

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `OCR_DATA_DIR` | `<DATA_FOLDER>/ocr` (`/app/data/ocr`) | Gốc dữ liệu OCR |
| `OCR_MODELS_DIR` | `$OCR_DATA_DIR/models` | Model đã xác minh |
| `OCR_PACKAGES_DIR` | `$OCR_DATA_DIR/packages` | Wheel/.deb/model staging từ offline bundle |
| `OCR_MANIFESTS_DIR` | `$OCR_DATA_DIR/manifests` | Trạng thái cài đặt từng engine |
| `OCR_OFFLINE` | `false` | `true` = không bao giờ tải qua mạng |
| `TESSDATA_PREFIX` | `$OCR_MODELS_DIR/tesseract` (Dockerfile) | Phải trùng thư mục trên; khác ⇒ `incompatible` |
| `OCR_TESSERACT_CMD` | `tesseract` | Tên/đường dẫn executable |
| `OPEN_NOTEBOOK_ENABLE_OCR_TESSERACT` | – | Entrypoint khôi phục `tesseract-ocr` |
| `OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR` | – | Entrypoint khôi phục `easyocr==1.7.2` |
| `OCR_TRUSTED_WHEELS_SHA256` / `OCR_TRUSTED_DEBS_SHA256` | – | Digest ghim (in ra bởi `bundle install`) để cho phép cài gói đã stage offline |
| `OPEN_NOTEBOOK_RUNTIME_CONSTRAINTS` | `/app/runtime-constraints.txt` (Docker) | Constraints xuất từ `uv.lock`, áp dụng khi cài Docling/EasyOCR lúc chạy (D-14) |
| `OCR_ALLOW_UNVERIFIED_DEPENDENCIES` | – | `true` = cho phép engine khác RapidOCR khi Content Core/Docling khác bộ đã kiểm chứng (chỉ sau khi tự kiểm chứng lại) |
| `OCR_RAPIDOCR_FORCE_CPU` | – | `true` = RapidOCR chạy CPU kể cả khi có GPU (chỉ OCR; D-16). Mặc định giữ hành vi cũ |
| `HF_HUB_OFFLINE` | – | `1` cho máy không Internet: Docling chỉ dùng model Heron/TableFormer đã có trong `HF_HOME` |
| `OCR_HF_HUB_TIMEOUT` | `20` | Giây; timeout cho request Hugging Face Hub không tự đặt timeout (D-24) |
| `OCR_RAPIDOCR_PERSISTENT` | – | `true` = trọng số RapidOCR nằm trên data volume (D-08) |
| `OCR_TESSERACT_OSD_GATE` | bật | `false` = không lọc kết quả dò hướng độ tin cậy thấp của Tesseract (D-25) |
| `OCR_TESSERACT_OSD_MIN_CONFIDENCE` | `2.0` | Ngưỡng `Orientation confidence` trên từng vùng OCR (D-25) |
| `OCR_PDF_PREP` | bật | `false` = không dò hướng trang scan, không chỉnh scale theo độ phân giải scan (D-25) |
| `OCR_PAGE_OSD_MIN_CONFIDENCE` | `2.0` | Ngưỡng `Orientation confidence` trên cả trang (D-25) |
| `OCR_PAGE_OSD_MAX_PAGES` | `200` | Số trang scan tối đa được dò hướng trong một tài liệu (D-25) |
| `OCR_EASYOCR_CONFIDENCE` | `0.2` | Ngưỡng confidence dòng của EasyOCR, 0–1 (D-26) |
| Build arg `OCR_INSTALL_TESSERACT` | `false` | Nướng Tesseract vào image |

Các biến Phase 8C là cấu hình toàn deployment (đọc khi dựng OCR options), không đổi theo từng job.
Cơ sở chọn mặc định: [OCR_QUALITY_OPTIMIZATION.md](OCR_QUALITY_OPTIMIZATION.md).

### 2.1 Trạng thái do API trả về (Phase 8D)

| Trường | Ý nghĩa |
|---|---|
| `engines[].quality` | Phân loại chất lượng: `recommended` · `speed` · `compatibility` · `experimental`. Độc lập với `ready` và với `readiness` |
| `general.page_orientation.enabled` | Chuẩn hóa hướng trang không bị tắt (`OCR_PDF_PREP`) |
| `general.page_orientation.available` | Thật sự chạy được: có binary Tesseract **và** `osd.traineddata` |
| `general.page_orientation.reason` | `ok` · `disabled` · `tesseract_missing` · `osd_data_missing` |
| metadata source `page_orientation` | Như `reason`, cộng `not_a_pdf` / `skipped`, cho từng tài liệu |

Đổi biến chất lượng nào (hoặc cài/gỡ `osd.traineddata`) cũng làm kết quả readiness cũ hết hiệu lực
(fingerprint `quality`); chạy lại "Chuẩn bị" hoặc "Kiểm tra offline".

## 3. Ánh xạ engine → Docling (đã xác minh trên Docling 2.129.0)

Xem `open_notebook/ocr/options.py` và DECISIONS D-01…D-04, D-09. Ghi chú quan trọng:

- Tesseract: Docling chạy `tesseract --list-langs` và OSD **không** kèm `--tessdata-dir`, nên
  dùng một `TESSDATA_PREFIX` cố định, mã ngôn ngữ dạng thư mục con (`fast/vie`), và một tệp
  cấu hình chuẩn `configs/tsv` (`tessedit_create_tsv 1`) do mã tự tạo trong thư mục tessdata.
  Từ Phase 8C file `configs/tsv` có thêm `user_defined_dpi 216`; `tesseract_cmd` trỏ tới
  `open_notebook/ocr/tesseract_gate.py` (lọc OSD, D-25); `scale` theo độ phân giải ảnh scan.
- Mọi engine: trang scan nằm ngang/ngược được sửa `/Rotate` trong bản sao tạm trước khi Docling
  chuyển đổi (`pdf_prep.py`), khi có binary Tesseract và `osd.traineddata`.
- EasyOCR: `download_enabled=False` ⇒ không bao giờ tải model trong lúc xử lý tài liệu;
  `confidence_threshold=0.2` (D-26).
- RapidOCR: backend = cái Auto đang chọn (`onnxruntime` nếu có, ngược lại `torch`), `lang=[]`.
