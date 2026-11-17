# Phase 12C — Báo cáo triển khai Legal Document Normalization

Thiết kế: [PHASE12B_LEGAL_NORMALIZATION_DESIGN.md](PHASE12B_LEGAL_NORMALIZATION_DESIGN.md) · quyết định D-34.

## 1. File thay đổi

### Backend

| File | Thay đổi |
|---|---|
| `open_notebook/ocr/legal_normalizer.py` (mới) | normalizer thuần: phát hiện số trang / header lặp, placeholder, ghép liên trang, serializer giữ marker gốc, giới hạn tài nguyên, `normalize_or_fallback`, cổng `OCR_LEGAL_NORMALIZATION_ENABLED` |
| `open_notebook/ocr/options.py` | `OcrSettings.text_normalization` (đã giải theo cổng), thuộc tính `legal_normalization` |
| `open_notebook/ocr/docling_extract.py` | Legal + PDF ⇒ lớp Docling (cả RapidOCR mặc định, cả URL PDF); `convert_file` gọi normalizer chỉ khi Legal + PDF (kiểm tra magic bytes) + Markdown; metadata normalization |
| `open_notebook/domain/content_settings.py` | trường `ocr_text_normalization` (`standard` / `legal`, mặc định `standard`, không migration) |
| `open_notebook/graphs/source.py` | log chế độ hiệu lực; log khi Legal bật nhưng tài liệu không thuộc phạm vi |
| `api/models.py`, `api/ocr_service.py` | `OcrConfig` thêm lựa chọn đã lưu / hiệu lực / cổng / phiên bản; `OcrConfigUpdate.ocr_text_normalization`; từ chối Legal khi cổng tắt (`InvalidInputError` → 400) |

### Frontend

| File | Thay đổi |
|---|---|
| `settings/components/OcrEngineManager.tsx` | mục **Chuẩn hóa văn bản sau OCR** (Tiêu chuẩn / Văn bản pháp lý), nút lưu riêng, trạng thái hiệu lực, cảnh báo khi cổng tắt |
| `lib/types/api.ts`, `lib/api/ocr.ts` | kiểu `OcrTextNormalization`, trường mới của `OcrConfig` |
| `lib/locales/vi-VN`, `en-US` | khóa `ocr.textNormalization.*` (đủ cả hai locale) |

Giữ nguyên thiết kế mobile-first (RadioGroup có sẵn, lớp Tailwind có sẵn); chỉ quản trị viên thấy và đổi (router
`/ocr` đã `require_admin`).

### Công cụ, kiểm thử, triển khai

`tests/legal_harness.py`, `tests/fixtures/legal/legal_fixtures.py` (24 fixture), `tests/test_ocr_legal_normalizer.py`,
`tests/test_ocr_legal_pipeline.py`, `tests/test_ocr_phase12_scripts.py`, `tests/test_offline_package.py`;
`scripts/ocr/phase12_{metrics,diagnose,compare,benchmark}.py`, `scripts/ocr/generate_phase12_fixtures.py`,
`scripts/ocr/phase12-test.sh`, `scripts/windows/phase12-test.ps1`; `deploy/phase12-test/`; `scripts/offline/`;
`Dockerfile` (build arg `OCR_PREINSTALL_RUNTIMES`, mặc định `false`); `.dockerignore`.

## 2. Thiết kế thực tế so với yêu cầu

| Yêu cầu | Thực hiện |
|---|---|
| Sau Docling, trước khi lưu Source / embedding | trong `convert_file` (cả đường selected engine và đường RapidOCR mặc định khi bật Legal) |
| Không phá parity khi tắt | nhánh Standard không đổi (test so sánh byte) |
| Chỉ loại tài liệu đã nghiệm thu | PDF (magic bytes) + Markdown; mọi định dạng khác: Standard |
| Lỗi ⇒ không mất nội dung | `normalize_or_fallback` → Standard + `legal_normalization_status=failed` |
| Nhất quán RAG | `Source.full_text` = nội dung đã chuẩn hóa; `embed_source` đọc lại chính trường này (test) |
| Logging an toàn | chỉ phiên bản, số phép biến đổi theo loại, số cảnh báo, thời gian |
| UI | cài đặt toàn cục cho admin; **không** có lựa chọn theo tài liệu |

## 3. Phần chưa hoàn thành (có chủ ý / ngoài phạm vi)

1. **Lựa chọn theo từng tài liệu** — cần đổi API tạo Source + form tải lên (Phase sau).
2. **Hiển thị "đã chuẩn hóa" / cảnh báo / so sánh gốc–chuẩn hóa trên trang Source** — metadata trích xuất hiện
   không được lưu vào Source; lưu sẽ cần trường mới hoặc sidecar có vòng đời ⇒ không làm (không migration). Xem
   nội dung gốc và chuẩn hóa: dùng diagnostic cục bộ.
3. **Trích dẫn số trang trong RAG** — provenance không đi tới chunk.
4. **Sửa thứ tự đọc** — ngoài phạm vi (bảo toàn).

## 4. Cách kiểm thử

```bash
uv run pytest tests/test_ocr_legal_normalizer.py tests/test_ocr_legal_pipeline.py tests/test_ocr_phase12_scripts.py tests/test_offline_package.py
```

```bash
uv run python scripts/ocr/phase12_benchmark.py --out /tmp/phase12_benchmark.json
```

```bash
cd frontend && npx vitest run src/components/ui/markdown-renderer.test.tsx "src/app/(dashboard)/settings/components/OcrEngineManager.test.tsx"
```

Pipeline thật (Heron, TableFormer, engine, Agri): [PHASE12E_WINDOWS_LOCAL_TEST_GUIDE.md](PHASE12E_WINDOWS_LOCAL_TEST_GUIDE.md).
