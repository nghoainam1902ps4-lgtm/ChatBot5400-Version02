# OCR Architecture Audit (Phase 0)

Ngày khảo sát: 2026-11-12 · Branch: `claude/friendly-mendel-a2b6m5` ·
Commit gốc (mốc rollback): `5e042279439302d3ccf39bef4d1d8d402314d194` (release v1.0.8)

## 1. Phiên bản

| Thành phần | Phiên bản | Nguồn xác minh |
|---|---|---|
| ChatBot5400 | v1.0.8 (`frontend/package.json`), `VERSION`=1.0.2 (file cũ, không dùng) | repo |
| Open Notebook (nền) | `pyproject.toml` version 1.14.0 | repo |
| Python | 3.12 (`.python-version`, image `python:3.12-slim-trixie`) | repo |
| Content Core | 2.0.7 | `uv.lock` |
| Docling | 2.129.0 (docling-core 2.96.0, docling-ibm-models 4.0.3, docling-parse 7.20.0) | `uv.lock` |
| RapidOCR | 3.9.2 | `uv.lock` |
| PyTorch | 2.14.0 (torchvision 0.29.0) | `uv.lock` |
| onnxruntime | **không cài** | `.venv` sau `uv sync --extra docling` |
| EasyOCR / tesserocr | **không cài** | `.venv` |
| Frontend | Next.js 16, React 19, TanStack Query, i18next (vi-VN, en-US) | `frontend/package.json` |
| Backend | FastAPI + surreal-commands worker | repo |
| Database | SurrealDB v2 (migrations 1..33 tự chạy khi API khởi động) | repo |

> **Lưu ý triển khai thực tế:** image production *không* chứa Docling. Entry point cài
> `content-core[docling]==<version của content-core>` lúc boot khi
> `OPEN_NOTEBOOK_ENABLE_DOCLING=true` bằng `uv pip install` (không theo `uv.lock`). Vì vậy
> phiên bản Docling trên VPS có thể **khác** 2.129.0. Mã mới kiểm tra sự tồn tại của các
> class/field Docling lúc chạy và báo `incompatible` nếu thiếu.

## 2. OCR engine thực tế hiện nay

Content Core 2.0.7 (`content_core/processors/document/docling.py::extract_docling`) tạo:

```python
PdfPipelineOptions(do_ocr=cfg.docling_ocr, do_formula_enrichment=..., do_picture_description=..., do_chart_extraction=...)
DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=...)})
```

Không truyền `ocr_options` ⇒ Docling dùng mặc định `OcrAutoOptions()` (lang=`[]`).
`docling/models/stages/ocr/auto_ocr_model.py` chọn theo thứ tự trên Linux:

1. nemotron (không cài) → 2. RapidOCR backend **onnxruntime** (cần `onnxruntime` — không cài)
→ 3. **EasyOCR** (nếu cài) → 4. RapidOCR backend **torch**.

⇒ **Engine thực tế = RapidOCR 3.9.2, backend torch, `lang=[]` = mô hình PP-OCRv6 small mặc
định (Simplified Chinese/Latin)**. Trọng số `.pth` được RapidOCR tự tải từ
`www.modelscope.cn` vào thư mục package (trong venv, mất khi recreate container) ở lần dùng
đầu tiên. Wheel RapidOCR có kèm sẵn bản ONNX (`PP-OCRv6_det_small.onnx`,
`PP-OCRv6_rec_small.onnx`, `ch_ppocr_mobile_v2.0_cls_mobile.onnx`) nhưng không dùng vì thiếu
onnxruntime.

**Rủi ro tương thích ngược phát hiện được:** nếu chỉ `pip install easyocr` (để thêm lựa chọn
EasyOCR) thì chế độ Auto sẽ **âm thầm chuyển** mọi người dùng từ RapidOCR sang EasyOCR (bước 3
đứng trước bước 4). Thiết kế mới phải ghim RapidOCR tường minh khi EasyOCR có mặt.

Ảnh (PNG/JPEG/TIFF/BMP) đi qua Docling với `InputFormat.IMAGE` **không có** format option ⇒
luôn OCR (Auto), bỏ qua cờ `docling_ocr`.

## 3. Layout / Table thực tế

- Layout: `LayoutObjectDetectionOptions` mặc định = **`layout_heron_default`** (Docling Heron).
- Table: `TableStructureOptions` (TableFormer V1, kind `docling_tableformer`, mode `ACCURATE`).
- Khớp với yêu cầu (Heron/TableFormer) — giữ nguyên, không truyền `layout_options` /
  `table_structure_options`.
- Trọng số tải từ Hugging Face vào `HF_HOME=/app/data/.cache/huggingface` (persistent).

## 4. Luồng xử lý PDF

```
POST /api/sources (api/routers/sources.py)
  → submit_command("process_source")  [hoặc execute_command_sync khi async_processing=false]
  → worker: commands/source_commands.py::process_source_command
  → open_notebook/graphs/source.py::source_graph → content_process()
      ContentSettings.get_instance() → ContentCoreConfig(document_engine, docling_ocr, …)
  → content_core.extract_content(file_path=…, config=…)
      → _extract_file → get_file_type (mime) → _route_for_mime → extract_docling()
          → PdfPipelineOptions + DocumentConverter(...).convert(path) → export_to_markdown()
  → save_source → transformations (graph) → embed (vectorize) → SurrealDB
```

