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

## 7. Chất lượng OCR theo lựa chọn (Phase 8C)

Số đo trên dữ liệu tổng hợp, CPU; chi tiết: [OCR_QUALITY_BENCHMARK.md](OCR_QUALITY_BENCHMARK.md).

| Lựa chọn | Phù hợp | Không phù hợp |
|---|---|---|
| Tesseract Vietnamese Best | Văn bản và bảng scan tiếng Việt từ 150 DPI; trang xoay 90/180/270°; số tiền, ngày, số hiệu | Tiêu đề in đậm chữ hoa có dấu chồng có thể mất dấu |
| Tesseract Vietnamese Fast | Như Best, nhanh hơn một chút; số liệu trong bảng | Nhãn chữ trong bảng kém Best |
| RapidOCR (mặc định) | Chữ số, ngày, số tiền; PDF có text layer | Dấu tiếng Việt trên trang scan (model không có bảng ký tự tiếng Việt) |
| EasyOCR Vietnamese | Ảnh scan từ 200 DPI, văn bản thường | Scan 150 DPI: sai chữ số và dấu; bảng |

- Trang scan nằm ngang/ngược được tự sửa hướng cho **mọi** lựa chọn khi đã cài Tesseract Fast hoặc
  Best (cần `osd.traineddata`). Chưa cài thì hành vi như trước.
- Metadata của source ghi `ocr_scale`, `scan_dpi`, `rotated_pages`.
- Cấu hình và cách tắt từng phần: [OCR_QUALITY_OPTIMIZATION.md](OCR_QUALITY_OPTIMIZATION.md) §6.

## 8. Ba trạng thái và phân loại chất lượng (Phase 8D, D-27)

Giao diện và API báo **ba trạng thái độc lập** cho mỗi lựa chọn. Không trạng thái nào suy ra trạng thái khác.

| Trạng thái | Câu hỏi nó trả lời | Nguồn |
|---|---|---|
| 1. Sẵn sàng (`state`, `ready`) | Runtime và model đã cài, chọn được chưa? | cài đặt + smoke test |
| 2. Đã xác minh offline (`readiness`) | Toàn bộ pipeline chạy được khi không có Internet chưa? | "Chuẩn bị" / "Kiểm tra offline" |
| 3. Chất lượng (`quality`) | Engine này đo được ra sao trên văn bản tiếng Việt? | benchmark Phase 8C/8D, cố định theo phiên bản |

Một engine có thể "Sẵn sàng" và "Đã xác minh offline" nhưng vẫn ở mức "Thử nghiệm".

| Lựa chọn | Phân loại | Dùng cho | Giới hạn đã đo |
|---|---|---|---|
| Tesseract Vietnamese Best | **Khuyến nghị cho tiếng Việt** | Văn bản và bảng scan tiếng Việt; chất lượng tổng thể tốt nhất | Một số tiêu đề in đậm chữ hoa mất dấu (đã chấp nhận, không chặn) |
| Tesseract Vietnamese Fast | **Ưu tiên tốc độ** | Nhanh hơn; bảng biểu tốt trên tập holdout (41/42 dòng) | Một số nhãn chữ trong bảng và tiêu đề in đậm mất dấu |
| RapidOCR – PaddleOCR | **Tương thích ngược** | Engine gốc; không đổi model hay cấu hình mặc định | Mất dấu tiếng Việt trên trang scan; không khớp được nhãn chữ trong bảng tiếng Việt (0/42 dòng holdout) |
| EasyOCR Vietnamese | **Thử nghiệm** | Chỉ để đánh giá | Sai chữ số và dấu ở scan 150 DPI; không dùng cho văn bản tài chính. Tăng độ phân giải giúp cải thiện nhưng không sửa được mọi lỗi |

Quy tắc:

- Engine mặc định không bao giờ tự đổi. Không có fallback tự động sang engine khác; đặc biệt không bao
  giờ sang engine thử nghiệm.
- Trước khi bật engine thử nghiệm, giao diện hiển thị cảnh báo và yêu cầu admin xác nhận.
- **Tự sửa hướng trang scan** là tính năng chung, hiển thị ở phần "Thông tin chung": khả dụng khi có
  binary Tesseract và `osd.traineddata` (có sau khi cài Tesseract Fast hoặc Best). Khi không khả dụng,
  mọi engine vẫn chạy theo khả năng gốc; hệ thống không tự tải hay cài Tesseract. Tắt hẳn bằng
  `OCR_PDF_PREP=false`.
- Tiếng Anh: `docs/7-DEVELOPMENT/decisions/ADR-013-ocr-engine-manager.md` (Addendum) và giao diện en-US.

## 9. Bổ sung Phase 9B

- **Quyền:** ngoài các API OCR, từ Phase 9B backend cũng chỉ cho quản trị viên ghi / kiểm tra credential nhà
  cung cấp và model, quản lý transformation, embed và dựng lại embedding, xóa insight (D-31).
- **Giới hạn thời gian dò hướng trang:** tối đa 200 trang scan và 600 giây cho mỗi tài liệu
  (`OCR_PAGE_OSD_MAX_PAGES`, `OCR_PAGE_OSD_BUDGET_SECONDS`). Chạm giới hạn thì các trang còn lại giữ nguyên
  hướng, tài liệu vẫn được xử lý; log và metadata ghi `page_orientation_limit` (D-30).
- **Chuyển đổi một phần:** log ghi `conversion_status` và `conversion_errors` cho từng tài liệu; khác `success`
  nghĩa là Docling bỏ qua một trang hoặc một vùng (D-32).
- **RapidOCR lưu bền:** sau khi tạo lại container vẫn cần "Chuẩn bị" một lần khi có Internet (file từ điển của
  RapidOCR nằm trong container); trạng thái sẵn sàng tự chuyển về "chưa kiểm tra" (D-32).
- Hướng dẫn vận hành theo tình huống: [OCR_OPERATOR_GUIDE.md](OCR_OPERATOR_GUIDE.md).
