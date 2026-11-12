# OCR Engine Manager — MASTER PLAN

> Tài liệu gốc lưu toàn bộ yêu cầu, giới hạn kiến trúc, phạm vi và tiêu chí nghiệm thu
> của nhiệm vụ "OCR Engine Manager cho ChatBot5400". Nếu context bị rút gọn, đọc lại file
> này cùng `PROGRESS.md`, `DECISIONS.md`, `CHECKPOINT.md`, `ACCEPTANCE_CHECKLIST.md`
> trước khi tiếp tục.

## 1. Mục tiêu

Nâng cao chất lượng OCR tiếng Việt trên CPU cho tài liệu nghiệp vụ ngân hàng (PDF có text,
PDF scan, công văn/quyết định/thông tư, nhiều trang, bảng biểu phức tạp, số tiền, ngày
tháng, số hiệu văn bản) **mà không thay đổi kiến trúc và mã nguồn cốt lõi**.

Thực hiện liên tục Phase 0 → 6 trong một phiên Claude Code: khảo sát, thiết kế, triển khai,
kiểm thử, review, commit/push lên branch phát triển. Không merge main, không deploy
production.

## 2. Kiến trúc đã chốt

- Giữ nguyên Docling làm Document Processing Engine; chỉ cho phép chọn OCR engine thay
  RapidOCR mặc định.
- Giữ nguyên: Layout model, Table model (TableFormer), PDF backend, luồng xử lý, định dạng
  đầu ra (Markdown), Transformation, Embedding, Vector DB, RAG, Chat AI.
- Nếu model Layout/Table thực tế khác Heron/TableFormer → ghi nhận, giữ nguyên.

```
PDF/PDF Scan → Content Processing hiện có → Docling → OCR engine (chọn) →
Layout hiện có → Table hiện có → Output hiện có → Transformation/Embedding/DB hiện có
```

### Danh sách engine (đúng 3 engine, 4 lựa chọn)

| Engine ID | Tên hiển thị | Model |
|---|---|---|
| `rapidocr` | RapidOCR – PaddleOCR | Model gốc của dự án (không nâng cấp PP-OCR) |
| `tesseract_fast` | Tesseract Vietnamese Fast | tessdata_fast, `vie`+`eng`, Tesseract CLI |
| `tesseract_best` | Tesseract Vietnamese Best | tessdata_best, `vie`+`eng`, Tesseract CLI |
| `easyocr` | EasyOCR Vietnamese | Latin Gen2 (`vi`,`en`), CPU bắt buộc |

Tesseract Fast/Best dùng chung executable, khác thư mục trọng số.

### Chỉ dùng API chính thức của Docling

`RapidOcrOptions`, `TesseractCliOcrOptions`, `EasyOcrOptions`, `PdfPipelineOptions`,
`AcceleratorOptions` — phải xác minh theo phiên bản Docling thực tế đang khoá.

### Tuyệt đối không

TrueOCR, VietOCR, ProtonX OCR, DeepSeek OCR, PaddleOCR-VL; engine cần custom adapter; class
kế thừa `BaseOcrModel`; sửa lõi Docling; monkey patch; sửa site-packages; viết lại pipeline
PDF; thay Content Core; đổi Layout/TableFormer; yêu cầu GPU/CUDA cho OCR; gửi dữ liệu OCR ra
ngoài; đổi các tích hợp AI/embedding khác.

## 3. Nguyên tắc thực thi

- Được: đọc/sửa code, cài dependency trong Cloud, chạy test/build, subagent, commit/push lên
  branch phát triển.
- Không: merge main, force push, ghi đè việc chưa commit, deploy production, truy cập VPS,
  xoá dữ liệu/DB/volume, đưa secrets/tài liệu ngân hàng lên GitHub, tự đổi quyền mạng/bảo mật.
- Ghi nhận commit gốc làm mốc rollback.

## 4. Phạm vi theo Phase

- **Phase 0** — Khảo sát repo, truy vết luồng PDF, nghiên cứu cách truyền OCR options, kiểm
  tra khả năng Cloud. Đầu ra: `OCR_ARCHITECTURE_AUDIT.md`, `OCR_IMPLEMENTATION_PLAN.md`.
- **Phase 1** — Cấu hình OCR trong Content Processing Settings (`docling_ocr`,
  `docling_ocr_engine`, `docling_ocr_device=cpu`, `docling_ocr_num_threads`,
  `docling_ocr_force_full_page`); ánh xạ engine → class Docling chính thức; Tesseract
  fast/best thư mục riêng; EasyOCR `vi`+`en`, CPU, thư mục model riêng, không tự tải model khi
  xử lý; lỗi rõ ràng, không âm thầm fallback.
- **Phase 2** — Cài đặt theo nhu cầu (không tải engine nào lúc cài/khởi động), persistent
  storage dưới `/app/data/ocr`, phân biệt model / Python deps / system packages / executable
  / config, vòng đời trạng thái (`not_installed, pending, downloading, installing,
  requires_restart, ready, failed, incompatible`), kiểm tra dung lượng, ghim phiên bản,
  checksum, chống tải trùng, retry, staging, không đánh dấu ready trước khi kiểm tra; chặn gỡ
  model đang dùng; không xoá dependency chung / Layout / TableFormer / tesseract binary.
- **Phase 3** — API (`/api/ocr/engines`, install, activate, test, delete model, jobs) dùng
  background job hiện có và phân quyền admin hiện có; UI Settings → Content Processing → OCR
  Engine Manager (vi/en), thông tin chung, 4 engine với trạng thái thật, thao tác thật, cấu
  hình, test OCR với mẫu không nhạy cảm.
- **Phase 4** — Offline bundle (manifest, models, wheels, system-packages, checksums,
  README); cài offline không gọi HF/PyPI; cập nhật image/recreate container giữ dữ liệu,
  cấu hình, model; khôi phục runtime.
- **Phase 5** — Unit, integration (engine thực tế qua Docling), Docker test (hoặc NOT
  VERIFIED + script), benchmark (CER/WER chỉ khi có ground truth, không số liệu giả),
  regression.
- **Phase 6** — Security review, tài liệu bàn giao, review độc lập toàn bộ diff.

## 5. Tiêu chí nghiệm thu

Xem `ACCEPTANCE_CHECKLIST.md` — mỗi tiêu chí PASS / FAIL / NOT VERIFIED kèm bằng chứng.

## 6. Ưu tiên

1. An toàn dữ liệu 2. Tương thích ngược 3. Thay đổi tối thiểu 4. Giữ nguyên lõi Docling
5. Chất lượng OCR tiếng Việt 6. Chạy CPU 7. Cài theo nhu cầu 8. Offline 9. Bảo trì lâu dài.
