# OCR Engine Manager — Hướng dẫn sử dụng & API

Vị trí: **Settings (Cài đặt) → Content Processing → OCR Engine Manager** (chỉ quản trị viên).

## 1. Luồng sau triển khai

```
Upload PDF/ảnh → API → worker (process_source) → source graph content_process()
   ├─ cấu hình mặc định (RapidOCR, không tuỳ chỉnh, Auto vẫn chọn RapidOCR)
   │     → content_core.extract_content()  (KHÔNG đổi một dòng hành vi)
   └─ engine khác / tuỳ chỉnh / Auto có thể đổi engine
         → open_notebook/ocr/docling_extract.py
             PdfPipelineOptions(... giống hệt Content Core ..., ocr_options=<engine>)
             DocumentConverter → Layout Heron → TableFormer → OCR đã chọn → Markdown
   → Transformation / Embedding / SurrealDB (không đổi)
```

Module mới: `open_notebook/ocr/` (catalog, paths, runtime, store, installer, options, status,
docling_extract, tester, metrics, bundle, cli), `api/routers/ocr.py`, `api/ocr_service.py`,
`commands/ocr_commands.py`, UI `frontend/src/app/(dashboard)/settings/components/OcrEngineManager.tsx`.

Giữ nguyên: Docling, Layout Heron, TableFormer, PDF backend, Content Core, transformation,
embedding, RAG, chat, mọi loại nguồn khác (URL, Office, audio, YouTube…).

## 2. Bốn lựa chọn

| ID | Tên | Docling class | Ngôn ngữ | Model | Runtime |
|---|---|---|---|---|---|
| `rapidocr` | RapidOCR – PaddleOCR | `RapidOcrOptions(backend=<như Auto>, lang=[])` | mặc định PP-OCR | có sẵn (gói rapidocr) | có sẵn cùng Docling |
| `tesseract_fast` | Tesseract Vietnamese Fast | `TesseractCliOcrOptions(lang=[fast/vie, fast/eng])` | vie+eng | tessdata_fast 4.1.0 (15 MB) | gói hệ thống `tesseract-ocr` ≥ 4 |
| `tesseract_best` | Tesseract Vietnamese Best | `TesseractCliOcrOptions(lang=[best/vie, best/eng])` | vie+eng | tessdata_best 4.1.0 (38 MB) | gói hệ thống `tesseract-ocr` ≥ 4 |
| `easyocr` | EasyOCR Vietnamese | `EasyOcrOptions(lang=[vi,en], use_gpu=False, download_enabled=False)` | vi+en | craft_mlt_25k + latin_g2 (99 MB) | Python `easyocr==1.7.2` |

## 3. Trạng thái hiển thị

| Trạng thái | Ý nghĩa |
|---|---|
| Chưa cài đặt (`not_installed`) | Thiếu model **hoặc** thiếu runtime (xem dòng Runtime/Tệp model) |
| Đang chờ / Đang tải / Đang kiểm tra | Job worker thật đang chạy; thanh tiến trình lấy từ manifest của worker |
| Cần khởi động lại (`requires_restart`) | Runtime vừa cài bằng CLI sau khi tiến trình đã chạy |
| Sẵn sàng (`ready`) | Runtime hoạt động **và** mọi tệp model khớp SHA-256 ghim cứng |
| Thất bại (`failed`) | Job lỗi (thông báo cụ thể), model hỏng checksum, hoặc worker chết giữa chừng |
| Không tương thích (`incompatible`) | Tesseract < 4, easyocr ≠ 1.7.x, `TESSDATA_PREFIX` sai, Docling thiếu API |

## 4. Thao tác

- **Cài đặt / Thử lại**: đưa job `ocr_install_model` vào hàng đợi; chỉ tải model của engine đó
  (osd dùng chung cho Fast/Best được tái sử dụng). Không cài runtime.
- **Hướng dẫn cài runtime**: hiển thị biến môi trường và lệnh CLI; ứng dụng web không chạy
  pip/apt.
- **Sử dụng**: chỉ khi engine `ready`; nếu không, engine đang dùng giữ nguyên.
- **Kiểm tra**: job `ocr_test_engine` chạy *đường xử lý thật* (Docling + Layout + TableFormer +
  OCR đã chọn) trên ảnh mẫu tổng hợp; hiển thị engine, model, ngôn ngữ, thiết bị, class OCR
  Docling thực sự dùng, văn bản, thời gian, CER.
- **Gỡ model**: bị chặn khi engine đang dùng hoặc đang cài; không xoá osd khi engine kia còn
  cần; không bao giờ xoá Layout/TableFormer/RapidOCR/tesseract binary.
- **Cấu hình**: bật/tắt OCR, số luồng CPU (trống = mặc định Docling 4), bắt buộc OCR toàn trang.
  Áp dụng cho job xử lý tiếp theo (worker đọc lại Settings mỗi job), không cần restart.

## 5. API (admin, `require_admin`)

| Method | Path | Mô tả |
|---|---|---|
| GET | `/api/ocr/engines` | general info + config + 4 engine |
| GET | `/api/ocr/engines/{id}` | một engine |
| POST | `/api/ocr/engines/{id}/install` | 202 + `job_id`; 400 nếu builtin / đang cài / runtime không tương thích |
| POST | `/api/ocr/engines/{id}/activate` | 400 nếu chưa ready (giữ engine cũ) |
| POST | `/api/ocr/engines/{id}/test` | 202 + `job_id` |
| DELETE | `/api/ocr/engines/{id}/model` | 400 nếu đang dùng / builtin / đang cài |
| GET | `/api/ocr/jobs/{job_id}` | trạng thái job OCR (chỉ job OCR) |
| GET/PUT | `/api/ocr/config` | `docling_ocr`, `docling_ocr_num_threads` (0 = mặc định), `docling_ocr_force_full_page` |

`PUT /api/settings` **không** nhận `docling_ocr_engine` (tránh bỏ qua kiểm tra ready);
`GET /api/settings` trả về giá trị chỉ-đọc.

## 6. CLI quản trị

```bash
docker compose exec open_notebook uv run --no-sync python -m open_notebook.ocr.cli status
docker compose exec open_notebook uv run --no-sync python -m open_notebook.ocr.cli install-model tesseract_best
docker compose exec open_notebook uv run --no-sync python -m open_notebook.ocr.cli runtime install easyocr
docker compose exec open_notebook uv run --no-sync python -m open_notebook.ocr.cli remove-model easyocr
```