File khởi tạo Docling duy nhất: `content_core/processors/document/docling.py` (site-packages,
không được sửa). ChatBot5400 chỉ truyền `ContentCoreConfig`.

## 5. Khả năng truyền OCR engine qua Content Core

`ContentCoreConfig` 2.0.7 chỉ có `docling_output_format`, `docling_ocr`, `docling_formulas`,
`docling_vision`. **Không có** `ocr_options`/`accelerator_options`, không có hook. ⇒ Ưu tiên 1
(API có sẵn) không khả thi. Ưu tiên 3 (fork Content Core) cần host một repo fork (phiên làm việc
không được tạo repository) và bảo trì lâu dài. ⇒ Chọn **ưu tiên 2: lớp cấu hình tối thiểu trong
ChatBot5400** (xem `DECISIONS.md` D-02).

## 6. Settings, xác thực, job

- `ContentSettings` (`open_notebook/domain/content_settings.py`) là `RecordModel` singleton
  (record `open_notebook:content_settings`, schemaless). Trường mới có default Pydantic ⇒
  **không cần migration**.
- **Lỗi có sẵn:** singleton nạp DB *một lần mỗi process*; worker không bao giờ nạp lại ⇒ thay
  đổi Settings không tới worker cho tới khi restart. Cần nạp lại khi xử lý mỗi nguồn (D-05).
- Phân quyền: JWT middleware + `require_admin` (`api/auth.py`). PUT `/api/settings` đã là admin.
- Background job: surreal-commands (`@command`, `submit_command`, `get_command_status`).
  **Lưu ý bảo mật có sẵn:** `POST /api/commands/jobs` cho mọi user đã đăng nhập submit bất kỳ
  command đã đăng ký ⇒ command OCR phải tự xác thực (nonce do API admin sinh).
- Capability probe: `GET /api/capabilities` (`open_notebook/utils/runtime_capabilities.py`).

## 7. Docker / lưu trữ

- `Dockerfile` multi-stage; runtime `python:3.12-slim-trixie`, chạy supervisord (api, worker,
  frontend) **với quyền root** (có sẵn, không thay đổi trong phạm vi này).
- Volume: `./notebook_data:/app/data` (dev & prod), `./surreal_data:/mydata`.
- Cache persistent: `UV_CACHE_DIR=/app/data/.cache/uv`, `HF_HOME=/app/data/.cache/huggingface`,
  `PLAYWRIGHT_BROWSERS_PATH`. Venv nằm trong layer image (ephemeral) — entrypoint cài lại extra
  từ cache mỗi container mới (ADR-007).
- Prod (`deploy/docker-compose.prod.yml`): `OPEN_NOTEBOOK_ENABLE_DOCLING=true`,
  `UV_TORCH_BACKEND=cpu`, `OPEN_NOTEBOOK_WORKER_MAX_TASKS=1`.

## 8. Docling 2.129 — API OCR đã xác minh

| Class | Trường dùng | Ghi chú |
|---|---|---|
| `RapidOcrOptions` | `backend`, `lang`, `mode` | `lang=[]` = model mặc định |
| `TesseractCliOcrOptions` | `lang`, `path`, `tesseract_cmd`, `mode` | **`path` không áp dụng cho `--list-langs` và OSD** ⇒ cần `TESSDATA_PREFIX` cố định (D-04) |
| `EasyOcrOptions` | `lang`, `use_gpu`, `model_storage_directory`, `download_enabled`, `recog_network` | `use_gpu=False` ép CPU chỉ cho OCR |
| `PdfPipelineOptions` | `ocr_options`, `accelerator_options` | |
| `AcceleratorOptions` | `num_threads`, `device` | BaseSettings (`DOCLING_*`/`OMP_NUM_THREADS`) |
| `OcrMode` | `DEFAULT`, `FULL_PAGE` | `force_full_page_ocr` đã deprecated ⇒ dùng `mode` |

## 9. Khả năng của Cloud (phiên này)

| Hạng mục | Kết quả |
|---|---|
| CPU / RAM / đĩa | 4 vCPU, 15 GiB RAM, ~24 GB trống |
| Python / uv | 3.12 venv qua uv 0.11 — `uv sync --extra docling` OK |
| Docker CLI | Có; **Docker daemon không chạy** (`/var/run/docker.sock` không tồn tại) |
| apt (root) | Có — đã cài `tesseract-ocr` 5.3.4 để kiểm thử |
| GitHub (raw/releases) | Truy cập được ⇒ tải được tessdata & EasyOCR model |
| PyPI | Truy cập được |
| **huggingface.co** | **Bị chặn (403 proxy)** ⇒ không tải được Layout Heron / TableFormer |
| **www.modelscope.cn** | **Bị chặn (403 proxy)** ⇒ RapidOCR torch không tải được trọng số |

Hệ quả: **không thể chạy toàn bộ pipeline Docling trong Cloud**. Kiểm thử OCR thực hiện ở mức
*OCR stage* bằng chính class OCR của Docling (qua factory chính thức) trên trang PDF đã render;
toàn bộ pipeline có script nghiệm thu chạy trên máy triển khai (`NOT VERIFIED` trong Cloud).
Không thay đổi chính sách mạng của môi trường (theo yêu cầu).
