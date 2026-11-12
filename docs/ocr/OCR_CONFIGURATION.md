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
| Build arg `OCR_INSTALL_TESSERACT` | `false` | Nướng Tesseract vào image |

## 3. Ánh xạ engine → Docling (đã xác minh trên Docling 2.129.0)

Xem `open_notebook/ocr/options.py` và DECISIONS D-01…D-04, D-09. Ghi chú quan trọng:

- Tesseract: Docling chạy `tesseract --list-langs` và OSD **không** kèm `--tessdata-dir`, nên
  dùng một `TESSDATA_PREFIX` cố định, mã ngôn ngữ dạng thư mục con (`fast/vie`), và một tệp
  cấu hình chuẩn `configs/tsv` (`tessedit_create_tsv 1`) do mã tự tạo trong thư mục tessdata.
- EasyOCR: `download_enabled=False` ⇒ không bao giờ tải model trong lúc xử lý tài liệu.
- RapidOCR: backend = cái Auto đang chọn (`onnxruntime` nếu có, ngược lại `torch`), `lang=[]`.
