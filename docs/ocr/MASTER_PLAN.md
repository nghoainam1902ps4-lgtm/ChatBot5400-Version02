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

- **Phase 7** — Hardening: khoá dependency, guard tương thích, parity, nghiệm thu full pipeline strict,
  Docker acceptance viết lại, CPU mode, đánh giá `/api/commands/jobs`, `OCR_LOCAL_ACCEPTANCE.md`.
- **Phase 8A** — Bảo mật cuối và mô hình vận hành mới:
  - **Mô hình:** ONLINE để cài / cập nhật / chuẩn bị model; OFFLINE để xử lý tài liệu (OCR, Layout,
    Table, trích xuất, Markdown). Không hứa LLM / embedding chạy offline. Cài / cập nhật hoàn toàn
    offline không bắt buộc; offline bundle giữ nguyên, không mở rộng.
  - **A — Bảo mật job nền:** API commands chỉ cho admin, tắt submit tổng quát, worker kiểm tra lại đầu
    vào (D-19).
  - **B — Chuẩn bị online + trạng thái sẵn sàng:**
    - lệnh `prepare` / `readiness`;
    - các trạng thái `runtime_missing`, `model_missing`, `model_incomplete`, `incompatible`,
      `pipeline_not_verified`, `not_offline_ready`, `offline_ready`;
    - không bao giờ báo `offline_ready` chỉ dựa trên file (D-20).
  - **C — RapidOCR:** mặc định warm-up; lưu bền vững là tuỳ chọn (D-21).
  - **D — UI:** khung trạng thái sẵn sàng với nút Chuẩn bị / Kiểm tra; lỗi rõ ràng khi thiếu model
    offline (D-22).
  - **E — Cập nhật online:** dùng lại cache và model; kết quả cũ thành lỗi thời.
  - **F — Nghiệm thu:** 4 engine; Docker gồm chuẩn bị online → offline → restart offline → cập nhật
    online (D-23); regression so với `e32eae8`.
  - **G–H — Tài liệu:** `OCR_ONLINE_PREPARATION.md` và `RELEASE_CANDIDATE.md`.

### Phase 8C — Sửa chất lượng OCR và nghiệm thu cuối

- Phân tích nguyên nhân gốc 15 bài full pipeline thất bại ([OCR_FAILURE_ANALYSIS.md](OCR_FAILURE_ANALYSIS.md)).
- Tesseract: lọc OSD độ tin cậy thấp, chuẩn hóa hướng trang, scale theo độ phân giải scan (D-25).
- EasyOCR: ngưỡng confidence 0,2 (D-26). RapidOCR: tái dùng chuẩn hóa hướng trang.
- Tập holdout độc lập chống overfitting ([OCR_QUALITY_BENCHMARK.md](OCR_QUALITY_BENCHMARK.md)).
- Không đổi ngưỡng, fixture, ground truth; không thêm engine; không sửa Docling/Content Core.
- Báo cáo: [OCR_PHASE8C_REPORT.md](OCR_PHASE8C_REPORT.md).

### Phase 8D, 9A, 9B, 9C — phát hành

- 8D: phân loại chất lượng, tiêu chí phát hành có điều kiện (D-27) — [OCR_PHASE8D_REPORT.md](OCR_PHASE8D_REPORT.md).
- 9A: công tắc tắt URL ingestion (D-29), Release Candidate — [OCR_PHASE9A_REPORT.md](OCR_PHASE9A_REPORT.md).
- 9B: review độc lập cuối, sửa lỗi phân quyền có sẵn (D-31), giới hạn thời gian dò hướng (D-30), nghiệm thu
  cuối, Pull Request và merge — [OCR_PHASE9B_REPORT.md](OCR_PHASE9B_REPORT.md).
- 9C: triển khai production theo [OCR_PRODUCTION_DEPLOYMENT_PLAN.md](OCR_PRODUCTION_DEPLOYMENT_PLAN.md), chỉ sau
  khi chủ dự án phê duyệt; vận hành theo [OCR_OPERATOR_GUIDE.md](OCR_OPERATOR_GUIDE.md).
- Không nghiên cứu OCR thêm, không thêm engine, không đổi model sau Phase 8D.

## 5. Tiêu chí nghiệm thu

Xem `ACCEPTANCE_CHECKLIST.md` — mỗi tiêu chí PASS / FAIL / NOT VERIFIED kèm bằng chứng.

## 6. Ưu tiên

1. An toàn dữ liệu 2. Tương thích ngược 3. Thay đổi tối thiểu 4. Giữ nguyên lõi Docling
5. Chất lượng OCR tiếng Việt 6. Chạy CPU 7. Cài theo nhu cầu 8. Offline 9. Bảo trì lâu dài.
